# Agent Communicator Design Refresh Plan

## Goal

Refresh the Agent Communicator TUI to feel cleaner, more modern, and easier to navigate, inspired by opencode's minimal interface:

- solid filled UI surfaces instead of heavy bordered cards
- focused composer-first layout
- lightweight footer/status treatment
- command palette for discoverability
- compact agent switcher
- hidden/system agents kept out of normal chat list

This plan is design/implementation guidance only; it should be implemented after the current socket/wrapper routing fixes and E2E rerun are complete.

## Current observations

Captured current Agent Communicator TUI:

- Pane: `broccoli-comms-agents:ui-inspiration` / `%10`
- Command: `agent-communicator`

Issues observed:

1. Sidebar uses heavy bordered cards for each agent; this consumes vertical space and creates visual noise.
2. Conversation pane is mostly blank when there are no messages.
3. Footer is overloaded with status and many shortcuts.
4. Remote `agent-communicator` rows can appear as normal selectable agents.
5. Hidden count is shown but not actionable/explainable.
6. Conversation title is visually awkward/truncated.

Captured opencode:

- Pane: `broccoli-comms-agents:opencode-inspiration` / `%11`
- Command: `nix-shell -p opencode --run opencode`

Useful design patterns:

1. Large minimal central prompt.
2. Mode/model status near the composer.
3. Clean command palette overlay via `ctrl+p`.
4. Compact agent switcher overlay via `ctrl+x a`.
5. Sparse footer: current path/branch/version and a few contextual hints.
6. Solid filled selection blocks instead of nested borders.

## Design direction

### TUI text sizing constraint

Because this is a terminal UI, all text should be treated as the same cell/font size. Visual hierarchy must come from:

- solid filled backgrounds
- foreground/background color
- bold/dim styles
- spacing and alignment
- glyphs/icons such as `●`, `▣`, and timeline rails

Do not rely on large headers, tiny metadata, or web-like font scaling in the actual TUI. The HTML mock should also approximate this by using one text size throughout.

### Visual language

Move from bordered-card UI to solid surfaces:

- selected item: solid accent background
- hovered/focused item: muted filled background
- section headers: compact uppercase/label text
- secondary metadata: low-contrast inline text
- use borders sparingly only for app shell separation, not every row

Example agent row style:

```text
  ● local-alpha                 Pi · local
    /home/tanmay/project        zephyrus
```

Selected:

```text
████████████████████████████████████████
█ ● local-alpha        Pi · local       █
█ /home/tanmay/project zephyrus         █
████████████████████████████████████████
```

But implemented as a filled Lip Gloss style, not box drawing around every card.



### Shortcut/help non-redundancy rule

The footer and composer should not duplicate the full keymap. Show only one primary discoverability hint: `Ctrl+P command palette`. Other actions should be discoverable inside the command palette, and shortcut labels should only be shown for shortcuts that are actually implemented and supported.

### Non-redundancy rule

The selected/current agent context should be owned by the current-agent panel. Avoid repeating the same agent name/host/provider/status in the chat header, composer placeholder, and agent list. The agent list should primarily be a switcher for other agents; if the current agent appears there, show it with minimal styling and no repeated metadata.

### Layout v2

Proposed default layout:

```text
┌ left rail / list ┐  main conversation

Agent Communicator       local-alpha · Pi · zephyrus
5 agents · 5 hidden       /msg · chat message

LOCAL                    ┌ composer area / focused input ┐
█ ● local-alpha       █   │ type message...              │
  ● local-beta            └──────────────────────────────┘
  ● pi

REMOTE                   Empty state / messages
  ● vm/remote-alpha       No messages yet.
  ● vm/remote-beta        Press Enter to send, Ctrl+P for commands.

status line: rpc ok · registry online · socket agent-tracker.sock
hint line: ctrl+p commands · ctrl+x a agents · tab mode · ctrl+q quit
```

Eventually make sidebar collapsible, but not required for first pass.

