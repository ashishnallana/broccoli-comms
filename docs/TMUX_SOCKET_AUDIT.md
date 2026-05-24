# Tmux Socket Audit

Chunk 2 audit for app-private tmux/socket consistency.

## Scope audited

Command used:

```sh
rg 'subprocess\.|\btmux\b|TMUX|TMUX_PANE|tmux_socket|AGENT_TRACKER_TMUX_SOCKET|BROCCOLI_COMMS_TMUX_SOCKET' agent-tracker wrapper app
```

Files reviewed:

- `app/broccoli-comms.py`
- `wrapper/agent-wrapper.sh`
- `agent-tracker/tmux_util.py`
- `agent-tracker/tmux_reliability.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/state.py`
- `agent-tracker/registry_client.py`
- `agent-tracker/ctl_commands/*.py`

## Safe patterns

- App runtime commands use `tmux -S "$BROCCOLI_COMMS_RUNTIME_DIR/tmux.sock"` via `app/broccoli-comms.py::tmux()`.
- `base_env()` exports both:
  - `BROCCOLI_COMMS_TMUX_SOCKET`
  - `AGENT_TRACKER_TMUX_SOCKET`
- App runtime env strips inherited `TMUX` and `TMUX_PANE` before launching tracker, tmux commands, TUI, and attach.
- Tracker tmux helpers use shared command builders that prefer per-agent socket, then private socket env, then legacy/default tmux only when no app/private socket exists.
- Command builders avoid double-prefixing explicit `-S`/`-L` tmux arguments.
- CLI tmux helpers strip inherited `TMUX`/`TMUX_PANE` when a private/explicit socket is used, while preserving legacy behavior when no socket is configured.
- `agent-wrapper` now builds a single explicit `tmux_cmd` from `AGENT_TRACKER_TMUX_SOCKET`, `BROCCOLI_COMMS_TMUX_SOCKET`, or the pane's `TMUX` socket, and uses it for all tmux metadata/cwd operations.

## Findings and fixes

### Already safe

- `app/broccoli-comms.py`: lifecycle/status/attach commands already used the private `-S` socket. Chunk 1 also made `BROCCOLI_COMMS_RUNTIME_DIR` exact and stripped inherited tmux env.
- `agent-tracker/rpc_handler.py`: registration/rename/send/capture paths route tmux operations through `tmux_util` and stored per-agent `tmux_socket`. Rename no longer calls the Home Manager `tmux-status-refresh` helper from standalone runtime code.
- `agent-tracker/monitor.py`: notification delivery uses `tmux_util` with stored per-agent sockets.

### Fixed in Chunk 2

- `agent-tracker/tmux_reliability.py`: raw `tmux` construction now uses private socket env by default and strips inherited tmux env when private/explicit sockets are used.
- `agent-tracker/ctl_commands/common.py`: added shared CLI `tmux_command()` / `tmux_env()` helpers and used them for current-pane detection and daemon startup env.
- `agent-tracker/ctl_commands/focus.py`: focus/next/prev tmux calls now use shared helpers and explicit/private sockets.
- `agent-tracker/ctl_commands/save.py`: tmux option/path queries now use shared helpers and accept an optional socket.
- `agent-tracker/registry_client.py`: remote save fallback now passes the agent's stored tmux socket into save helpers.
- `agent-tracker/tmux_util.py`: command execution now strips inherited tmux env when using default private or explicit sockets; `get_pane_info()` accepts an optional socket.
- `agent-tracker/rpc_handler.py`: capture session lookup now passes the resolved tmux socket into `get_pane_info()`.
- `agent-tracker/rpc_handler.py`: removed the rename-time `tmux-status-refresh` subprocess call because it can target/mutate the user's default tmux server and does not belong in the standalone runtime boundary.
- `wrapper/agent-wrapper.sh`: all tmux metadata and heartbeat cwd queries use explicit `tmux -S` command construction.

## Remaining risks / follow-ups

- Some copied tests intentionally create/use default tmux sessions; they are test-only and not app runtime paths.
- The standalone wrapper still depends on `TMUX`/`TMUX_PANE` being set by the private tmux pane to know which pane it is wrapping. It now uses explicit socket command construction after that point.
- Future managed-agent/UI work should continue to pass socket paths through APIs rather than relying on ambient tmux context.
