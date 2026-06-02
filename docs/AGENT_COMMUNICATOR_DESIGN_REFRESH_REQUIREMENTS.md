# Agent Communicator Design Refresh Requirements

Reference mock:

- `docs/agent-communicator-design-refresh-mock.html`

Reference plan:

- `docs/AGENT_COMMUNICATOR_DESIGN_REFRESH_PLAN.md`

## Goal

Implement a cleaner TUI refresh for `agent-communicator-tui` based on the approved mock. The design must be terminal-first: one text size, high spacing/readability, solid filled UI elements, and minimal redundant information.

## Non-goals

- Do not change message routing semantics beyond UI display needs.
- Do not reintroduce `agent-tracker-ctl`; use `broccoli-comms agent-tracker ...` surfaces where the TUI shells out.
- Do not add unsupported shortcut hints.
- Do not show `agent-communicator` mailboxes as normal chat targets.

## Required layout

Two columns only.

### Left column: chat

Left column contains:

1. Header: only `Conversation` or similarly generic label.
   - Must **not** repeat selected agent name/host/provider/status.
2. Chat timeline.
3. Composer/input.

### Right column: current agent + agent list

Right column contains:

1. Top section: current selected agent info.
2. Bottom section: switchable agent list.
3. Bottom status line: registry status only, e.g. `registry online`.

## Current agent info requirements

Current selected agent info must show only:

- status indicator (`●` or equivalent)
- agent name
- agent host
- agent provider/model family (`pi`, `claude`, `codex`, `gemini`, etc.)
- agent status text (`idle`, `busy`, `waiting`, unknown)

Do **not** show in the current-agent panel:

- socket path
- UUID
- cwd
- target address
- pane id
- duplicate registry/local counts
- shortcut help

## Agent list requirements

The right-column bottom section is an agent switcher/list.

Rows should show only:

- status indicator
- agent display name
- provider badge/text
- host
- status

Counts belong in section headings:

```text
LOCAL (3)
REMOTE (2)
```

Do not show separate `local 3 · remote 2` status text.

The current selected agent should not duplicate its full details in the list. Prefer either:

- exclude current selected agent from switcher list, or
- show it as a minimal selected row without repeated metadata.

## Hidden/system agents

`agent-communicator` identities must be hidden from normal agent list by default.

Hide agents where any of these are true:

- name is `agent-communicator`
- display/target name ends with `/agent-communicator`
- `agent_type` starts with `agent-communicator`
- `agent_cmd` contains `agent-communicator`

Do not display explanatory text like:

```text
System agents hidden: agent-communicator mailboxes...
```

System agents may be accessible through command palette later, but no visible normal-list note is required in this refresh.

## Chat timeline requirements

Use a bubbleless timeline inspired by opencode:

- simple vertical rail/glyphs
- whitespace between turns
- no heavy bordered message bubbles
- solid filled block only for emphasized agent output if useful

Outgoing messages must show read/delivery ticks:

- sent: `✓`
- delivered: `✓✓` muted/cyan
- read: `✓✓` green or strong success style

The receipt line should be compact, e.g.:

```text
✓✓ read · 4.2s
```

## Composer requirements

The message mode must appear inside/next to the input box, not in the top header.

Example:

```text
/msg  type message…
```

Below/beside input, show only supported minimal help:

```text
/msg sends an inbox message        Enter send
```

Do not show unsupported or redundant shortcut help.

## Shortcut/help requirements

Keyboard navigation update:

- `Ctrl+P` is reserved for moving up/previous in the agent list/navigation.
- `Ctrl+Enter` opens the command palette popup.
- Do not show `Ctrl+P command palette` anywhere.


Only show shortcut hints that are actually supported.

For this refresh:

- Composer may show `Enter send`.
- Command palette may show command/action labels.
- Do **not** show footer text like `Ctrl+Enter command palette` unless command palette is implemented and bound.
- Do **not** show `Ctrl+X A`, `Ctrl+F`, `Ctrl+R`, `Ctrl+Q`, etc. unless implemented in this PR.

## Command palette requirements

Add a command palette in this implementation pass.

Minimum acceptable command palette:

- Opens with `Ctrl+Enter`.
- Centered overlay.
- Search/filter input.
- Arrow navigation.
- Enter executes selected command.
- Escape closes.
- Contains only commands backed by existing functionality.

Initial commands:

- Switch agent
- Refresh agents
- Toggle compact/detailed list if implemented
- Focus selected pane if already supported
- Registry status if already supported
- Help/about if implemented

Even though command palette must be implemented, do not show persistent `Ctrl+Enter command palette` footer/help text in normal UI unless the final UI design explicitly includes it. The palette itself may show `Ctrl+Enter` in its overlay/header.

## Visual style requirements

- Use same text size everywhere; terminal UI cannot rely on font-size hierarchy.
- Use color, dim/bold, solid filled rectangles, and spacing for hierarchy.
- Prefer solid selected row/background over borders.
- Avoid bordered cards for each agent.
- Use more padding/spacing because terminal fonts are small.
- Avoid dense all-in-one footer/status lines.

## Data/display non-redundancy rules

1. Current agent panel owns selected agent identity.
2. Chat header must not repeat selected agent identity.
3. Composer placeholder must not repeat selected agent name.
4. Agent list must not repeat current agent info already shown above.
5. Runtime counts appear only once, in section headings.
6. Shortcut help appears only once, near the relevant interaction.

## Implementation areas

Likely files:

- `agent-communicator-tui/agent_list.go`
- `agent-communicator-tui/hidden_agents.go`
- `agent-communicator-tui/style.go`
- `agent-communicator-tui/view.go`
- `agent-communicator-tui/commands.go`
- new `agent-communicator-tui/command_palette.go` if implementing palette
- tests under `agent-communicator-tui/*_test.go`

## Acceptance criteria

1. UI is two columns: chat left, agent info/list right.
2. Current agent panel only shows name, host, provider, status indicator/status.
3. Agent list rows only show name, host, provider, status.
4. Local/remote counts are shown in `LOCAL (n)` / `REMOTE (n)` headings.
5. No visible “system agents hidden” explanatory note.
6. `agent-communicator` rows are hidden by default from normal list.
7. `/msg` appears inside/with the input box, not in header.
8. `/msg sends an inbox message` appears beside/near `Enter send`.
9. Outgoing messages show read/delivery tick marks.
10. Unsupported shortcut hints are removed.
11. Same text size is used throughout; hierarchy uses color/fill/spacing.
12. Go tests pass: `cd agent-communicator-tui && go test ./...`.
13. Nix build passes where feasible: `nix build .#agentCommunicator`.

## Review requirements

Reviewer must verify:

- Screenshot/pane capture resembles `docs/agent-communicator-design-refresh-mock.html`.
- No redundant selected-agent info appears in multiple locations.
- No unsupported shortcut hints are visible.
- `agent-communicator` rows are hidden by default.
- Tests/builds listed above pass or blockers are documented.
