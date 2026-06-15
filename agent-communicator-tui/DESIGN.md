# Agent Communicator TUI Design Guide

This guide defines the default visual language for `agent-communicator-tui`. New views should feel like the Simple Chat view first: calm, readable, keyboard-first, and consistent across terminal widths.

## North star: Simple Chat

Simple Chat is the reference implementation for layout, tone, spacing, and interaction density.

It prioritizes:

- One primary task on screen: read the conversation and send the next message.
- Clear hierarchy: title, composer, message stream, supporting sidebar, status, tabs.
- Minimal chrome: use background blocks and spacing before heavy borders.
- Stable navigation: the same keys and visual selection language work everywhere.
- Responsive behavior: the chat remains usable on narrow terminals by hiding secondary panels.

When adding or redesigning a screen, start from Simple Chat patterns instead of inventing new UI primitives.

## Layout system

### Wide layout

For widths `>= 70`, use a two-column shell:

```text
┌──────────────────────── chat/content ───────────────────────┬──── right column ────┐
│ title                                                        │ current agent        │
│ composer                                                     │ switcher/list        │
│                                                              │ registry/status      │
│ message/content stream                                       │                     │
└──────────────────────────────────────────────────────────────┴─────────────────────┘
status/errors
bottom tabs
```

Guidelines:

- Primary content owns the left column.
- Secondary navigation, metadata, and details belong in the right column.
- Keep the right column around one third of the width, capped near the existing Simple Chat behavior.
- Do not let helper panels compete visually with the conversation/content stream.

### Narrow layout

For widths `< 70`:

- Render only the primary panel.
- Hide the right column rather than compressing it into an unreadable layout.
- Use compact labels such as `Simple` instead of `Simple Chat` when needed.
- Reduce horizontal padding from 3 cells to 1 cell.

### Vertical structure

Reserve the bottom of the screen for global feedback:

1. Main content
2. Status/error lines
3. Bottom tab bar

Do not place permanent global commands above the main content unless the screen is a modal or command palette.

## Color and style tokens

Use the shared theme and style helpers. Avoid hard-coded colors in view code.

Preferred tokens:

- `colors.BaseBg`: primary content background.
- `colors.RightColumnBg`: sidebars and secondary panels.
- `colors.PanelBg` / `colors.PanelBgAlt`: nested panels, filters, unread rows.
- `colors.InputBg`: composer and editable input areas.
- `colors.IncomingBubbleBg`: incoming message cards/bubbles on wide layouts.
- `colors.TaskUpdateBg`: task/memory/update cards.
- `colors.CapturePaneBg`: pane capture blocks.
- `colors.SelectedBg` / `colors.SelectedFg`: selected rows, active tabs, hero cards.
- `colors.Accent`: titles and primary section headers.
- `colors.AccentStrong`: important labels inside cards.
- `colors.Muted`: secondary text and hints.
- `colors.Warning` / `colors.Error` / `colors.Success`: semantic states only.

Preferred shared styles/helpers:

- `titleStyle` for view titles.
- `shellTitleStyle` for app/sidebar branding.
- `sectionHeaderStyle` for minor section headers.
- `mutedStyle` for non-critical hints.
- `errorBarStyle` for blocking errors.
- `fgOnBg`, `bgOnly`, `bgSpaces`, `padStyledLine`, and `wrapBackgroundStyledText` for background-safe rendering.

Rule: if a component has a non-base background, every visible cell in that component should be padded/styled with the same background to avoid terminal color gaps.

### Accent usage for scannable metadata

Use accent color to improve readability for high-signal metadata fields, not as decoration.

- Highlight metadata values that identify or classify records, such as memory type, memory status, subject/assigned agent name, sender/agent name, and current agent.
- Prefer `colors.Accent` for normal metadata emphasis and `colors.AccentStrong` for selected, primary, or especially important metadata values.
- Keep low-signal metadata muted so accent-colored fields remain easy to scan.
- Do not rely on color alone: pair emphasized statuses with readable text, dots, badges, or labels.

## Typography and labels

- Titles use short nouns: `Simple Chat`, `Swarm Mode`, `Saved Messages`, `Switch agent`.
- Hints use lowercase, compact command language: `enter send`, `esc close`, `c-u/c-d scroll`.
- Status lines use dot-separated facts: `rpc ok · active coder · online 2/3 · registry online`.
- Avoid noisy labels such as `Selected` when selection is already shown by color or position.
- Prefer `—` for empty optional values inside detail panels.
- Use sentence case for prose and title case only for major view names.

## Spacing and chrome

