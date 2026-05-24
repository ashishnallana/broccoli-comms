# Broccoli Comms setup and multi-device registry guide

This guide covers:

- installing/running Broccoli Comms on a new machine
- required dependencies for Nix and non-Nix installs
- configuring managed agents
- setting up `agent-registry` for multi-device agent discovery and messaging
- validating the registry in the reusable `~/projects/nix/test-vm`

## 1. What Broccoli Comms owns

Broccoli Comms is designed to avoid depending on a user's existing Home Manager or tmux setup. The app owns:

- a private `tmux` server/socket
- a private `agent-tracker` daemon/socket
- managed agent windows launched through `agent-wrapper`
- the `agent-communicator` TUI launched with explicit private socket environment

Default paths:

| Purpose | Default |
| --- | --- |
| Runtime dir | `$XDG_RUNTIME_DIR/broccoli-comms` |
| Tracker socket | `$XDG_RUNTIME_DIR/broccoli-comms/agent-tracker.sock` |
| Tmux socket | `$XDG_RUNTIME_DIR/broccoli-comms/tmux.sock` |
| Config | `$XDG_CONFIG_HOME/broccoli-comms/config.json` |
| Logs/cache | `$XDG_CACHE_HOME/broccoli-comms` |

## 2. Dependencies

### Nix path

With Nix, Broccoli Comms packages include the runtime dependencies they launch, including:

- Python
- tmux
- agent-tracker
- agent-wrapper
- agent-communicator TUI

You still need the configured agent command itself to be usable, for example `pi`, `claude`, `codex`, or `gemini`, unless you configure agents with absolute store paths.

### Manual/non-Nix path

Manual installs currently require these on `PATH`:

- `python3`
- `tmux`
- `go` for building the TUI from source
- configured agent commands, for example `pi`, `claude`, `codex`, or `gemini`

## 3. New-machine single-device setup

From a checkout:

```sh
git clone <broccoli-comms-repo> broccoli-comms
cd broccoli-comms
nix run .#broccoli-comms -- doctor --json
nix run .#broccoli-comms -- agent add main --cwd "$HOME/project" --command 'pi'
nix run .#broccoli-comms -- start
nix run .#broccoli-comms -- open
```

For persistent installation:

```sh
cd broccoli-comms
nix profile install .#broccoli-comms
broccoli-comms doctor
broccoli-comms agent add main --cwd "$HOME/project" --command 'pi'
broccoli-comms start
broccoli-comms open
```

Useful commands:

```sh
broccoli-comms status --json
broccoli-comms agent list --json
broccoli-comms agent focus main
broccoli-comms agent attach main
broccoli-comms stop
```

## 4. Non-Nix/manual setup

```sh
git clone <broccoli-comms-repo> broccoli-comms
cd broccoli-comms
make build
./bin/broccoli-comms doctor --json
./bin/broccoli-comms agent add main --cwd "$HOME/project" --command 'pi'
./bin/broccoli-comms start
./bin/broccoli-comms open
```

If `doctor` fails, install the missing runtime dependency or use the Nix package path.

## 5. Multi-device architecture

`agent-registry` is the rendezvous service for multiple agent-tracker instances.

```text
machine A agent-tracker ─┐
                         ├─ agent-registry ─ discovery + queued messages
machine B agent-tracker ─┘
```

Important properties:

- Trackers only integrate with registries when configured with a non-empty registry list.
- Registry delivery uses durable queue + tracker long-poll/ack.
- The registry does not need to connect back to tracker machines for normal message delivery.
- Cross-device messages are at-least-once; tracker inbox delivery de-duplicates by `message_id`.

## 6. Registry host setup

### NixOS module

Add the registry flake/module to the host that should run the rendezvous service:

```nix
{
  inputs.broccoli-comms.url = "github:<owner>/broccoli-comms";

  outputs = { self, nixpkgs, broccoli-comms, ... }: {
    nixosConfigurations.registry-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        broccoli-comms.nixosModules.agent-registry # if exposed by your wrapper flake
        # or import the standalone agent-registry flake/module directly
      ];
    };
  };
}
```

If using the standalone registry slice directly:

```nix
{
  inputs.agent-registry.url = "path:/path/to/broccoli-comms/agent-registry";

  outputs = { self, nixpkgs, agent-registry, ... }: {
    nixosConfigurations.registry-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        agent-registry.nixosModules.default
        ({ ... }: {
          services.agent-registry = {
            enable = true;
            port = 8080;
            auth = true;
            tokenFile = "/run/secrets/agent-registry-token";
            staleSeconds = 60;
            goneSeconds = 180;
          };
        })
      ];
    };
  };
}
```

Create a shared token on the registry host:

```sh
sudo install -d -m 0700 /run/secrets
umask 077
openssl rand -base64 32 | sudo tee /run/secrets/agent-registry-token >/dev/null
```

For local/dev-only testing, you may disable auth:

```nix
services.agent-registry = {
  enable = true;
  port = 8080;
  auth = false;
};
```

Check the registry:

```sh
curl http://registry-host:8080/healthz
curl -H "Authorization: Bearer $(cat token-file)" http://registry-host:8080/agents
```

## 7. Tracker/client machine setup

Each machine that should publish local agents or receive cross-device messages needs `agent-tracker` registry integration.

