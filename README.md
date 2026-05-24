# Broccoli Comms

Standalone agent communication runtime extracted from `home-manager-core`.

The goal is to run an agent workspace without depending on the user's Home Manager, tmux config, shell hooks, or existing tmux sessions.

## Intended runtime model

`broccoli-comms` owns:

- a private tmux server/socket
- a private `agent-tracker` daemon/socket
- managed agent panes/windows launched through `agent-wrapper`
- the `agent-communicator` TUI as the primary UI

Default private paths:

- runtime: `$XDG_RUNTIME_DIR/broccoli-comms`
- tracker socket: `$XDG_RUNTIME_DIR/broccoli-comms/agent-tracker.sock`
- tmux socket: `$XDG_RUNTIME_DIR/broccoli-comms/tmux.sock`
- config: `$XDG_CONFIG_HOME/broccoli-comms/config.json`
- logs/cache: `$XDG_CACHE_HOME/broccoli-comms`

## New-machine bootstrap

Recommended Nix path from a checkout:

```sh
nix run .#broccoli-comms -- doctor
nix run .#broccoli-comms -- start
nix run .#broccoli-comms -- open
```

For a persistent install from a checkout:

```sh
nix profile install .#broccoli-comms
broccoli-comms doctor --json
broccoli-comms start
broccoli-comms open
```

Nix packages include the runtime dependencies they launch, including `tmux`. Manual/non-Nix installs must provide `python3`, `tmux`, and configured agent commands (for example `pi`, `claude`, or `codex`) on `PATH`.

## Nix usage

```sh
nix run .#broccoli-comms -- doctor
nix run .#broccoli-comms
nix run .#broccoli-comms -- status --json
nix run .#broccoli-comms -- attach
nix run .#broccoli-comms -- agent focus main
nix run .#broccoli-comms -- stop
```

Exposed packages:

- `broccoliComms` / `default`
- `agent-tracker`
- `agent-tracker-ctl`
- `agent-wrapper`
- `agent-communicator`
- `agent-registry`
- `agent-registry-managed-agent`

## Standalone non-Nix usage

Requires `python3`, `go`, and system `tmux` on `PATH` for building/running, plus any configured agent commands on `PATH`.

```sh
make build
./bin/broccoli-comms doctor --json
./bin/broccoli-comms doctor
./bin/broccoli-comms start
./bin/broccoli-comms attach
./bin/broccoli-comms stop
```

## Configured agents

Edit `$XDG_CONFIG_HOME/broccoli-comms/config.json`:

```json
{
  "agents": {
    "main": {
      "cwd": "/home/user/project",
      "command": "pi"
    },
    "reviewer": {
      "cwd": "/home/user/project",
      "command": "pi --role reviewer"
    }
  }
}
```

Or manage the same config through the CLI:

```sh
broccoli-comms agent list --json
broccoli-comms agent add main --cwd /home/user/project --command 'pi'
broccoli-comms agent add reviewer --cwd /home/user/project --command 'pi --role reviewer'
broccoli-comms agent focus main
broccoli-comms agent attach main
broccoli-comms agent restart main
broccoli-comms agent remove reviewer
```

Then run:

```sh
broccoli-comms start
broccoli-comms attach
```

`start` reconciles configured agents into private tmux windows, avoids duplicate windows on repeated starts, and launches each agent through `agent-wrapper` with the private tracker/tmux socket environment.

`open` / `ui` launches `agent-communicator` as the Broccoli Comms frontend with `AGENT_TRACKER_SOCKET` and private tmux socket variables set to the app-owned runtime. The TUI shows a small Broccoli Comms runtime/tracker status line when launched in this app mode.

`agent focus <name>` selects a running managed-agent window by private tmux metadata/window id, and `agent attach <name>` attaches directly to that managed window.

`agent-tracker-ctl spin <dir> <command> [args...]` also auto-wraps raw commands through `agent-wrapper` before creating the tmux window/session, so spun agents register, heartbeat, inherit the intended tracker/tmux socket environment, and appear in status/communicator views. Commands already starting with `agent-wrapper` are not wrapped again.

Runtime/frontend JSON contracts are documented in `docs/RUNTIME_API.md`:

```sh
broccoli-comms status --json
broccoli-comms agent list --json
```

## Smoke test

Run the private runtime lifecycle smoke test with isolated temp runtime/cache/config directories:

```sh
bash scripts/smoke-private-runtime.sh
bash scripts/smoke-managed-agents.sh
# or
make smoke-private-runtime
make smoke-managed-agents
```

The runtime test starts `broccoli-comms`, verifies the private tracker and tmux sockets/session, checks status JSON, stops the runtime, and verifies cleanup. The managed-agent test adds a harmless `sleep 60` configured agent, verifies reconciliation/no duplicates/restart/remove, and cleans up isolated temp state.

## Source copied from home-manager-core

Initial copied slices:

- `agent-tracker/` from `modules/agent-tracker/`
- `agent-communicator-tui/`
- `agent-registry/`
- `wrapper/agent-wrapper.sh` extracted as standalone wrapper source
- `app/broccoli-comms.py` new private-runtime launcher

See `docs/MIGRATION_PLAN.md` for the migration plan.
