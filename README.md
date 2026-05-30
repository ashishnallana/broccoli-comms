# Broccoli Comms

Broccoli Comms is a standalone agent workspace runtime. It runs terminal-based coding agents, tracks their panes/inboxes, and provides a terminal UI for messaging and control without depending on a user's Home Manager setup, shell hooks, or global agent-tracker service.

## What it is

`broccoli-comms` owns an isolated runtime containing:

- managed agent panes and the TUI in your default tmux server/session by default
- a private `agent-tracker` daemon/socket for registration, inboxes, pane capture, and local direct input
- managed agent windows launched through `agent-wrapper`
- the `agent-communicator` TUI as the primary interface
- optional `agent-registry` connectivity for multi-device discovery and queued cross-machine messages

Typical local workflow:

```sh
broccoli-comms start       # start private tracker plus default-tmux Broccoli session
broccoli-comms ui          # open the terminal UI; alias: open
broccoli-comms status      # inspect runtime state
broccoli-comms stop        # stop Broccoli session and private tracker
```

Default paths/mode:

- runtime: `$XDG_RUNTIME_DIR/broccoli-comms`
- tracker socket: `$XDG_RUNTIME_DIR/broccoli-comms/agent-tracker.sock`
- tmux mode: `default` (uses your normal tmux server and a `broccoli-comms` session)
- private tmux compatibility: set `BROCCOLI_COMMS_TMUX_MODE=private` to use `$XDG_RUNTIME_DIR/broccoli-comms/tmux.sock`
- config: `$XDG_CONFIG_HOME/broccoli-comms/config.json`
- logs/cache: `$XDG_CACHE_HOME/broccoli-comms`

## Install and quick start

### Nix machine

Required on the host:

- Nix with flakes enabled
- `git` if you want to clone a checkout locally
- the agent commands you want to run on `PATH`, for example `pi`, `claude`, or `codex`

The Nix package supplies Broccoli Comms' own runtime tools, including Python, tmux, the Go-built TUI, `agent-tracker`, `agent-wrapper`, and `agent-registry`.

Run directly from a checkout:

```sh
git clone https://github.com/tanmayv/broccoli-comms.git
cd broccoli-comms
nix run .#broccoli-comms -- doctor
nix run .#broccoli-comms -- start
nix run .#broccoli-comms -- ui
```

Run directly from GitHub:

```sh
nix run github:tanmayv/broccoli-comms#broccoli-comms -- doctor
nix run github:tanmayv/broccoli-comms#broccoli-comms -- ui
```

Install persistently with Nix:

```sh
nix profile install github:tanmayv/broccoli-comms#broccoli-comms
broccoli-comms doctor
broccoli-comms start
broccoli-comms ui
```

### Non-Nix machine

A non-Nix install builds the TUI from source and uses system dependencies.

Required on the host:

- `git` to clone this repository
- `make` to run the build/install targets
- `go` to build `agent-communicator`
- `python3` to run `broccoli-comms`, `agent-tracker`, and `agent-registry`
- `tmux` for the agent/UI session runtime
- a POSIX shell; `bash` is needed for the smoke-test scripts
- the agent commands you want to run on `PATH`, for example `pi`, `claude`, or `codex`

No third-party Python packages are required for the core launcher/tracker/registry path; they use the Python standard library.

Build and run:

```sh
git clone https://github.com/tanmayv/broccoli-comms.git
cd broccoli-comms
make build
./bin/broccoli-comms doctor
./bin/broccoli-comms start
./bin/broccoli-comms ui
```

Optional: put the checkout's `./bin` directory on `PATH`, or symlink `bin/broccoli-comms` into a directory on `PATH`. Prefer a symlink over copying so the launcher can still find the rest of the source checkout.

## Build from source

From a source checkout you can build either with Nix or with the repository `Makefile`.

Nix build:

```sh
git clone https://github.com/tanmayv/broccoli-comms.git
cd broccoli-comms
nix build .#broccoli-comms
./result/bin/broccoli-comms doctor
```

Non-Nix build:

```sh
git clone https://github.com/tanmayv/broccoli-comms.git
cd broccoli-comms
make build
./bin/broccoli-comms doctor
```

