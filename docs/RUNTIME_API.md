# Broccoli Comms Runtime API

Broccoli Comms keeps runtime/control data UI-agnostic so the terminal TUI and future desktop/native frontends can consume the same JSON contracts.

Current API surface is CLI-based. Future local HTTP/RPC APIs should preserve these shapes where practical.

## Design rules

- Runtime data is JSON-friendly: objects, arrays, strings, numbers, booleans, and nulls.
- Frontends must not infer managed-agent identity from tmux window names. Managed windows are identified by tmux metadata (`@broccoli_managed_agent`) and `window_id`.
- Frontends should treat tmux IDs/pane IDs as opaque strings.
- Runtime paths and sockets are explicit. Do not depend on inherited `TMUX`/`TMUX_PANE` for app runtime operations.
- UI-specific behavior belongs in UI clients, not in tracker or launcher state contracts.
- New fields may be added; clients should ignore unknown fields.

## `broccoli-comms status --json`

Returns stable runtime health and path information.

Example:

```json
{
  "app": "broccoli-comms",
  "version": "0.1.0",
  "paths": {
    "runtime_dir": "/run/user/1000/broccoli-comms",
    "cache_dir": "/home/user/.cache/broccoli-comms",
    "config_dir": "/home/user/.config/broccoli-comms"
  },
  "tracker": {
    "socket": "/run/user/1000/broccoli-comms/agent-tracker.sock",
    "up": true
  },
  "tmux": {
    "socket": "/run/user/1000/broccoli-comms/tmux.sock",
    "up": true,
    "session": "broccoli-comms"
  },
  "config": {
    "path": "/home/user/.config/broccoli-comms/config.json"
  },
  "agents": {
    "configured_count": 1,
    "managed_running_count": 1,
    "managed_windows": [
      {
        "window_id": "@1",
        "window_name": "main",
        "managed_agent": "main",
        "pane_id": "%2",
        "cwd": "/home/user/project"
      }
    ]
  }
}
```

Compatibility aliases currently included at top level:

- `tracker_socket`
- `tracker_up`
- `tmux_socket`
- `tmux_up`

Prefer the nested `tracker` and `tmux` objects for new clients.

## `broccoli-comms agent list --json`

Returns configured agents enriched with runtime metadata and tracker registration info when available.

Example:

```json
{
  "app": "broccoli-comms",
  "version": "0.1.0",
  "config": "/home/user/.config/broccoli-comms/config.json",
  "runtime": {
    "tracker_up": true,
    "tmux_up": true,
    "tmux_session": "broccoli-comms"
  },
  "agents": {
    "main": {
      "name": "main",
      "configured": {
        "cwd": "/home/user/project",
        "command": "pi"
      },
      "cwd": "/home/user/project",
      "command": "pi",
      "running": true,
      "window_exists": true,
      "managed_windows": [
        {
          "window_id": "@1",
          "window_name": "main",
          "managed_agent": "main",
          "pane_id": "%2",
          "cwd": "/home/user/project"
        }
      ],
      "tracker": {
        "name": "main",
        "agent_id": "...",
        "tmux_pane": "%2",
        "tmux_socket": "/run/user/1000/broccoli-comms/tmux.sock",
        "status": "idle"
      }
    }
  }
}
```

Notes:

- `configured` is the config source of truth.
- `managed_windows` is derived from private tmux metadata.
- `running` is true when at least one managed window is present for the agent.
- `tracker` is best-effort and may be null if the private tracker is down or the wrapper has not registered yet.
- `cwd` and `command` remain as direct fields for simple clients; prefer `configured.cwd` and `configured.command` for new clients.

## `broccoli-comms doctor --json`

Returns readiness checks for bootstrap/install diagnostics. The top-level `ok` is false when any check has `status: "error"`; warnings are advisory.

Check objects include at least:

```json
{
  "name": "tmux",
  "status": "ok",
  "message": "tmux executable found",
  "path": "/nix/store/.../bin/tmux",
  "version": "tmux 3.6a"
}
```

Current checks cover executable availability, writable runtime/cache/config directories, configured agent command lookup where practical, and tracker/tmux socket reachability when the runtime is up.

## Related commands

Managed agent config/window commands:

```sh
broccoli-comms agent add <name> --cwd <dir> --command <cmd>
broccoli-comms agent focus <name>
broccoli-comms agent attach <name>
broccoli-comms agent remove <name>
broccoli-comms agent restart <name>
```

`focus` selects a running managed-agent window using private tmux metadata/window ids and prints a JSON-friendly result. `attach` attaches the current terminal directly to that managed window. Other commands also print JSON-friendly results.

When launched via `broccoli-comms open` / `broccoli-comms ui`, `agent-communicator` receives `AGENT_TRACKER_SOCKET`, `AGENT_TRACKER_TMUX_SOCKET`, and `BROCCOLI_COMMS_TMUX_SOCKET` for the app-owned runtime. Frontends should prefer these explicit sockets and avoid inherited/default tmux state in app mode.
