# Broccoli Comms `agent-tracker` passthrough implementation plan

## Goal

Add a stable Broccoli Comms wrapper for tracker control commands so users do not need `agent-tracker-ctl` on their shell `PATH`:

```sh
broccoli-comms agent-tracker read-inbox --last 10
broccoli-comms agent-tracker send-message test-agent "hello"
broccoli-comms agent-tracker spin /path/to/project pi
broccoli-comms agent-tracker rename --force old-name new-name
```

The passthrough must run against the **Broccoli Comms private runtime** by default: private tracker socket and private tmux socket.

## Current repo facts

The tracker CLI code already exists in this repo:

- Entrypoint: `agent-tracker/agent-tracker-ctl.py`
- Shared helpers: `agent-tracker/ctl_commands/common.py`
- Command modules: `read_inbox.py`, `send_message.py`, `spin.py`, `rename.py`, `send_text.py`, `send_key.py`, `capture_pane.py`, etc.

The Nix package includes `agent-tracker-ctl` in the packaged runtime `PATH`, but source checkout usage should not depend on that global command being available.

## User-facing command

Add a top-level subcommand:

```sh
broccoli-comms agent-tracker <agent-tracker-ctl-subcommand> [args...]
```

Examples:

```sh
broccoli-comms agent-tracker --help
broccoli-comms agent-tracker list
broccoli-comms agent-tracker read-inbox --last 10
broccoli-comms agent-tracker send-message test-agent "hello"
broccoli-comms agent-tracker send-text test-agent "draft"
broccoli-comms agent-tracker send-key test-agent C-c Enter
broccoli-comms agent-tracker capture-pane test-agent --last 80
broccoli-comms agent-tracker registry-status
broccoli-comms agent-tracker spin /home/user/project pi
broccoli-comms agent-tracker rename --force old-name new-name
```

## Implementation design

Update `app/broccoli-comms.py`.

### Parser

Register `agent-tracker` with `argparse.REMAINDER` so all remaining arguments are passed through untouched:

```py
agent_tracker_parser = sub.add_parser(
    "agent-tracker",
    help="Run agent-tracker-ctl against the Broccoli Comms private runtime",
)
agent_tracker_parser.add_argument("tracker_args", nargs=argparse.REMAINDER)
agent_tracker_parser.set_defaults(func=agent_tracker)
```

If no remainder args are provided, pass `--help` to the underlying CLI.

### Command function

Use the in-repo CLI and Broccoli Comms private env:

```py
def agent_tracker(args: argparse.Namespace) -> None:
    ensure_tracker()
    ensure_tmux()
    ctl = repo_root() / "agent-tracker" / "agent-tracker-ctl.py"
    tracker_args = list(args.tracker_args or ["--help"])
    argv = [sys.executable, str(ctl), *tracker_args]
    os.execvpe(sys.executable, argv, base_env())
```

Using `os.execvpe` is preferred because stdout/stderr and exit status mirror `agent-tracker-ctl`.

Calling both `ensure_tracker()` and `ensure_tmux()` for all passthrough commands is acceptable for simplicity. The private tmux server is part of the Broccoli Comms runtime and ensuring it avoids per-command allowlist mistakes for pane-sensitive commands.

### Environment requirements

The command must use `base_env()` so these point at the private runtime:

- `AGENT_TRACKER_SOCKET`
- `AGENT_TRACKER_TMUX_SOCKET`
- `BROCCOLI_COMMS_TMUX_SOCKET`
- `BROCCOLI_COMMS_RUNTIME_DIR`
- `BROCCOLI_COMMS_CACHE_DIR`
- `BROCCOLI_COMMS_CONFIG_DIR`

`base_env()` already strips inherited `TMUX`/`TMUX_PANE`; keep that behavior.

## Tests and validation

Add tests if there is an app-level test harness. If not, add a small focused test for parser behavior or validate with smoke commands.

Required smoke/validation:

```sh
python app/broccoli-comms.py agent-tracker --help
python app/broccoli-comms.py agent-tracker list
python app/broccoli-comms.py agent-tracker registry-status
```

If a private runtime has agents/panes, also validate one pane-sensitive command:

```sh
python app/broccoli-comms.py agent-tracker capture-pane agent-communicator --last 20
```

Confirm the commands use `/run/user/.../broccoli-comms/agent-tracker.sock` rather than the global tracker socket.

## Documentation

Update `README.md` and/or `docs/RUNTIME_API.md` with:

- `broccoli-comms agent-tracker <subcommand> [args...]`
- It is equivalent to `agent-tracker-ctl` but pinned to Broccoli Comms' private runtime.
- It does not require `agent-tracker-ctl` in the user's shell `PATH`.
- Pane commands use the private tmux socket.

## Acceptance criteria

- `broccoli-comms agent-tracker --help` works.
- `broccoli-comms agent-tracker list` returns private tracker JSON.
- `broccoli-comms agent-tracker read-inbox --last 5` works against private mailbox/inbox state.
- `broccoli-comms agent-tracker send-message <agent> "hello"` uses the private tracker socket.
- Tmux-sensitive commands use the private tmux socket.
- Exit codes/stdout/stderr match the underlying CLI behavior.
- Existing `start`, `ui/open`, `stop`, and `agent ...` commands still work.
- No dependency on globally installed `agent-tracker-ctl`.
