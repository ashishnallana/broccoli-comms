# Broccoli Comms default tmux socket implementation plan

## Goal

Change Broccoli Comms so the default behavior uses the user's **default tmux socket/server** instead of always creating a Broccoli-owned private tmux socket.

The private tracker should remain private by default. The change is only about where the agent/UI panes live.

Current default:

```text
tracker: private Broccoli Comms tracker socket
 tmux:   private Broccoli Comms tmux socket at $XDG_RUNTIME_DIR/broccoli-comms/tmux.sock
```

New default:

```text
tracker: private Broccoli Comms tracker socket
 tmux:   user's default tmux server/socket
```

Keep the old private-tmux behavior available as an explicit compatibility mode.

## User-facing behavior

### Default mode

```sh
broccoli-comms start
broccoli-comms ui
broccoli-comms stop
```

Should use the default tmux server. Broccoli-managed windows/session should appear in the user's normal tmux server under the `broccoli-comms` session.

`broccoli-comms stop` must stop only the Broccoli Comms session/windows and private tracker. It must **not** kill the user's entire default tmux server.

### Private tmux compatibility mode

Support an environment variable:

```sh
BROCCOLI_COMMS_TMUX_MODE=private broccoli-comms start
BROCCOLI_COMMS_TMUX_MODE=private broccoli-comms ui
BROCCOLI_COMMS_TMUX_MODE=private broccoli-comms stop
```

Private mode should preserve the old behavior:

```text
$XDG_RUNTIME_DIR/broccoli-comms/tmux.sock
```

Optionally support a CLI flag later, but the first implementation can use only the env var.

### Mode names

Use these modes:

- `default`: use default tmux server/socket; this is the new default
- `private`: use Broccoli-owned private tmux socket; old behavior

Reject unknown values with a clear error.

## Important safety requirements

1. In `default` mode, never run `tmux kill-server`.
2. In `default` mode, do not apply Broccoli's private tmux config globally to the user's default tmux server.
3. In `default` mode, do not set global tmux options such as `status off` or `mouse on` on the user's server.
4. In `default` mode, only create/kill the `broccoli-comms` session and Broccoli-managed windows.
5. Keep the private tracker socket unchanged.
6. Remote direct pane input gates must remain unchanged and disabled by default.
7. `broccoli-comms ui` must be safe when run both outside tmux and from inside an existing tmux client.
8. Running `broccoli-comms ui` from inside tmux must not cause nested attach failures, must not steal or kill unrelated sessions, and must provide a clear behavior.

## Current code areas

Primary file:

- `app/broccoli-comms.py`

Important current behaviors to update:

- `paths()["tmux_socket"]` always points at `$runtime/tmux.sock`
- `base_env()` always sets:
  - `BROCCOLI_COMMS_TMUX_SOCKET`
  - `AGENT_TRACKER_TMUX_SOCKET`
- `tmux()` always runs:
  - `tmux -S <private-socket> ...`
- `ensure_tmux()` always writes and uses private tmux config
- `stop()` calls `tmux kill-server`
- agent/UI launch commands inject private tmux socket env vars
- `ui_window_registered()` compares agent registration socket to `paths()["tmux_socket"]`
- `status`/`doctor` report/check the private tmux socket

Related files/tests likely needing updates:

- `README.md`
- `About.md`
- `docs/RUNTIME_API.md`
- `docs/SETUP_AND_MULTI_DEVICE.md`
- `scripts/smoke-private-runtime.sh`
- `agent-communicator-tui/app.go` and tests only if app-runtime detection assumes `BROCCOLI_COMMS_TMUX_SOCKET`
- Python tests/checks if present for `app/broccoli-comms.py`

## Implementation design

### 1. Add tmux mode helpers

Add helpers in `app/broccoli-comms.py`:

```py
def tmux_mode() -> str:
    mode = os.environ.get("BROCCOLI_COMMS_TMUX_MODE", "default").lower()
    if mode not in {"default", "private"}:
        raise SystemExit("BROCCOLI_COMMS_TMUX_MODE must be 'default' or 'private'")
    return mode


def use_private_tmux() -> bool:
    return tmux_mode() == "private"
```

