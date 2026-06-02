# Socket/Wrapper Fix Task — Coder Instructions

You are the coding agent for the Broccoli Comms socket/wrapper cleanup.

## Communication constraint

Do **not** use `agent-tracker-ctl` or `broccoli-comms agent-tracker send-message` for coordination. The user explicitly asked for manual tmux communication because agent routing is suspect.

Use manual tmux evidence/communication only, for example:

```sh
tmux list-panes -a -F '#{session_name}\t#{window_name}\t#{pane_id}\t#{pane_pid}\t@agent_name=#{@agent_name}\t@agent_id=#{@agent_id}'
tmux capture-pane -p -t <pane> -S -120
tmux send-keys -t <pane> '<short message>' Enter
```

Your reviewer pane is in the same `socket-fix` tmux window. Use pane capture/send-keys to coordinate.

## Goal

Fix the current routing confusion by ensuring:

1. Only one canonical Broccoli Comms socket/runtime is used by Home Manager and CLI by default.
2. Only one wrapper layer is used; aliases must not cause nested `agent-wrapper -> agent-wrapper -> pi` chains.
3. `agent-tracker-ctl` is deprecated and should print a clear message telling users to use `broccoli-comms agent-tracker ...` instead.
4. Home Manager aliases/extensions point to canonical Broccoli Comms commands and avoid legacy/global tracker behavior.

## Repos likely involved

- `/home/tanmay/projects/nix/broccoli-comms`
- `/home/tanmay/projects/nix/home-manager-core`
- `/home/tanmay/projects/nix/home-manager-extensions`

## Required implementation areas

### A. Canonical runtime/socket

Make the default canonical runtime be the Broccoli CLI default:

```sh
${XDG_RUNTIME_DIR:-/tmp/$UID}/broccoli-comms
```

and socket:

```sh
$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock
```

Do not make Home Manager default to `~/.cache/broccoli-comms/runtime` unless explicitly configured by user.

Check:

- `broccoli-comms/modules/home-manager.nix`
- `home-manager-core/home.nix`

### B. Deprecate `agent-tracker-ctl`

Make the installed `agent-tracker-ctl` command print an error/help message like:

```text
agent-tracker-ctl is deprecated. Use: broccoli-comms agent-tracker <subcommand> [args...]
```

Exit non-zero, except `--help` may also print the same deprecation message.

Important: `broccoli-comms agent-tracker ...` may still internally use the Python ctl implementation; do not break that internal path. If needed, point `BROCCOLI_COMMS_AGENT_TRACKER_CTL` at the Python file while the standalone `agent-tracker-ctl` package is only a deprecation shim.

### C. One wrapper only

Prevent nested wrapping.

Add an environment guard such as:

```sh
BROCCOLI_COMMS_TRACK_ACTIVE=1
AGENT_WRAPPER_DEPTH=1
```

When a wrapper/alias sees this, it should exec the raw command directly rather than call `broccoli-comms track` again.

Check:

- `broccoli-comms/app/broccoli-comms.py` track implementation
- `broccoli-comms/wrapper/agent-wrapper.sh`
- `home-manager-core/modules/scripts/agent-wrapper-package.nix`
- alias generation in `home-manager-core/home.nix`
- `home-manager-extensions/ai-agents.nix` if it contributes aliases/settings

### D. Alias policy

Aliases (`pi`, `claude`, `codex`, `gemini`) should behave as:

- Outside Broccoli tracking: `broccoli-comms track --name <alias> -- <raw-binary> "$@"`
- Inside Broccoli tracking: `exec <raw-binary> "$@"`

Managed agents that run `--command pi` should not create a second agent registration inside the managed pane.

### E. Validation/tests

At minimum run targeted static/build tests that are feasible. Suggested checks:

```sh
cd /home/tanmay/projects/nix/broccoli-comms
python3 -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-tracker/ctl_commands/*.py agent-registry/*.py
bash -n wrapper/agent-wrapper.sh
nix flake check .#checks.x86_64-linux.unit-tests -L   # if available/fast enough

cd /home/tanmay/projects/nix/home-manager-core
nix flake check -L   # or targeted eval if full check is too heavy

cd /home/tanmay/projects/nix/home-manager-extensions
nix flake check -L   # or targeted eval if full check is too heavy
```

Also manually inspect wrappers/aliases with `nix build` where possible.

## Acceptance criteria

Document evidence that:

1. Home Manager and CLI default to the same socket.
2. `agent-tracker-ctl` prints the deprecation message.
3. `broccoli-comms agent-tracker list` still works.
4. `pi` alias outside tracking wraps once.
5. `pi` alias inside tracking execs raw and does not wrap again.
6. Managed `broccoli-comms agent add test --command pi --autostart` does not create nested wrappers or wrong agent identity.

## Final response expected

Write a concise implementation summary and test evidence in your pane. The reviewer will inspect diffs and run independent validation.
