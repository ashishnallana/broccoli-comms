# Broccoli Comms `registry` command implementation plan

## Goal

Add first-class `broccoli-comms registry ...` commands so users can run and manage an `agent-registry` rendezvous service from the Broccoli Comms CLI without invoking `nix run .#agent-registry` or manually setting environment variables.

Desired examples:

```sh
broccoli-comms registry start --host 127.0.0.1 --port 8080 --name local --noauth
broccoli-comms registry start --host 0.0.0.0 --port 8080 --name home --auth --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms registry status
broccoli-comms registry stop
broccoli-comms registry agents
broccoli-comms registry health
```

A second related goal is to make it easy to point the local private tracker at registries from the same CLI. That can be part of this command or a follow-up.

## Current repo facts

Registry server code already exists:

- `agent-registry/server.py`
- package in root flake: `.#agent-registry`
- standalone flake under `agent-registry/`
- NixOS/Home Manager modules under `agent-registry/module.nix` and `agent-registry/home-manager-module.nix`

The server is configured by environment variables:

- `AGENT_REGISTRY_HOST` — bind host, default `0.0.0.0`
- `AGENT_REGISTRY_PORT` — port, default `8080`
- `AGENT_REGISTRY_AUTH` — auth enabled by default; false values: `0`, `false`, `no`
- `AGENT_REGISTRY_TOKEN` — bearer token when auth is enabled
- `AGENT_REGISTRY_STATE_PATH` — on-disk registry state
- `TRACKER_STALE_SECONDS`
- `TRACKER_GONE_SECONDS`
- optional remote pane input gates such as `AGENT_REGISTRY_REMOTE_PANE_INPUT_ENABLED`

Tracker clients publish to registries with:

- `AGENT_REGISTRIES_JSON='[{"name":"local","url":"http://127.0.0.1:8080"}]'`
- optional token or token-file fields

## Proposed CLI

### `broccoli-comms registry start`

Start a local registry process managed by the Broccoli Comms source CLI.

Options:

```text
--host HOST                  bind host, default 127.0.0.1 for CLI-managed local registry
--port PORT                  bind port, default 8080
--name NAME                  logical registry name for generated tracker config/status, default local
--auth                       require bearer auth
--noauth                     disable auth, local/dev only
--token TOKEN                token value; avoid in shell history for real deployments
--token-file PATH            file containing token
--state-path PATH            registry state path, default <cache>/agent-registry/state.json
--stale-seconds N            default 60
--gone-seconds N             default 180
--foreground                 run in foreground instead of daemonizing
--force                      replace stale pid/socket/status files if needed
```

Recommended defaults:

- `--host 127.0.0.1`
- `--port 8080`
- `--name local`
- auth default should be safe. Options:
  - default to `--auth` if binding non-loopback
  - default to `--noauth` only for loopback local dev

Suggested rule:

- If neither `--auth` nor `--noauth` is passed:
  - loopback host (`127.0.0.1`, `localhost`, `::1`) defaults to noauth
  - non-loopback (`0.0.0.0`, public/private LAN IP) requires explicit `--auth`/`--noauth`; error with safety message

Process management:

- daemon mode writes a pid file under Broccoli Comms runtime, e.g.
  - `<runtime>/agent-registry.pid`
- logs under cache, e.g.
  - `<cache>/agent-registry.log`
- state path defaults to:
  - `<cache>/agent-registry/state.json`

### `broccoli-comms registry stop`

Stop the CLI-managed registry process using pid file.

Options:

```text
--force       SIGKILL if graceful stop fails
```

### `broccoli-comms registry status`

Show configured/managed registry process state and endpoint health.

Output should include:

- name
- URL
- pid/running
- host/port
- auth mode
- state path
- health endpoint result
- agent count if reachable

Support `--json`.

### `broccoli-comms registry health`

Convenience health check:

```sh
curl-equivalent GET /healthz
```

Use configured token if needed.

### `broccoli-comms registry agents`

Convenience list:

```sh
GET /agents
```

Options:

```text
--json       raw JSON
```

### `broccoli-comms registry trackers`

Optional convenience list:

```sh
GET /trackers
```

### `broccoli-comms registry configure-tracker`

Optional but useful: write or print local tracker registry environment/config.

Possible command:

```sh
broccoli-comms registry configure-tracker --name local --url http://127.0.0.1:8080 --noauth
broccoli-comms registry configure-tracker --name home --url https://registry.example.com --token-file ~/.config/broccoli-comms/registry-token
```

Potential behaviors:

1. `--print-env`: print the needed `AGENT_REGISTRIES_JSON`.
2. `--write-env-file`: write `<config>/registries.env` for `broccoli-comms start` to load.
3. update a Broccoli Comms config JSON key such as:

```json
{
  "registries": [
    {"name": "local", "url": "http://127.0.0.1:8080"}
  ]
}
```

This is larger than simply starting a registry, so it may be implemented as a follow-up if needed.

## Implementation design

Update `app/broccoli-comms.py`.

### Paths

Add paths:

```py
"registry_pid": runtime / "agent-registry.pid"
"registry_log": cache / "agent-registry.log"
"registry_state": cache / "agent-registry" / "state.json"
"registry_config": config / "registry.json"   # optional persisted CLI-managed registry config
```

