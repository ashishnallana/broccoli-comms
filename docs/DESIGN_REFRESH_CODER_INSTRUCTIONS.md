# Agent Communicator Design Refresh — Coder Instructions

You are the coder for the Agent Communicator TUI design refresh.

## Reference files

Read these completely first:

- `/home/tanmay/projects/nix/broccoli-comms/docs/AGENT_COMMUNICATOR_DESIGN_REFRESH_REQUIREMENTS.md`
- `/home/tanmay/projects/nix/broccoli-comms/docs/AGENT_COMMUNICATOR_DESIGN_REFRESH_PLAN.md`
- `/home/tanmay/projects/nix/broccoli-comms/docs/agent-communicator-design-refresh-mock.html`

## Goal

Implement the approved two-column TUI design in `agent-communicator-tui`:

- chat window on the left
- right column top: current agent info only
- right column bottom: agent switcher/list
- solid filled UI elements, not bordered cards
- same text size everywhere; use spacing/color/fill/bold/dim for hierarchy
- no redundant selected-agent information
- no unsupported help/shortcut text
- command palette implemented with `Ctrl+Enter`
- use capture-pane evidence to compare final TUI against the HTML mock

## Must-haves

1. Two columns only.
2. Current agent panel shows only:
   - status indicator
   - agent name
   - host
   - provider (`pi`, `claude`, etc.)
   - status text
3. Agent list rows show only:
   - status indicator
   - agent name
   - provider
   - host
   - status
4. Counts appear as section headings:
   - `LOCAL (n)`
   - `REMOTE (n)`
5. No visible “system agents hidden” explanatory text.
6. Hide `agent-communicator` rows by default from normal list.
7. `/msg` appears inside/next to input box, not in the header.
8. Near composer, show only:
   - `/msg sends an inbox message`
   - `Enter send`
9. Outgoing messages show tick marks for delivery/read state.
10. Add command palette (`Ctrl+Enter`) with real backed commands only.
11. Do not display unsupported shortcut hints.
12. Use `broccoli-comms agent-tracker ...`; do not introduce new `agent-tracker-ctl` shellouts.

## Capture-pane verification requirement

Before declaring done, run the updated TUI in a test tmux pane and capture it:

```sh
# Example only; adapt as needed.
BROCCOLI_COMMS_TMUX_MODE=private \
BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-ui-refresh/runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-ui-refresh/cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-ui-refresh/config \
./bin/broccoli-comms start

# Open UI in tmux, then:
tmux capture-pane -p -t <ui-pane> -S -120 > /tmp/agent-communicator-refresh-capture.txt
```

Compare the captured TUI to:

- `/home/tanmay/projects/nix/broccoli-comms/docs/agent-communicator-design-refresh-mock.html`

Your final summary must include:

- capture pane path
- what matches the mock
- any intentional deviations

## Suggested files

Likely edit areas:

- `agent-communicator-tui/agent_list.go`
- `agent-communicator-tui/hidden_agents.go`
- `agent-communicator-tui/style.go`
- `agent-communicator-tui/view.go`
- `agent-communicator-tui/commands.go`
- new `agent-communicator-tui/command_palette.go`
- relevant tests

## Required checks

Run as much as feasible:

```sh
cd /home/tanmay/projects/nix/broccoli-comms/agent-communicator-tui
go test ./...

cd /home/tanmay/projects/nix/broccoli-comms
nix build .#agentCommunicator -L
```

Also run/capture the TUI and compare against the mock.

## Coordination

Use manual tmux commands/captures for coordination with reviewer. Do not rely on agent-tracker messaging for this task.

Reviewer pane will be in the same `ui-refresh` tmux window. When ready, notify reviewer manually with:

```sh
tmux send-keys -t <reviewer-pane> 'READY_FOR_UI_REVIEW: <summary>' Enter
```

## Final response in your pane

Include:

- implementation summary
- files changed
- tests/builds run
- capture pane artifact path
- mock-comparison summary
- any known limitations
