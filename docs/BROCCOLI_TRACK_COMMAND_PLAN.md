# Broccoli Comms `track` command implementation plan

## Goal

Add a simple command to run any terminal agent command through Broccoli Comms' in-repo `agent-wrapper`, so it registers with the private tracker and appears in `agent-communicator`.

User-facing problem:

> I have a command like `my-agent` and I want to run it in an existing terminal/tmux pane, but still have it appear in Agent Communicator.

Current workaround requires manually setting env vars and knowing where `agent-wrapper` lives. The new command should hide that complexity.

## Desired UX

Run in the current terminal/pane and register as `my-agent`:

```sh
broccoli-comms track --name my-agent -- my-agent
```

Run from a specific working directory:

```sh
broccoli-comms track --name repo-coder --cwd /path/to/repo -- pi
```

Run an absolute command path:

```sh
broccoli-comms track --name custom -- /opt/agents/my-agent --flag value
```

If `agent-wrapper` is not on `PATH`, this must still work. `broccoli-comms track` should use the launcher's resolved `wrapper_path()` internally.

## Scope

Implement a top-level subcommand:

```sh
broccoli-comms track [--name NAME] [--cwd DIR] -- COMMAND [ARGS...]
```

Implementation should run in the **current tmux pane** by `exec`-ing `agent-wrapper`. It does not create a tmux window and should fail clearly outside tmux because no pane metadata is available. Creating windows is already covered by managed agents and `agent-tracker spin`.

## Behavior

1. Ensure the private tracker is running.
2. Do **not** require `agent-wrapper` on `PATH`.
3. Resolve the wrapper with existing `wrapper_path()`.
4. Validate `--name` if provided using existing agent name validation.
5. If `--name` is omitted, choose a safe default:
   - either command basename, e.g. `pi`
   - or cwd leaf if command basename is too generic
   - document the behavior
6. If `--cwd` is provided:
   - expand `~`
   - convert to absolute path
   - require it exists and is a directory
   - `chdir` before exec
7. Build env from `base_env()` so the tracker socket and runtime paths are correct.
8. Set:
   - `SUGGESTED_AGENT_NAME=<name>`
   - `AGENT_TRACKER_SOCKET=<private tracker socket>` via `base_env()`
9. For tmux socket behavior, rely on the current mode implementation:
   - default tmux mode: do not force private tmux env; wrapper should infer real tmux socket from `TMUX` if running inside tmux
   - private mode: `base_env()`/mode helpers should provide private tmux socket as appropriate
10. `os.execvpe(wrapper_path(), [wrapper_path(), *command], env)` so signals/stdin/stdout/stderr behave like the underlying command.

## Parser design

Add top-level parser:

```py
track_parser = sub.add_parser("track", help="Run a command through agent-wrapper so it appears in Agent Communicator")
track_parser.add_argument("--name", help="Suggested registered agent name")
track_parser.add_argument("--cwd", help="Working directory for the command")
track_parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --")
track_parser.set_defaults(func=track)
```

Handle optional leading `--` in `args.command` because `argparse.REMAINDER` may preserve it.

Error if no command remains:

```text
usage: broccoli-comms track --name NAME -- COMMAND [ARGS...]
error: command is required after --
```

## Implementation sketch

```py
def _derive_track_name(command: list[str], cwd: str | None) -> str:
    basename = Path(command[0]).name or "agent"
    candidate = re.sub(r"[^A-Za-z0-9_.-]", "-", basename).strip("-._")
    return candidate or "agent"


def track(args: argparse.Namespace) -> None:
    command = list(args.command or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("track requires a command after --")

    name = args.name or _derive_track_name(command, args.cwd)
    try:
        validate_agent_name(name)
    except ValueError as e:
        raise SystemExit(str(e))

    cwd = None
    if args.cwd:
        cwd = os.path.abspath(os.path.expanduser(args.cwd))
        if not os.path.isdir(cwd):
            raise SystemExit(f"track cwd does not exist or is not a directory: {cwd}")

    ensure_tracker()
    env = base_env()
    env["SUGGESTED_AGENT_NAME"] = name

    if cwd:
        os.chdir(cwd)

    wrapper = wrapper_path()
    os.execvpe(wrapper, [wrapper, *command], env)
```

If the implementation has tmux-mode-specific pane env helpers from the default-tmux work, use them rather than manually setting tmux socket env.

## Documentation updates

Update `README.md` with a short section near agent commands:

```md
### Track an ad-hoc command in the current pane

Use `broccoli-comms track` when you want to run a command yourself inside the current tmux pane but still have it register with Agent Communicator:

```sh
broccoli-comms track --name my-agent -- my-agent
broccoli-comms track --name repo-coder --cwd ~/repo -- pi
```

`track` resolves Broccoli's bundled `agent-wrapper`; `agent-wrapper` does not need to be on `PATH`. The command you run, such as `my-agent` or `pi`, must still be on `PATH` unless you pass an absolute path.
```

Update skills doc if present:

- `skills/broccoli-comms-cli/SKILL.md`

Add examples:

```sh
broccoli-comms track --name scratch-coder -- pi
broccoli-comms track --name custom --cwd /repo -- /opt/my-agent/bin/my-agent
```

## Tests / validation

At minimum:

```sh
python -m py_compile app/broccoli-comms.py
python app/broccoli-comms.py track --help
```

Focused smoke in a tmux pane if possible:

```sh
BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-track-runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-track-cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-track-config \
python app/broccoli-comms.py track --name track-smoke --cwd "$PWD" -- bash -lc 'sleep 5'
```

From another terminal while it runs:

```sh
BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-track-runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-track-cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-track-config \
python app/broccoli-comms.py agent-tracker list
```

Verify `track-smoke` appears.

Also validate:

- missing command errors cleanly
- invalid name errors cleanly
- nonexistent cwd errors cleanly
- `agent-wrapper` not on PATH still works by using resolved wrapper path
- default tmux mode behavior if current branch includes default-tmux changes
- private tmux mode still works if applicable

## Acceptance criteria

- `broccoli-comms track --name my-agent -- my-agent` runs the command through the in-repo/resolved wrapper.
- The launched command registers with the private tracker and appears in `agent-communicator` / `agent-tracker list` when run in a tmux pane.
- `agent-wrapper` does not need to be on `PATH`.
- `--cwd` works and validates directories.
- Missing command, invalid name, and bad cwd fail with clear messages.
- Existing commands are not regressed.
- Docs and skill examples are updated.