### 2. Add tmux command builder

Replace direct `tmux -S ...` construction with a helper:

```py
def tmux_command(*args: str) -> list[str]:
    if use_private_tmux():
        return ["tmux", "-S", str(paths()["tmux_socket"]), *args]
    return ["tmux", *args]
```

Keep using `env=base_env()` for non-interactive tmux management commands so inherited `TMUX`/`TMUX_PANE` are stripped. This makes default mode target the default tmux socket instead of an arbitrary currently attached/nested tmux client.

Interactive attach/switch commands need special handling described below, because `tmux attach` from inside an existing tmux client can fail or create confusing nested-client behavior.

### 3. Update `base_env()`

`base_env()` should always set private tracker/runtime env:

- `BROCCOLI_COMMS_APP_RUNTIME=1`
- `BROCCOLI_COMMS_RUNTIME_DIR`
- `BROCCOLI_COMMS_CACHE_DIR`
- `BROCCOLI_COMMS_CONFIG_DIR`
- `AGENT_TRACKER_SOCKET`

But tmux socket env should depend on mode:

Private mode:

```py
env["BROCCOLI_COMMS_TMUX_SOCKET"] = str(paths()["tmux_socket"])
env["AGENT_TRACKER_TMUX_SOCKET"] = str(paths()["tmux_socket"])
```

Default mode:

- Do **not** set `BROCCOLI_COMMS_TMUX_SOCKET`
- Do **not** set `AGENT_TRACKER_TMUX_SOCKET`

Reason: tracker/tmux utilities should use normal `tmux` commands in default mode, and `agent-wrapper` inside tmux panes can infer the actual socket from the pane's `TMUX` environment.

Continue stripping inherited `TMUX`/`TMUX_PANE` in `base_env()` for CLI-launched tmux commands.

### 4. Update launch command construction

`managed_agent_launch_command()` and `ui_launch_command()` currently inject private tmux socket env variables into the pane command.

Add a helper such as:

```py
def tmux_env_assignments_for_pane() -> list[str]:
    if not use_private_tmux():
        return []
    p = paths()
    return [
        f"AGENT_TRACKER_TMUX_SOCKET={shlex.quote(str(p['tmux_socket']))}",
        f"BROCCOLI_COMMS_TMUX_SOCKET={shlex.quote(str(p['tmux_socket']))}",
    ]
```

In default mode, omit these assignments so `wrapper/agent-wrapper.sh` uses `TMUX` from inside the pane to register the real default tmux socket.

Keep passing:

- `AGENT_TRACKER_SOCKET`
- `SUGGESTED_AGENT_NAME`
- `AGENT_ID` for UI
- `BROCCOLI_COMMS_APP_RUNTIME`
- `BROCCOLI_COMMS_RUNTIME_DIR`

### 5. Update `ensure_tmux()`

Private mode:

- keep old behavior
- write private tmux config
- start with `tmux -S <private> -f <tmux_conf> new-session ...`

Default mode:

- do not call `write_tmux_conf()` for global private config
- do not pass `-f <tmux_conf>`
- if session exists, return
- otherwise create:

```sh
tmux new-session -d -s broccoli-comms -c "$HOME" bash
```

Optionally set only safe session/window-local options after session creation. Do not change global server options.

### 6. Update `stop()`

Private mode:

- keep old `tmux kill-server` behavior for the private tmux socket
- clean private socket if unreachable

Default mode:

- run:

```sh
tmux kill-session -t broccoli-comms
```

- do not unlink or inspect `$runtime/tmux.sock` as authoritative
- stop the private tracker exactly as before

### 7. Make `ui` / `open` safe inside and outside tmux

`broccoli-comms ui` currently ends by attaching to the UI window/session. In default-tmux mode this must work safely in two cases:

#### Outside tmux

If `TMUX` is not set in the user's original environment, attach normally:

```py
os.execvpe("tmux", tmux_command("attach", "-t", target), base_env())
```

This opens the Broccoli session/UI in the terminal.

#### Inside tmux