The non-Nix build is source-checkout based: keep the checkout in place and run `./bin/broccoli-comms`, add the checkout's `bin/` directory to `PATH`, or symlink `bin/broccoli-comms` into a directory on `PATH`. Do not copy only the launcher by itself; it needs the repository's `agent-tracker/`, `agent-registry/`, and wrapper files.

The non-Nix build creates these local executables:

- `bin/broccoli-comms`
- `bin/agent-communicator`
- `bin/agent-wrapper`
- `bin/agent-tracker`
- `bin/agent-tracker-ctl`

Useful source checks:

```sh
make check
nix flake check
```

## Common commands

```sh
broccoli-comms doctor
broccoli-comms start
broccoli-comms ui             # alias: open
broccoli-comms status --json
broccoli-comms attach
broccoli-comms agent list --json
broccoli-comms agent focus main
broccoli-comms agent-tracker list
broccoli-comms registry start --host 127.0.0.1 --port 8080 --name local --noauth
broccoli-comms registry status
broccoli-comms stop
```

Exposed Nix packages:

- `broccoliComms` / `default`
- `agent-tracker`
- `agent-tracker-ctl`
- `agent-wrapper`
- `agent-communicator`
- `agent-registry`
- `agent-registry-managed-agent`

## Usage modes

### 1. Local-only, no registry

This is the simplest mode. Agents on the same machine communicate through the private local tracker only. No central registry is needed.

```sh
broccoli-comms start
broccoli-comms ui
```

Use this when all agents you care about are running under the same Broccoli Comms runtime.

### 2. Use an existing central registry

A central `agent-registry` is required for multi-device communication. Each machine runs its own local `broccoli-comms`/`agent-tracker`, and all trackers publish to and poll the same registry for discovery and queued messages.

Configure an existing registry URL, then restart/start Broccoli Comms so the private tracker receives it:

```sh
broccoli-comms registry add --name home --url https://registry.example.com --auth --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms registry list
broccoli-comms registry env
broccoli-comms start
broccoli-comms ui
broccoli-comms agent-tracker registry-status
```

For an unauthenticated local/dev registry:

```sh
broccoli-comms registry add --name local --url http://127.0.0.1:8080 --noauth
broccoli-comms start
```

Saved registry URLs live in `$BROCCOLI_COMMS_CONFIG_DIR/registries.json` (default `~/.config/broccoli-comms/registries.json`). Token contents are not stored; use `token-file`. If `AGENT_REGISTRIES_JSON` is explicitly set in the environment, it overrides saved registry URLs for that invocation.

### 3. Run a standalone registry with Broccoli Comms

One machine can host the central registry service, while every participating machine points its tracker at that registry URL.

```sh
# On the registry host:
broccoli-comms registry start --host 0.0.0.0 --port 8080 --name home --auth --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms registry status

# On each client machine:
broccoli-comms registry add --name home --url http://REGISTRY_HOST:8080 --auth --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms start
broccoli-comms agent-tracker registry-status
```

For loopback-only local testing, the registry can be started without auth:

```sh
broccoli-comms registry start --host 127.0.0.1 --port 8080 --name local --noauth
```

`--noauth` is only safe for loopback/local development. Registry startup does not enable remote direct pane input; remote direct input has separate security gates and remains disabled unless explicitly configured.

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

`start` reconciles configured agents into the `broccoli-comms` tmux session, avoids duplicate windows on repeated starts, and launches each agent through `agent-wrapper` with the private tracker environment. By default this session is created in your normal tmux server. `broccoli-comms stop` kills only the `broccoli-comms` session and private tracker, not unrelated tmux sessions. Set `BROCCOLI_COMMS_TMUX_MODE=private` on `start/ui/stop` to use the old Broccoli-owned private tmux socket behavior.

### Track an ad-hoc command in the current pane

Use `broccoli-comms track` when you want to run a command yourself in the current terminal/tmux pane but still have it register with Agent Communicator:

```sh
broccoli-comms track --name my-agent -- my-agent
broccoli-comms track --name repo-coder --cwd ~/repo -- pi
broccoli-comms track -- /opt/agents/my-agent --flag value
```