## Command palette

Add a command palette similar to opencode.

### Shortcut

Primary:

```text
Ctrl+P
```

Optional aliases:

```text
Ctrl+O
:
```

### Behavior

- Opens centered overlay.
- Search input at top.
- List of commands below grouped by category.
- Arrow keys navigate.
- Enter executes selected command.
- Escape closes.

### Initial command set

#### Messaging

- Send message (`/msg`)
- Send text to pane (`/text`)
- Send key to pane (`/keys`)
- Toggle input mode
- Clear composer

#### Agents

- Switch agent
- Focus selected agent pane
- Attach to selected agent
- Hide selected agent
- Show hidden/system agents
- Refresh agents
- Save selected agent

#### Conversation

- Mark inbox read
- Reload conversation
- Scroll messages up/down
- Open selected attachment
- Save conversation snippet

#### Runtime

- Show registry status
- Show tracker status
- Copy selected target address
- Copy selected agent UUID
- Debug capture current pane

#### UI

- Toggle sidebar
- Toggle compact/detailed rows
- Toggle system agents
- Open help
- Quit

### Data model

Add a command descriptor type, e.g. in Go:

```go
type commandAction struct {
    ID          string
    Title       string
    Subtitle    string
    Category    string
    Shortcut    string
    Keywords    []string
    Enabled     func(appModel) bool
    Run         func(appModel) tea.Cmd
}
```

The palette should filter by title/subtitle/category/keywords.

## Agent switcher overlay

Add a compact agent switcher inspired by opencode's `Select agent` overlay.

### Shortcut

```text
Ctrl+X A
```

or if Ctrl+X sequences are not ergonomic in Bubble Tea, use:

```text
Ctrl+A
```

if not conflicting with existing read action, or:

```text
Ctrl+G
```

### Behavior

- Centered overlay.
- Search agents by name, hostname, type, cwd.
- Shows only normal selectable agents by default.
- System/hidden agents toggleable with a command.

## System and hidden agents

`agent-communicator` identities should not appear as normal chat targets by default.

Rules:

1. Hide any agent where:
   - `name == "agent-communicator"`
   - target/display name ends with `/agent-communicator`
   - `agent_type` starts with `agent-communicator`
   - `agent_cmd` contains `agent-communicator`
2. Keep them discoverable under:
   - command palette: `Show system agents`
   - status detail overlay
3. Do not silently delete them from data model; only hide from normal list.
4. If directly addressed by a message/reply, conversation can still be resolved by stable identity.

## Empty states

Replace blank conversation area with contextual content.

### No messages

```text
No messages yet
Send a message to local-alpha, or use Ctrl+P for actions.

Target: local-alpha
Scope: local
Pane: %12
CWD: /path/to/project
```

### No agent selected

```text
Select an agent
Press Ctrl+X A to open the agent switcher, or Ctrl+P for commands.
```

### Registry disconnected

```text
Registry disconnected
Local messaging still works. Open registry status from Ctrl+P.
```

## Footer/status simplification

Split into two lines with distinct roles:

1. Runtime status line:

```text
rpc ok · local 4 · remote 2 · registry online · socket agent-tracker.sock
```

2. Contextual shortcut line:

```text
ctrl+p commands · ctrl+x a agents · tab mode · enter send · ctrl+q quit
```

Do not list every shortcut all the time. Put complete help in command palette/help overlay.

## Implementation phases

### Phase 0 — Baseline screenshots/captures

Capture current UI states before changes:

- normal list + empty conversation
- selected local agent with history
- selected remote agent
- registry disconnected state if easy
- command help/current footer

Store captures under an artifact dir or docs for comparison.

### Phase 1 — Solid-row sidebar refresh

Files likely involved:

- `agent-communicator-tui/agent_list.go`
- `agent-communicator-tui/style.go`
- `agent-communicator-tui/view.go`
- `agent-communicator-tui/hidden_agents.go`

Work:

1. Replace bordered agent cards with filled rows.
2. Add compact and detailed row modes if feasible.
3. Improve selected row contrast.
4. Keep local/remote grouping.
5. Add clear hidden/system count line.

Acceptance:

- Sidebar fits more agents vertically.
- Selection remains obvious.
- No regression in mouse/keyboard navigation.

### Phase 2 — Hide system communicator rows by default

Work:

1. Centralize `isSystemAgent(row)` logic.
2. Hide `agent-communicator` rows from normal list by default.
3. Count hidden system agents separately or explain hidden count.
4. Add tests for remote `host/agent-communicator` filtering.

Acceptance:

- Remote/local `agent-communicator` rows do not appear as normal selectable agents.
- They are still present in raw tracker data and can be shown in system overlay.

### Phase 3 — Command palette

Files likely involved:

- new `agent-communicator-tui/command_palette.go`
- `agent-communicator-tui/commands.go`
- `agent-communicator-tui/app.go`
- `agent-communicator-tui/view.go`
- tests in `command_palette_test.go`

Work:

1. Add palette state: open/closed, query, selected index.
2. Add command descriptors.
3. Render centered overlay.
4. Wire `Ctrl+P`, Escape, Enter, arrows.
5. Include current shortcut help as commands.

Acceptance:

- `Ctrl+P` opens palette.
- Search filters commands.
- Enter runs selected command.
- Escape closes without side effects.

### Phase 4 — Agent switcher overlay

Work:

1. Add agent switcher mode or reuse command palette infrastructure.
2. Search/filter normal agents.
3. Optional toggle for hidden/system agents.
4. Enter selects agent.

Acceptance:

- Agent switching does not require long sidebar navigation.
- Hidden `agent-communicator` rows remain hidden unless explicitly toggled.

### Phase 5 — Composer and empty-state polish

Work:

1. Place mode label near composer: `/msg`, `/text`, `/keys`.
2. Improve empty conversation state.
3. Add selected-agent metadata in empty state.
4. Reduce footer density.

Acceptance:

- New users understand what to do on blank conversation.
- Footer is shorter and less noisy.

### Phase 6 — Visual regression captures

After implementation, capture the same states as Phase 0 and compare:

- compact sidebar
- command palette open
- agent switcher open
- empty conversation
- selected conversation with messages

## Test plan

### Go unit tests

Add/extend tests for:

- system agent filtering
- hidden count behavior
- command palette filtering
- command palette keyboard behavior
- agent switcher filtering
- selected agent preservation after filtering

Run:

```sh
cd agent-communicator-tui
go test ./...
```

### Nix/build checks

```sh
nix build .#agentCommunicator
nix flake check -L
```

### Manual TUI validation

Use isolated runtime if possible:

```sh
BROCCOLI_COMMS_TMUX_MODE=private \
BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-ui-refresh/runtime \
BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-ui-refresh/cache \
BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-ui-refresh/config \
broccoli-comms start

broccoli-comms ui
```

Capture:

```sh
tmux capture-pane -p -t <ui-pane> -S -120 > /tmp/agent-communicator-ui-refresh.txt
```

Validate:

- no normal `agent-communicator` rows
- command palette opens
- agent switcher opens
- shortcuts work
- local and remote messaging still use correct target identity

## Risks

1. Over-polishing could destabilize routing-related TUI behavior.
   - Keep data model unchanged in early phases.
2. Hiding system agents could make diagnostics harder.
   - Provide explicit `Show system agents` command.
3. Keyboard conflicts with existing shortcuts.
   - Audit existing keymap before finalizing shortcuts.
4. Solid-row styles may have contrast issues across themes.
   - Use existing palette and add tests/snapshots where possible.

## Suggested first implementation PR

Keep first PR small:

1. Solid-row sidebar styling.
2. Hide `agent-communicator` rows by default.
3. Simplified footer text.
4. Baseline tests for filtering.

Then add command palette in second PR if needed.
