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

## Nix usage

```sh
nix run .#broccoli-comms
nix run .#broccoli-comms -- status
nix run .#broccoli-comms -- attach
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

Requires `python3`, `go`, and `tmux` on `PATH`.

```sh
make build
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

Then run:

```sh
broccoli-comms start
broccoli-comms attach
```

## Smoke test

Run the private runtime lifecycle smoke test with isolated temp runtime/cache/config directories:

```sh
bash scripts/smoke-private-runtime.sh
# or
make smoke-private-runtime
```

The test starts `broccoli-comms`, verifies the private tracker and tmux sockets/session, checks status JSON, stops the runtime, and verifies cleanup.

## Source copied from home-manager-core

Initial copied slices:

- `agent-tracker/` from `modules/agent-tracker/`
- `agent-communicator-tui/`
- `agent-registry/`
- `wrapper/agent-wrapper.sh` extracted as standalone wrapper source
- `app/broccoli-comms.py` new private-runtime launcher

See `docs/MIGRATION_PLAN.md` for the migration plan.