`track` starts the private tracker if needed, resolves Broccoli's bundled `agent-wrapper`, and then `exec`s it in the current terminal. `agent-wrapper` does not need to be on `PATH`. The command you run, such as `my-agent` or `pi`, must still be on `PATH` unless you pass an absolute path. If `--name` is omitted, the command basename is used as the suggested Agent Communicator name.

### Agent-tracker saved agent templates

Broccoli Comms managed agents live in `$XDG_CONFIG_HOME/broccoli-comms/config.json` and are controlled with `broccoli-comms agent ...`. The lower-level agent tracker also supports saved agent templates under:

```text
~/.config/agent-tracker/agents/<template-name>/config.json
```

These templates are useful for tracker/registry workflows that need a named saved agent configuration. Each template contains the working directory, agent command, optional command arguments, and a human-readable description.

Example: create a `broccoli-comms` Pi-agent template for this repository:

```sh
mkdir -p ~/.config/agent-tracker/agents/broccoli-comms
cat > ~/.config/agent-tracker/agents/broccoli-comms/config.json <<'JSON'
{
  "directory": "/home/tanmay/projects/nix/broccoli-comms",
  "agent-command": "pi",
  "agent-args": [],
  "description": "Pi agent for the broccoli-comms repository"
}
JSON
```

Generic template shape:

```json
{
  "directory": "/absolute/path/to/project",
  "agent-command": "pi",
  "agent-args": [],
  "description": "Friendly description shown to humans"
}
```

For command arguments, split them into `agent-args` instead of appending them to `agent-command`:

```json
{
  "directory": "/home/user/project",
  "agent-command": "pi",
  "agent-args": ["--model", "gemini-2.5-pro"],
  "description": "Pi agent for /home/user/project"
}
```

To verify saved templates:

```sh
find ~/.config/agent-tracker/agents -maxdepth 2 -name config.json -print
python3 -m json.tool ~/.config/agent-tracker/agents/broccoli-comms/config.json
```

`open` / `ui` launches `agent-communicator` as a wrapped frontend in the `broccoli-comms` tmux session and attaches or switches to it. From inside an existing default-tmux client, `ui` uses `tmux switch-client` instead of attempting a nested attach. Wrapping lets the communicator register as `agent-communicator`, so its inbox/status views use the private tracker. The TUI shows a Broccoli Comms runtime/tracker status line when launched in this app mode, including RPC health, active target/model/machine, local/remote online counts, registry state, and current time.

Agent Communicator key highlights:

- `F1` `/msg inbox`: normal inbox message mode; `Enter` sends to the selected conversation.
- `F2` `/text pane`: explicit direct text mode; `Enter` sends composer text to the selected pane through the existing direct-input backend.
- `F3` `/key pane`: explicit direct key mode; `Enter` sends whitespace-separated key tokens.
- `F4` `/broadcast`: visible but disabled; pressing `Enter` does not send.
- `n` jumps to the next unread conversation; `Ctrl-N` / `Ctrl-P` keep next/previous agent navigation.

Legacy slash commands (`/msg`, `/text`, `/text --no-submit`, `/key`) remain supported. The composer context line shows the selected target plus model badge and machine where known.

`agent focus <name>` selects a running managed-agent window by tmux metadata/window id, and `agent attach <name>` attaches or switches directly to that managed window.

`broccoli-comms agent-tracker spin <dir> <command> [args...]` also auto-wraps raw commands through `agent-wrapper` before creating the tmux window/session, so spun agents register, heartbeat, inherit the intended private tracker environment and tmux pane metadata, and appear in status/communicator views. Commands already starting with `agent-wrapper` are not wrapped again.

`broccoli-comms agent-tracker <subcommand> [args...]` runs the in-repo `agent-tracker-ctl` against the Broccoli Comms private tracker and active tmux mode. This is the preferred wrapper for source-checkout usage because it does not require a globally installed `agent-tracker-ctl` on `PATH` and keeps commands pinned to the app-owned tracker runtime.