If the user invoked `broccoli-comms ui` from inside an existing tmux client, do **not** attempt a nested `tmux attach` by default. Instead, switch the current client to the Broccoli target:

```sh
tmux switch-client -t <target>
```

Use the user's original tmux environment for this switch, not stripped `base_env()`, because `switch-client` operates on the current attached client. If the current client is on a different socket than the default target, fail gracefully with instructions instead of creating a nested attach.

Recommended helper:

```py
def in_tmux_client() -> bool:
    return bool(os.environ.get("TMUX"))


def exec_tmux_interactive(target: str) -> None:
    if in_tmux_client() and not use_private_tmux():
        os.execvpe("tmux", ["tmux", "switch-client", "-t", target], os.environ.copy())
    else:
        os.execvpe("tmux", tmux_command("attach", "-t", target), base_env())
```

For private mode, switching from an arbitrary existing tmux client to the private socket may not be possible. Keep the existing attach behavior for private mode, but if tmux reports a nested-session error, print a clear message such as:

```text
Broccoli Comms is using a private tmux socket. Run this command outside tmux, or attach manually:
  tmux -S <private-socket> attach -t broccoli-comms
```

If implementing graceful fallback is straightforward, prefer catching attach failures for private mode and printing the manual command instead of raw tmux errors.

#### Commands affected

Use the same interactive helper for:

- `broccoli-comms ui`
- `broccoli-comms open`
- `broccoli-comms attach`
- `broccoli-comms agent attach <name>`

For `agent focus <name>`, if already inside default tmux, switching/selecting in the current client is appropriate. Outside tmux, either attach to the target or keep existing behavior if it already works.

### 8. Update attach/focus command construction

Replace all direct `os.execvpe("tmux", ["tmux", "-S", ...])` calls with either:

- `exec_tmux_interactive(target)` for user-facing attach/open operations
- `tmux_command(...)` for non-interactive tmux operations

Examples:

```py
exec_tmux_interactive(SESSION)
exec_tmux_interactive(window["window_id"])
```

### 9. Update registration checks

`ui_window_registered()` currently requires registered `tmux_socket == paths()["tmux_socket"]`.

In default mode, the registered socket should come from the wrapper's `TMUX` env and may not equal `paths()["tmux_socket"]`.

Recommended behavior:

- Private mode: keep strict pane + private socket comparison
- Default mode: compare pane id and session/window context, but do not compare against `paths()["tmux_socket"]`

Example:

```py
if use_private_tmux():
    return info.get("tmux_pane") == window.get("pane_id") and info.get("tmux_socket") == str(paths()["tmux_socket"])
return info.get("tmux_pane") == window.get("pane_id")
```

### 10. Update status/doctor output

Status should expose tmux mode.

Human status should show something like:

```text
tmux mode:      default
tmux session:   broccoli-comms
tmux socket:    default
```

Private mode can show the private socket path.

JSON status should include:

```json
{
  "tmux": {
    "mode": "default",
    "session": "broccoli-comms",
    "socket": null,
    "running": true
  }
}
```

or, for private mode:

```json
{
  "tmux": {
    "mode": "private",
    "session": "broccoli-comms",
    "socket": "/run/user/.../broccoli-comms/tmux.sock",
    "running": true
  }
}
```

Doctor should not report missing `$runtime/tmux.sock` as a problem in default mode.

### 11. Update docs

Update docs to say:

- default behavior uses the default tmux server/session
- private tracker remains private
- old private tmux behavior is available with `BROCCOLI_COMMS_TMUX_MODE=private`
- `stop` only kills the Broccoli session in default mode
- using default tmux improves visibility/integration with the user's normal tmux workflow but reduces tmux isolation compared with private mode

Files:

- `README.md`
- `About.md`
- `docs/RUNTIME_API.md`
- possibly `docs/SETUP_AND_MULTI_DEVICE.md`

## Testing and validation

### Syntax/unit checks

```sh
python -m py_compile app/broccoli-comms.py agent-registry/server.py agent-tracker/*.py agent-tracker/ctl_commands/*.py
```

