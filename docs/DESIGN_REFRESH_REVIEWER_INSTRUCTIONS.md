# Agent Communicator Design Refresh — Reviewer Instructions

You are the reviewer for the Agent Communicator TUI design refresh.

## Reference files

Read these completely first:

- `/home/tanmay/projects/nix/broccoli-comms/docs/AGENT_COMMUNICATOR_DESIGN_REFRESH_REQUIREMENTS.md`
- `/home/tanmay/projects/nix/broccoli-comms/docs/agent-communicator-design-refresh-mock.html`
- coder instructions: `/home/tanmay/projects/nix/broccoli-comms/docs/DESIGN_REFRESH_CODER_INSTRUCTIONS.md`

## Review goal

Validate that the implemented TUI matches the approved HTML mock and requirements using actual `tmux capture-pane` output from the running TUI.

## Required visual checks

Use capture-pane evidence. The final TUI should have:

1. Two columns only.
2. Left column: chat window + composer.
3. Right column: current agent info top, agent list bottom.
4. Current agent info only includes name, host, provider, status indicator/status.
5. Agent list rows only include name, host, provider, status.
6. Counts appear as `LOCAL (n)` / `REMOTE (n)` headings.
7. No visible system-agent explanatory note.
8. No normal `agent-communicator` rows in the agent list.
9. Chat header does not repeat selected agent identity.
10. Composer contains `/msg` inside/next to input.
11. Composer help shows `/msg sends an inbox message` and `Enter send` only.
12. Outgoing messages show read/delivery ticks.
13. No unsupported shortcut hints are visible.
14. Same text size everywhere; hierarchy is color/fill/spacing/bold/dim.
15. Solid selected rows/surfaces, not heavy bordered cards.
16. Command palette opens with `Ctrl+Enter` and contains real commands only.

## Required validation commands

Run independently after coder says ready:

```sh
cd /home/tanmay/projects/nix/broccoli-comms/agent-communicator-tui
go test ./...

cd /home/tanmay/projects/nix/broccoli-comms
nix build .#agentCommunicator -L
```

Run the TUI and capture it. Suggested:

```sh
RUN=/tmp/bc-ui-refresh-review.$(date +%s)
mkdir -p "$RUN"/{runtime,cache,config}
BROCCOLI_COMMS_TMUX_MODE=private \
BROCCOLI_COMMS_RUNTIME_DIR="$RUN/runtime" \
BROCCOLI_COMMS_CACHE_DIR="$RUN/cache" \
BROCCOLI_COMMS_CONFIG_DIR="$RUN/config" \
./bin/broccoli-comms start

# Open the built TUI in tmux, capture with:
tmux capture-pane -p -t <ui-pane> -S -140 > "$RUN/ui-capture.txt"
```

Also test command palette capture:

```sh
tmux send-keys -t <ui-pane> C-Enter
sleep 1
tmux capture-pane -p -t <ui-pane> -S -140 > "$RUN/command-palette-capture.txt"
```

## Review output

Write in your pane:

- PASS/FAIL by acceptance criterion
- test/build commands run
- capture artifact paths
- any differences from the HTML mock
- whether differences are acceptable

If PASS, include exact marker:

```text
UI_REFRESH_REVIEW_PASS
```

If FAIL, include exact marker:

```text
UI_REFRESH_REVIEW_FAIL
```

## Coordination

Use manual tmux commands/captures only. Do not use agent-tracker messaging for coordination.