### Registry script resolution

Add helper:

```py
def registry_script() -> str:
    return os.environ.get("BROCCOLI_COMMS_AGENT_REGISTRY") or str(repo_root() / "agent-registry" / "server.py")
```

Root flake should set `BROCCOLI_COMMS_AGENT_REGISTRY` for packaged `broccoli-comms`, similar to tracker/wrapper/TUI:

```sh
export BROCCOLI_COMMS_AGENT_REGISTRY=${./agent-registry/server.py}
```

or a store path containing `server.py`.

### Environment builder

Add:

```py
def registry_env(args) -> dict[str, str]:
    env = base_env()
    env.update({
        "AGENT_REGISTRY_HOST": args.host,
        "AGENT_REGISTRY_PORT": str(args.port),
        "AGENT_REGISTRY_AUTH": "true" if auth_enabled else "false",
        "AGENT_REGISTRY_STATE_PATH": str(state_path),
        "TRACKER_STALE_SECONDS": str(args.stale_seconds),
        "TRACKER_GONE_SECONDS": str(args.gone_seconds),
    })
    if token:
        env["AGENT_REGISTRY_TOKEN"] = token
    return env
```

If `--token-file` is provided, read it and set `AGENT_REGISTRY_TOKEN`. Do not print token values.

### Start

Daemon mode:

- ensure dirs
- refuse unsafe non-loopback noauth unless explicit `--noauth --i-understand` if we choose to require an extra guard
- if pid file process alive, report already running
- start `python registry_script()` with env
- write pid
- wait for `/healthz` to respond
- write `registry.json` with non-secret config:

```json
{
  "name": "local",
  "host": "127.0.0.1",
  "port": 8080,
  "auth": false,
  "token_file": null,
  "state_path": "...",
  "url": "http://127.0.0.1:8080"
}
```

Foreground mode:

- build env
- `os.execvpe(sys.executable, [sys.executable, registry_script()], env)`

### Stop

- read pid file
- SIGTERM, wait
- SIGKILL if `--force` or timeout
- delete pid file

### Status/health/agents/trackers

Use Python stdlib `urllib.request`.

Add authorization header if configured/token-file available.

For `status`, do not fail hard if HTTP check fails; show process and endpoint details.

## Interaction with `broccoli-comms start`

Initial implementation can keep `registry start` independent of `broccoli-comms start`.

However, for a complete one-command local registry + tracker setup, consider follow-up:

- `broccoli-comms start --registry local` or
- load `<config>/registries.json` in `base_env()` and set `AGENT_REGISTRIES_JSON` automatically.

For this task, it is acceptable to document that after starting a registry, tracker integration still requires starting Broccoli Comms with `AGENT_REGISTRIES_JSON` unless `configure-tracker` is implemented.

## Safety and security

- Warn/error on `--noauth` with `--host 0.0.0.0` or non-loopback unless explicitly allowed.
- Do not print token values.
- Prefer `--token-file` over `--token`.
- Document that remote direct pane input remains separately gated and is not enabled by registry start.

## Tests

Add app-level tests if a test harness exists or create one.

Test cases:

1. Parser accepts:
   - `registry start --host 127.0.0.1 --port 8080 --name local --noauth`
   - `registry stop`
   - `registry status --json`
2. Safety:
   - `registry start --host 0.0.0.0 --noauth` errors unless an explicit override is implemented.
3. Env construction:
   - correct `AGENT_REGISTRY_HOST`, `AGENT_REGISTRY_PORT`, `AGENT_REGISTRY_AUTH`, `AGENT_REGISTRY_STATE_PATH`
   - token file read without token printing
4. Smoke:

```sh
BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-registry-runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-registry-cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-registry-config \
python app/broccoli-comms.py registry start --host 127.0.0.1 --port 18080 --name local --noauth

BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-registry-runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-registry-cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-registry-config \
python app/broccoli-comms.py registry health

BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-registry-runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-registry-cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-registry-config \
python app/broccoli-comms.py registry agents

BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-registry-runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-registry-cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-registry-config \
python app/broccoli-comms.py registry stop
```

## Documentation updates

Update:

- `README.md`
- `docs/SETUP_AND_MULTI_DEVICE.md`
- possibly `docs/RUNTIME_API.md`

Document:

- Local dev registry start/stop/status
- Authenticated registry with token file
- How to point trackers at the registry with `AGENT_REGISTRIES_JSON`
- Security warning for noauth/non-loopback
- Difference between registry process and tracker registry integration

## Acceptance criteria

- `broccoli-comms registry start --host 127.0.0.1 --port <free-port> --name local --noauth` starts a registry.
- `broccoli-comms registry health` returns ok for that registry.
- `broccoli-comms registry agents` returns JSON/list without requiring curl.
- `broccoli-comms registry status --json` reports process and endpoint details.
- `broccoli-comms registry stop` stops the managed registry.
- Auth mode supports `--auth --token-file`.
- Unsafe noauth public bind is prevented or requires explicit override.
- Existing `broccoli-comms start/ui/stop/agent/agent-tracker` commands are not regressed.
