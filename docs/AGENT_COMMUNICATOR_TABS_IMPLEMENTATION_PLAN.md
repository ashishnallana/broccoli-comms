# Agent Communicator Tabs Implementation Plan

## Goal

Add first-class tabs to `agent-communicator-tui` so users can switch clearly between:

1. **Simple Chat** — the current focused conversation with the selected agent.
2. **Advanced Chat** — the aggregate/all-inbox conversation view.
3. **Saved Messages** — saved/starred messages grouped by sender/agent.

The code already has the underlying view modes (`simpleView`, `advancedView`, `savedView`) and `Ctrl-T` cycles them. This plan turns those modes into visible, keyboard/mouse navigable tabs.

## Current state

Relevant files:

- `agent-communicator-tui/app.go`
  - Defines `viewMode` with `simpleView`, `advancedView`, `savedView`.
  - `model.mode` stores the active view.
- `agent-communicator-tui/advanced.go`
  - `toggleMode()` cycles through the three modes.
  - `reloadMessages()` chooses per-mode loading behavior.
  - `displayMessages()` and `displayOrderedMessages()` already branch on mode.
- `agent-communicator-tui/update_key.go`
  - `Ctrl-T` currently cycles modes.
  - `Tab` / `Shift-Tab` currently switch agent sections.
- `agent-communicator-tui/view_conversation.go`
  - Renders conversation title and saved-mode composer placeholder.
- `agent-communicator-tui/view_agent_list.go`
  - Sidebar already changes title to `Saved` in saved mode.
- `agent-communicator-tui/mouse.go`
  - Mouse support exists for agent selection and composer input-mode buttons, but not for top-level view tabs.

## UX design

### Tab bar placement

Render a top-level tab bar at the **bottom of the window** as a persistent navigation strip:

```text
┌──────────────────────── main content ────────────────────────┐
│ Conversation / agents / saved messages                       │
└───────────────────────────────────────────────────────────────┘
[ Simple Chat ] [ Advanced Chat ] [ Saved Messages ]
```

For narrow/mobile layouts (`width < 70`), keep the bottom strip but use compact labels:

```text
[ Simple ] [ Advanced ] [ Saved ]
```

The bottom tab strip should be full-width, below the main content, and should remain visible regardless of active tab. Status/error footer text can either render above the tab strip or be folded into a one-line status area immediately above it.

### Generic/extensible tab model

Design the tab system as a data-driven registry, not as hard-coded `if mode == ...` rendering logic. Adding a future tab should usually mean adding one `appTab` entry plus its render/load behavior, without rewriting key handling or mouse hit testing.

Suggested tab metadata:

```go
type appTab struct {
    ID          string
    Mode        viewMode
    Label       string
    ShortLabel  string
    Help        string
    CanCompose  bool
    Load        func(model) tea.Cmd
}
```

Initial entries:

```go
[]appTab{
    {ID: "simple", Mode: simpleView, Label: "Simple Chat", ShortLabel: "Simple", CanCompose: true},
    {ID: "advanced", Mode: advancedView, Label: "Advanced Chat", ShortLabel: "Advanced", CanCompose: true},
    {ID: "saved", Mode: savedView, Label: "Saved Messages", ShortLabel: "Saved", CanCompose: false},
}
```

Future examples should be straightforward:

- `traces` / MLflow traces
- `tasks`
- `reviews`
- `artifacts`
- `settings`

Avoid switch statements in rendering/key/mouse code where a lookup over registered tabs is enough.

### Active tab styling

Use existing Lip Gloss styles and palette tokens:

- Active tab: `colors.SelectedBg` + `colors.SelectedFg`, bold.
- Inactive tab: `colors.PanelBg` + `colors.Muted`.
- Optional accent underline or separator using `colors.Accent`.

### Keyboard behavior

Recommended bindings:

- `Ctrl-T`: keep existing behavior for backward compatibility; cycle forward.
- `Ctrl-Shift-T` or `Ctrl-Y` if Bubble Tea supports it cleanly: cycle backward. If not, skip.
- `Tab` / `Shift-Tab`: **change top-level tabs**.
- Agent-section switching should move to another binding, for example:
  - `Ctrl-G`: toggle local/remote/hidden agent section, or
  - `[` / `]`: previous/next agent section when composer is empty.

Rationale: the user explicitly asked for tabs, and `Tab` is the expected key for tab navigation. Current `Tab` behavior is useful but less discoverable and can be preserved through a new binding.

### Mouse behavior

Clicking a tab switches `m.mode`, resets message scroll/selection as `toggleMode()` currently does, and runs `reloadMessages()`.

### Bottom status/help text

Use the bottom area as two layers when status text exists:

```text
error/status message, if any
tab/s-tab switch tabs · c-t cycle tab · c-n/c-p agent/saved row · c-f save
[ Simple Chat ] [ Advanced Chat ] [ Saved Messages ]
```

When no status exists, keep the tab strip as the final visible line. Saved mode should keep composer disabled and continue showing `Saved messages`.

## Implementation steps

### 1. Add tab metadata helpers

Create a new file:

```text
agent-communicator-tui/tabs.go
```

Add:

```go
type appTab struct {
    ID         string
    Mode       viewMode
    Label      string
    ShortLabel string
    Help       string
    CanCompose bool
}

func appTabs() []appTab
func tabForMode(mode viewMode) (appTab, bool)
func viewModeLabel(mode viewMode, compact bool) string
func (m model) activeTabIndex() int
func (m *model) setMode(mode viewMode)
func (m *model) selectTab(delta int)
func (m model) activeTab() appTab
```