Home Manager-style options from the tracker module:

```nix
services.agent-tracker = {
  enable = true;
  httpPort = 19876;

  registries = [
    { name = "home"; url = "https://registry.example.com"; }
  ];

  registryAuth = true;
  registryTokenFile = "/home/your-user/.config/agent-tracker/registry-token";
  registryHeartbeatSeconds = 30;
};
```

The tracker usually runs as the user, so `registryTokenFile` must be readable by that user:

```sh
mkdir -p ~/.config/agent-tracker
umask 077
printf '%s' '<same-shared-token>' > ~/.config/agent-tracker/registry-token
```

For local/dev testing against an unauthenticated registry:

```nix
services.agent-tracker = {
  enable = true;
  registries = [
    { name = "dev"; url = "http://127.0.0.1:8080"; }
  ];
  registryAuth = false;
};
```

Verify from a tracker machine:

```sh
agent-tracker-ctl registry-status
agent-tracker-ctl list
agent-tracker-ctl send-message other-host/agent-name "hello from this host"
```

## 8. Managed agents on a registry host

The registry NixOS/Home Manager modules can also keep local agents running in tmux. This is optional and separate from registry discovery.

Example NixOS managed agent:

```nix
services.agent-registry = {
  enable = true;
  auth = false;

  managedAgents.reviewer = {
    user = "tanmay";
    session = "broccoli-review";
    cwd = "/home/tanmay/project";
    command = "pi";
    wrapperPath = "agent-wrapper";
    reconcileIntervalSeconds = 30;

    restart = {
      enable = true;
      intervalSeconds = 86400;
      warningLeadTimeSeconds = 300;
      warningMessage = "Restarting in 5 minutes";
    };
  };
};
```

Important: `managedAgents` only starts/reconciles local tmux agents. To publish those agents to a multi-device registry, the same machine/user must also run `agent-tracker` with registry integration enabled.

By default, managed agents use the target user's normal tmux socket under `/run/user/<uid>/tmux-<uid>/default`. The helper defensively ignores invalid inherited runtime dirs such as bare `/run/user`; set `tmuxSocketPath` explicitly if you need a different socket.

## 9. Testing with `~/projects/nix/test-vm`

The reusable test VM provides SSH on `127.0.0.1:2222` with user/password `dev`/`dev`.

Start the VM:

```sh
cd ~/projects/nix/test-vm
nohup nix run .#devvm >/tmp/test-vm-devvm.log 2>&1 &
tail -f /tmp/test-vm-devvm.log
```

Wait for SSH:

```sh
ss -ltn '( sport = :2222 )'
```

Create a temporary test flake that imports the registry module and the test-vm base module:

```sh
mkdir -p /tmp/broccoli-registry-test
cat > /tmp/broccoli-registry-test/flake.nix <<'EOF'
{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.test-vm.url = "path:/home/tanmay/projects/nix/test-vm";
  inputs.agent-registry.url = "path:/home/tanmay/projects/nix/broccoli-comms/agent-registry";

  outputs = { nixpkgs, test-vm, agent-registry, ... }: {
    nixosConfigurations.registry-test = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        "${test-vm}/devvm.nix"
        agent-registry.nixosModules.default
        ({ pkgs, ... }: {
          services.agent-registry = {
            enable = true;
            auth = false;
            port = 8080;
            managedAgents.smoke = {
              user = "dev";
              session = "registry-smoke";
              cwd = "/home/dev";
              command = "sleep 300";
              wrapperPath = "env";
              reconcileIntervalSeconds = 30;
            };
          };
          environment.systemPackages = [ agent-registry.packages.x86_64-linux.default pkgs.curl pkgs.jq pkgs.tmux pkgs.coreutils ];
        })
      ];
    };
  };
}
EOF
```

Build and push the config to the VM:

```sh
out=$(nix build path:/tmp/broccoli-registry-test#nixosConfigurations.registry-test.config.system.build.toplevel --no-link --print-out-paths)
NIX_SSHOPTS='-p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null' \
  nix copy --no-check-sigs --to ssh-ng://dev@127.0.0.1 "$out"
ssh -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null dev@127.0.0.1 \
  sudo "$out/bin/switch-to-configuration" test
```

Check registry health and managed-agent reconciliation inside the VM:

```sh
ssh -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null dev@127.0.0.1 \
  'curl -fsS http://127.0.0.1:8080/healthz && systemctl status agent-registry --no-pager && tmux -S /run/user/1000/tmux-1000/default list-panes -a -F "#S #{pane_id} #{@agent_name}"'
```

Expected results:

- `/healthz` returns `{"ok": true}`
- `agent-registry.service` is active
- tmux has a `registry-smoke` pane tagged with `@agent_name=smoke`

## 10. Current future work

These are intentionally not required for the basic setup above:

- decide whether `agent-registry` remains bundled by default or optional in Broccoli Comms
- expose Broccoli Comms top-level NixOS/Home Manager modules for registry setup, instead of using the nested standalone registry flake directly
- add remote pane capture and send-keys/send-text through registry with capability-gated auth
- add a generic permission request model for approve/deny prompts across Pi/Claude/Codex/Gemini
- add deeper `doctor` checks for registry config/secrets and agent command versions
