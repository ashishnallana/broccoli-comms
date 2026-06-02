# Socket/Wrapper Fix Task — Reviewer Instructions

You are the reviewer for the Broccoli Comms socket/wrapper cleanup.

## Communication constraint

Do **not** use `agent-tracker-ctl` or `broccoli-comms agent-tracker send-message` for coordination. The user explicitly asked for manual tmux communication because agent routing is suspect.

Use manual tmux only:

```sh
tmux list-panes -a -F '#{session_name}\t#{window_name}\t#{pane_id}\t#{pane_pid}\t@agent_name=#{@agent_name}\t@agent_id=#{@agent_id}'
tmux capture-pane -p -t <coder-pane> -S -200
tmux send-keys -t <coder-pane> '<short review request>' Enter
```

Your coder pane is in the same `socket-fix` tmux window.

## Review objective

Independently validate the coder's changes for:

1. One canonical Broccoli Comms runtime/socket by default.
2. No nested wrapper chains.
3. `agent-tracker-ctl` standalone deprecation shim.
4. `broccoli-comms agent-tracker ...` still functional.
5. Home Manager aliases/extensions do not use legacy/global tracker behavior.

## Files/areas to inspect

- `/home/tanmay/projects/nix/broccoli-comms/flake.nix`
- `/home/tanmay/projects/nix/broccoli-comms/app/broccoli-comms.py`
- `/home/tanmay/projects/nix/broccoli-comms/wrapper/agent-wrapper.sh`
- `/home/tanmay/projects/nix/broccoli-comms/modules/home-manager.nix`
- `/home/tanmay/projects/nix/home-manager-core/home.nix`
- `/home/tanmay/projects/nix/home-manager-core/modules/scripts/agent-wrapper-package.nix`
- `/home/tanmay/projects/nix/home-manager-extensions/ai-agents.nix`
- docs/skills mentioning `agent-tracker-ctl`

## Required checks

### Static checks

```sh
cd /home/tanmay/projects/nix/broccoli-comms
python3 -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-tracker/ctl_commands/*.py agent-registry/*.py
bash -n wrapper/agent-wrapper.sh
```

### Behavior checks

Use temporary isolated dirs. Do not rely on production tracker state.

Check deprecated command:

```sh
nix run /home/tanmay/projects/nix/broccoli-comms#agent-tracker-ctl -- --help
```

Expected: deprecation message telling users to use `broccoli-comms agent-tracker ...`.

Check canonical runtime:

```sh
TMP=$(mktemp -d)
HOME=$TMP/home XDG_RUNTIME_DIR=$TMP/run XDG_CACHE_HOME=$TMP/cache XDG_CONFIG_HOME=$TMP/config \
  nix run /home/tanmay/projects/nix/broccoli-comms#broccoli-comms -- status --json
```

Expected runtime is `$TMP/run/broccoli-comms`, not cache.

Check internal ctl still works:

```sh
HOME=$TMP/home XDG_RUNTIME_DIR=$TMP/run XDG_CACHE_HOME=$TMP/cache XDG_CONFIG_HOME=$TMP/config \
  nix run /home/tanmay/projects/nix/broccoli-comms#broccoli-comms -- agent-tracker list
```

Expected: valid JSON or no local agents, not deprecation failure.

Check wrapper depth:

- Inspect code for `BROCCOLI_COMMS_TRACK_ACTIVE` / `AGENT_WRAPPER_DEPTH` or equivalent.
- If feasible, run a managed command with a fake `pi` alias and inspect `ps --forest`; there should be only one wrapper layer.

### Home Manager eval checks

Run targeted evals where possible. Full `nix flake check` may be heavy; if blocked, document why.

## Review output

Write final review in your pane with:

- PASS/FAIL by acceptance criterion.
- Commands run.
- Any bugs/regressions found.
- Whether product code was fixed without introducing new legacy socket paths.