Simple Chat uses spacing as structure. Follow these defaults:

- Primary panel padding: `Padding(1, 3, 0, 3)` on wide layouts, `Padding(1, 1, 0, 1)` on narrow layouts.
- Composer horizontal padding: 2 cells on wide layouts, 1 on narrow layouts.
- Separate composer and message stream with one blank `BaseBg` line.
- Prefer solid background cards over borders for frequent UI elements.
- Use borders only for controls that need button affordance or modal separation.
- Keep cards compact: usually 2 lines for list rows, 1-3 lines for status summaries.

## Composer and input box pattern

The composer is the primary action surface, and Simple Chat is the reference for every editable input box.

- Place the primary composer directly under the view title in chat-like screens.
- Use the same visual treatment as the Simple Chat composer for all primary input boxes: `colors.InputBg`, full-width padded background fill, rounded/soft spacing via padding rather than heavy borders, and a calm single-surface look.
- Composer, search, filter, and form fields may vary in size, but should still read as the same component family; avoid introducing alternate boxed/bordered input styles unless a modal requires explicit separation.
- Show the active mode as a small accent prefix, for example `/msg`, `/text`, `/keys`.
- Keep mode help outside the input box on `BaseBg` using muted text.
- Limit composer growth; preserve room for the message/content stream.
- Disable composer affordances when the active tab cannot send, and explain why in muted text.

## Message/content stream pattern

Use message bubbles/cards for chronological, selectable, or reviewable content.

- Render a left rail `┃` for each message/card.
- Use `colors.Accent` on the rail for the selected item; `colors.Muted` otherwise.
- Incoming messages and update cards can use filled backgrounds on wide layouts.
- Sent messages can stay on `BaseBg` with receipt/read markers.
- Headers should include sender/agent identity first, timestamp second.
- Use markdown rendering for message bodies when the content type is markdown or unspecified.
- Collapse long non-selected advanced content where appropriate, but keep Simple Chat messages readable by default.

## Right column pattern

The right column is supporting context, not the main task.

Use it for:

- Current agent hero card.
- Current/next task summary.
- Agent switcher/list.
- Registry or runtime status.

Agent rows should follow the existing card model:

- Two lines: identity/status, then provider/host/status metadata.
- Selected row uses `SelectedBg`/`SelectedFg` with bold name.
- Unread row uses `PanelBgAlt` and stronger name text.
- Status is shown with a colored dot plus concise text.

## Tabs and global navigation

- Bottom tabs are global mode switches.
- Active tab uses `SelectedBg`/`SelectedFg` and a leading `▸`.
- Inactive tabs use muted text on `PanelBg`.
- Use registered tab labels and short labels; avoid ad-hoc tab rendering.
- Fit or truncate tabs rather than wrapping them.

## Modals and palettes

Modal screens may take over the full viewport, but they should still use the same tokens.

- Title at top in `titleStyle`.
- One concise help line below the title in `mutedStyle`.
- Selected row uses `SelectedBg`/`SelectedFg`.
- Empty/error states use semantic colors and actionable copy.
- `esc` should close unless the modal is performing an irreversible action.

## Responsive and accessibility rules

- Every rendered line should respect the available width using `truncateCells`, `wrapLine`, or `padStyledLine`.
- Avoid horizontal scrolling for core screens.
- Do not rely on color alone: pair status colors with dots, labels, badges, or text.
- Keep high-contrast selected states.
- Use stable layout heights so content does not jump during refreshes.
- Preserve keyboard-first operation; mouse support should be additive.

## Implementation checklist

Before adding a new view or component:

- [ ] Can this reuse `conversationPanel`, `rightColumn`, `bottomTabBar`, or existing card helpers?
- [ ] Does it use shared `colors` and style helpers instead of hard-coded colors?
- [ ] Does every non-base background fill the full rendered width?
- [ ] Does it degrade cleanly below 70 columns?
- [ ] Are labels short and consistent with Simple Chat?
- [ ] Are empty/loading/error states explicit and concise?
- [ ] Are selection, unread, disabled, warning, and error states visually distinct?
- [ ] Are tests updated for important layout text, truncation, and responsive behavior?

## Anti-patterns

Avoid:

- New one-off color palettes.
- Heavy boxes around every element.
- Dense dashboards that obscure the primary action.
- Repeating global controls in every panel.
- Long prose in persistent UI chrome.
- Hard-coded terminal widths or unbounded strings.
- Treating the wide right column as required functionality on narrow terminals.

If in doubt, make the UI quieter, more spacious, and closer to Simple Chat.