`setMode` should centralize the state reset currently embedded in `toggleMode()`:

- assign `m.mode`
- reset `m.messageOffset = 0`
- clamp/select latest message as appropriate
- call `m.clampSavedSelected()` for saved mode

Keep `toggleMode()` as a thin wrapper over `selectTab(1)` for compatibility.

### 2. Render tab bar at the bottom of the full window

The bottom renderer must iterate `appTabs()` and should not assume there are exactly three tabs. It should gracefully truncate, compact, or horizontally clip if future tabs exceed terminal width.

In `view.go`:

- Add `m.bottomTabBar(m.width)` and render it as the last line/block in `baseView()`.
- Reduce the main content height by `lineCount(m.bottomTabBar(...))` plus any status/help lines.
- Keep the tab strip outside `conversationPanel()` so it spans the full window and remains consistent in wide and narrow layouts.
- Preserve existing error/status footer behavior by rendering status above the tab strip.

Target structure:

```go
tabs := m.bottomTabBar(m.width)
status := m.footer(m.width)
bottomH := lineCount(tabs) + lineCount(status)
bodyH := max(3, m.height-bottomH)
content := m.mainContentView(bodyH) // existing baseView body logic factored out
return truncateLines(lipgloss.JoinVertical(lipgloss.Left, content, status, tabs), m.height)
```

Implementation option: split existing `baseView()` into `baseView()` + `mainContentView(bodyH int)` to avoid duplicating the current menu/mobile/wide layout logic.

### 3. Add tab styles

Either in `style.go` or `tabs.go`, add styles such as:

```go
var activeTopTabStyle = lipgloss.NewStyle()...
var inactiveTopTabStyle = lipgloss.NewStyle()...
```

Use existing palette values only; avoid introducing new colors unless necessary.

### 4. Change key handling

In `update_key.go`:

- Change `tea.KeyTab` to call `m.selectTab(1)` and `m.reloadMessages()`.
- Change `tea.KeyShiftTab` to call `m.selectTab(-1)` and `m.reloadMessages()`.
- Preserve `Ctrl-T` as cycle-forward.
- Move `toggleAgentSection()` to a new binding and document it.

Important saved-mode behavior:

- In `savedView`, `Ctrl-N`/`Ctrl-P` should continue moving saved rows.
- In chat modes, `Ctrl-N`/`Ctrl-P` should continue moving agents.

### 5. Add mouse hit testing for bottom tabs

In `mouse.go`:

- Add `mouseSelectBottomTab(x, y) (viewMode, bool)`.
- Check it before agent-list clicks and input-mode clicks.
- Treat the final rendered tab line/block as the clickable region: `y >= m.height-lineCount(m.bottomTabBar(m.width))` after accounting for any status line above it.
- Map `x` ranges to the rendered tab widths.
- On tab click, call `m.setMode(mode)`, `m.selectLatestMessage()`, and `m.reloadMessages()`.

### 6. Update conversation titles

Make titles more specific:

- `simpleView`: `Simple Chat`
- `advancedView`: `Advanced Chat`
- `savedView`: `Saved Messages`

This gives users confirmation even if the tab row is truncated.

### 7. Tests

Add or update tests in `agent-communicator-tui`:

1. `TestTabBarRendersActiveMode`
   - Verify all registered tab labels render and active mode is distinguishable.
2. `TestTabSwitchingWithTabAndShiftTab`
   - `Tab`: simple → advanced → saved → simple.
   - `Shift-Tab`: simple → saved.
3. `TestCtrlTRemainsBackwardCompatible`
   - Existing `Ctrl-T` cycle still works.
4. `TestSavedTabRendersWithoutComposer`
   - Existing saved-mode test should continue to pass with tab bar present.
5. `TestMouseClickTabSwitchesMode`
   - Click tab x-position and assert `m.mode` changes.
6. `TestTabSwitchReloadsExpectedMessages`
   - Use a stub local client or assert the returned command is non-nil for chat modes and nil/expected for saved mode.
7. `TestTabsAreDataDriven`
   - Add a temporary/fake tab in test or validate helper behavior over `appTabs()` so keyboard cycling and mouse x-range calculations do not assume exactly three tabs.
8. `TestBottomTabBarCompactsWhenManyTabsOrNarrowWidth`
   - Ensure renderer still returns a bounded-width line when labels exceed terminal width.

### 8. Validation

Run:

```sh
cd agent-communicator-tui
nix develop . -c go test ./...
```

Optionally run whole-repo checks where available:

```sh
python3 -m py_compile ../app/broccoli-comms.py ../agent-tracker/*.py ../agent-registry/*.py
```

## Rollout notes

- This should be a TUI-only change; no tracker/runtime API changes are required.
- Keep `Ctrl-T` compatibility so existing users are not broken.
- Be careful with `Tab` inside composer: the current composer is a rune buffer, not a full text editor, so capturing `Tab` for top-level tabs is acceptable. If future multiline editor support needs literal tabs, gate tab switching to empty composer or add an insert-tab binding.

## Open decisions

1. Should `Tab` always switch top-level tabs, or only when composer is empty?
2. What replacement binding should own current agent-section switching?
3. Should advanced chat be renamed to `All Chat` for clarity?
4. Should saved messages be a read-only tab forever, or should it eventually support search/filter/edit actions?
5. Should status/error text render above the bottom tabs, or should the tab strip include a compact status segment on the right?