```sh
broccoli-comms agent-tracker --help
broccoli-comms agent-tracker list
broccoli-comms agent-tracker read-inbox --last 10
broccoli-comms agent-tracker registry-status
broccoli-comms agent-tracker capture-pane agent-communicator --last 80
```

For explicit pane control, `broccoli-comms agent-tracker send-text TARGET TEXT`, `broccoli-comms agent-tracker send-text --no-submit TARGET TEXT`, and `broccoli-comms agent-tracker send-key TARGET KEY [KEY...]` call the tracker `send_input` backend directly. These bypass inbox messages. Local bare names/UUIDs use the registered tmux pane/socket metadata; remote `host/agent` targets are registry-routed only when explicitly enabled on sender, registry, and receiver (`BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED=1` or the narrower send/receive/registry env gates). Remote direct input is disabled by default and should be treated as dangerous pane control.

```sh
broccoli-comms agent-tracker send-text alice "hello"
broccoli-comms agent-tracker send-text --no-submit alice "draft without enter"
broccoli-comms agent-tracker send-key alice C-c Enter
# Remote examples require explicit remote pane-input gates on both trackers and the registry:
broccoli-comms agent-tracker send-text host-a/alice "hello remotely"
broccoli-comms agent-tracker send-key registry-a:host-a/alice Escape
```

Remote-origin inbox delivery can optionally focus the destination pane when `BROCCOLI_COMMS_FOCUS_REMOTE_MESSAGES=1` is set. This is disabled by default; when enabled, the tracker uses only registered tmux pane/socket metadata and treats focus as best-effort so message delivery still succeeds if focus fails.

## Local registry management

`broccoli-comms registry ...` can run the in-repo `agent-registry` rendezvous service under Broccoli Comms runtime/cache/config paths:

```sh
# Local development registry, loopback only, no auth.
broccoli-comms registry start --host 127.0.0.1 --port 8080 --name local --noauth
broccoli-comms registry health
broccoli-comms registry agents --json
broccoli-comms registry status --json
broccoli-comms registry stop

# Authenticated LAN/public bind. Prefer token files over shell-history tokens.
broccoli-comms registry start --host 0.0.0.0 --port 8080 --name home --auth --token-file ~/.config/broccoli-comms/registry-token
```

Unauthenticated non-loopback binds are refused for safety. Starting a registry does not automatically point a tracker at it; use `broccoli-comms registry add --name local --url http://127.0.0.1:8080 --noauth` (or `--auth --token-file ...`) when you want the private tracker to publish/consume that registry URL after restart. Use `registry list/remove/enable/disable/env` to manage saved URLs. Registry URL configuration does not enable remote direct pane input; the separate remote pane-input gates remain required.

## Start on boot/login

You can start the Broccoli Comms tracker/managed agents and a Broccoli-managed registry automatically with your OS service manager.

Use full paths in service files because boot/login services often have a minimal `PATH`:

```sh
command -v broccoli-comms
```

Also make sure any agent commands in your config, such as `pi`, `claude`, or `codex`, are either on the service `PATH` or written as absolute paths in `broccoli-comms agent add --command ...`.

### Linux systemd user services

This example uses user services, so it starts when the user session starts. Enable lingering if you want user services to start at boot before interactive login:

```sh
loginctl enable-linger "$USER"
```

Create `~/.config/systemd/user/broccoli-comms.service` for the private tracker and managed agents:

```ini
[Unit]
Description=Broccoli Comms private tracker and managed agents
After=default.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=%h/.nix-profile/bin/broccoli-comms start
ExecStop=%h/.nix-profile/bin/broccoli-comms stop
Environment=PATH=%h/.nix-profile/bin:/run/current-system/sw/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
```

Create `~/.config/systemd/user/broccoli-comms-registry.service` if this machine should also host a central registry:

```ini
[Unit]
Description=Broccoli Comms agent registry
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.nix-profile/bin/broccoli-comms registry start --foreground --host 0.0.0.0 --port 8080 --name home --auth --token-file %h/.config/broccoli-comms/registry-token
Restart=on-failure
Environment=PATH=%h/.nix-profile/bin:/run/current-system/sw/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
```

Enable and start:

```sh
systemctl --user daemon-reload
systemctl --user enable --now broccoli-comms.service
systemctl --user enable --now broccoli-comms-registry.service
systemctl --user status broccoli-comms.service
systemctl --user status broccoli-comms-registry.service
```

If you do not want this machine to host a registry, omit `broccoli-comms-registry.service`. Client machines only need `broccoli-comms registry add ...` plus `broccoli-comms start`.

### macOS LaunchAgent

A LaunchAgent starts when the user logs in. This is usually safer than a system LaunchDaemon because Broccoli Comms is a user-level tmux/tracker runtime and needs access to the user's home directory and agent commands.

First choose a stable runtime directory. macOS does not always provide `XDG_RUNTIME_DIR`, so this example uses `/tmp/broccoli-comms-$USER`.

Create `~/Library/LaunchAgents/in.broccoli.comms.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>in.broccoli.comms</string>

  <key>RunAtLoad</key>
  <true/>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/.nix-profile/bin/broccoli-comms</string>
    <string>start</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>BROCCOLI_COMMS_RUNTIME_DIR</key>
    <string>/tmp/broccoli-comms-YOU</string>
    <key>PATH</key>
    <string>/Users/YOU/.nix-profile/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>StandardOutPath</key>
  <string>/tmp/broccoli-comms.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/broccoli-comms.err.log</string>
</dict>
</plist>
```

Create `~/Library/LaunchAgents/in.broccoli.comms.registry.plist` if this Mac should host a registry:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>in.broccoli.comms.registry</string>

  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/.nix-profile/bin/broccoli-comms</string>
    <string>registry</string>
    <string>start</string>
    <string>--foreground</string>
    <string>--host</string>
    <string>0.0.0.0</string>
    <string>--port</string>
    <string>8080</string>
    <string>--name</string>
    <string>home</string>
    <string>--auth</string>
    <string>--token-file</string>
    <string>/Users/YOU/.config/broccoli-comms/registry-token</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>BROCCOLI_COMMS_RUNTIME_DIR</key>
    <string>/tmp/broccoli-comms-YOU</string>
    <key>PATH</key>
    <string>/Users/YOU/.nix-profile/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>StandardOutPath</key>
  <string>/tmp/broccoli-comms-registry.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/broccoli-comms-registry.err.log</string>
</dict>
</plist>
```

Replace `YOU` and the `broccoli-comms` path with your actual username/path. Then load the services:

```sh
launchctl unload ~/Library/LaunchAgents/in.broccoli.comms.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/in.broccoli.comms.plist
launchctl start in.broccoli.comms

launchctl unload ~/Library/LaunchAgents/in.broccoli.comms.registry.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/in.broccoli.comms.registry.plist
launchctl start in.broccoli.comms.registry
```

Check logs and status:

```sh
tail -f /tmp/broccoli-comms.err.log
broccoli-comms status --json
broccoli-comms registry status --json
```

Runtime/frontend JSON contracts are documented in `docs/RUNTIME_API.md`:

```sh
broccoli-comms status --json
broccoli-comms agent list --json
```

For complete install, dependency, and multi-device registry setup instructions, see `docs/SETUP_AND_MULTI_DEVICE.md`.

## Smoke test

Run the Nix/package checks and private runtime lifecycle smoke tests with isolated temp runtime/cache/config directories:

```sh
nix flake check
bash scripts/smoke-private-runtime.sh
bash scripts/smoke-managed-agents.sh
# or
make smoke-private-runtime
make smoke-managed-agents
```

The runtime test starts `broccoli-comms`, verifies the private tracker and active tmux mode/session, checks status JSON, stops the runtime, and verifies cleanup. The managed-agent test adds a harmless `sleep 60` configured agent, verifies reconciliation/no duplicates/restart/remove, and cleans up isolated temp state.

## Source copied from home-manager-core

Initial copied slices:

- `agent-tracker/` from `modules/agent-tracker/`
- `agent-communicator-tui/`
- `agent-registry/`
- `wrapper/agent-wrapper.sh` extracted as standalone wrapper source
- `app/broccoli-comms.py` new private-runtime launcher

See `docs/MIGRATION_PLAN.md` for the migration plan.