If Go changes are needed:

```sh
( cd agent-communicator-tui && go test ./... )
```

### Default tmux mode smoke

Use isolated tracker/cache/config, but default tmux server:

```sh
export BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-default-tmux-runtime
export BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-default-tmux-cache
export BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-default-tmux-config
unset BROCCOLI_COMMS_TMUX_MODE
rm -rf "$BROCCOLI_COMMS_RUNTIME_DIR" "$BROCCOLI_COMMS_CACHE_DIR" "$BROCCOLI_COMMS_CONFIG_DIR"

python app/broccoli-comms.py start
python app/broccoli-comms.py status --json
python app/broccoli-comms.py agent-tracker list
python app/broccoli-comms.py ui   # or open in a controlled smoke tmux if interactive attach is inconvenient
python app/broccoli-comms.py stop
```

Verify:

- no `$BROCCOLI_COMMS_RUNTIME_DIR/tmux.sock` is required/created as the authoritative socket
- default tmux has/had a `broccoli-comms` session
- `stop` removes only the `broccoli-comms` session, not the default tmux server
- private tracker starts/stops normally
- `agent-tracker list` works

### UI inside/outside tmux smoke

Outside tmux:

```sh
BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-ui-outside-runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-ui-outside-cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-ui-outside-config \
python app/broccoli-comms.py ui
```

Expected: command attaches to the Broccoli UI/session.

Inside an existing default tmux client:

```sh
tmux new-session -d -s broccoli-ui-sentinel 'sleep 300'
tmux new-session -d -s broccoli-ui-test-shell
# attach to broccoli-ui-test-shell, then run:
python app/broccoli-comms.py ui
```

Expected in default mode: the current tmux client switches to the Broccoli UI/session instead of attempting a nested attach. The sentinel session survives.

Also validate non-interactive behavior without attaching by using `capture-pane` after `ui` creates the UI window, if possible:

```sh
python app/broccoli-comms.py agent-tracker capture-pane agent-communicator --last 20
```

### Private tmux compatibility smoke

```sh
export BROCCOLI_COMMS_TMUX_MODE=private
export BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-private-tmux-runtime
export BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-private-tmux-cache
export BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-private-tmux-config
rm -rf "$BROCCOLI_COMMS_RUNTIME_DIR" "$BROCCOLI_COMMS_CACHE_DIR" "$BROCCOLI_COMMS_CONFIG_DIR"

python app/broccoli-comms.py start
python app/broccoli-comms.py status --json
python app/broccoli-comms.py agent-tracker list
python app/broccoli-comms.py stop
```

Verify old private socket behavior still works.

### Managed agent smoke

```sh
python app/broccoli-comms.py agent add smoke --cwd "$PWD" --command 'bash -lc "sleep 60"'
python app/broccoli-comms.py start
python app/broccoli-comms.py agent list --json
python app/broccoli-comms.py agent-tracker list
python app/broccoli-comms.py agent remove smoke
python app/broccoli-comms.py stop
```

Run in both default and private modes if practical.

### Safety smoke

Before `stop`, create a non-Broccoli session in the default tmux server:

```sh
tmux new-session -d -s broccoli-stop-sentinel 'sleep 300'
python app/broccoli-comms.py start
python app/broccoli-comms.py stop
tmux has-session -t broccoli-stop-sentinel
# cleanup
tmux kill-session -t broccoli-stop-sentinel
```

The sentinel session must survive.

## Acceptance criteria

- Default `broccoli-comms start` uses default tmux server/socket.
- Default `broccoli-comms stop` does not kill the user's tmux server or unrelated sessions.
- `BROCCOLI_COMMS_TMUX_MODE=private` preserves old private tmux behavior.
- Managed agents register with usable tmux pane/socket metadata in both modes.
- `broccoli-comms ui/open/attach/focus/agent attach` work in both modes.
- `broccoli-comms agent-tracker capture-pane/send-text/send-key` still work for local registered agents.
- Status/doctor accurately report tmux mode.
- Docs explain the behavior and tradeoff.
- Registry and remote direct-input security gates are not weakened.
