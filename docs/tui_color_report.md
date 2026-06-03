# Broccoli Comms TUI Color/Background Debug Report

Date: 2026-06-03
Scope: `agent-communicator-tui` Go Bubble Tea/Lip Gloss UI.

## Verification

- Static audit of all `Foreground(...)`, `Background(...)`, `BorderForeground(...)`, and theme role usages in `agent-communicator-tui/*.go`.
- Test run: `cd agent-communicator-tui && nix develop . -c go test ./...` passes.

## Active theme

Runtime uses the Tokyo Night truecolor theme:

- `agent-communicator-tui/palette.go:44`: `var colors = tokyoNightTerminalTheme()`
- Theme values live in `agent-communicator-tui/theme.go`.

Key theme roles:

| Role | Hex | Use |
|---|---:|---|
| `BaseBg` | `#1a1b26` | Main chat/conversation background |
| `PanelBg` | `#1f2335` | Filter row, generic boxed panels |
| `PanelBgAlt` | `#24283b` | Unread agent cards and incoming message body highlight |
| `RightColumnBg` | `#24283b` | Agent/current-agent side column |
| `InputBg` | `#16161e` | Composer and command-palette query |
| `PopupBg` | `#16161e` | Command-palette modal/scrim |
| `SelectedBg` | `#7aa2f7` | Selected agent/card/current hero/selected modal rows |
| `SelectedFg` | `#16161e` | Text on selected blue backgrounds |
| `Text` | `#a9b1d6` | Normal text |
| `TextStrong` | `#c0caf5` | Strong/unread text |
| `TextSubtle` | `#9aa5ce` | Section headers |
| `Muted` | `#737aa2` | Secondary metadata/help |
| `Accent` | `#7aa2f7` | Titles, selected message rail, prompt labels |
| `AccentAlt` | `#bb9af7` | Shell/app title and code keywords |
| `Success` | `#9ece6a` | Online status, strings, active tab bg |
| `Warning` | `#e0af68` | Unread badge bg, code text, warnings |
| `Error` | `#f7768e` | Failed status/errors/cancel bg |
| `Info` | `#7aa2f7` | Links, selected save button, sent-message logical border color |
| `Saved` | `#e0af68` | Saved-star marker/logical saved border |

`defaultTerminalTheme()` in `palette.go` is not active at runtime. It is an ANSI-index fallback/test fixture. It still uses explicit ANSI background indexes (`0`, `8`, etc.), not transparent terminal background.

## Component coloring map

### Top-level layout

- Desktop layout: `baseView()` joins `conversationPanel()` and `rightColumn()` horizontally.
- Narrow/mobile layout (`width < 70`): renders only `conversationPanel()`.
- No root-level full-screen wrapper is applied outside those panels, so full-screen coverage depends on each panel's own `Width`/`Height` background.

### Chat / conversation window

Location: `agent-communicator-tui/view.go:136-158`

- Outer chat panel: explicit `Background(colors.BaseBg)` with `Width(width)`, `Height(height)`, padding.
- Title: `titleStyle` = `Accent` foreground, bold, no own background.
- Message viewport: no own background; visually relies on outer chat `BaseBg`.
- Empty-state text: `mutedStyle` foreground only; relies on outer chat `BaseBg`.
- Composer is embedded at bottom and has its own `InputBg`.

### Message rows / bubbles

Location: `agent-communicator-tui/bubbles.go:13-50`

- Rail: muted `┃`; selected message rail switches to `Accent` + bold.
- Header: `agentStyle(colorKey, true)` picks deterministic sender color from `AgentColors`.
- Sent/outgoing message body: no body background; relies on chat `BaseBg`.
- Incoming message body on wide terminals (`width >= 70`): explicit `PanelBgAlt` background with horizontal padding.
- Receipts: foreground-only (`ReadTick`, `DeliveredTick`, `SentTick`) and metadata muted; rely on chat `BaseBg`.
- `messageBorderColor()` and `renderBubble()` exist but `renderBubble()` is currently unused by the active renderer.

### Markdown inside messages

Location: `agent-communicator-tui/markdown.go`

- Links: `Info` foreground + underline.
- Inline/code block text: `Warning` foreground.
- Comments: `Muted` foreground + italic.
- Keywords: `AccentAlt` foreground + bold.
- Strings: `Success` foreground.
- Numbers: `Accent` foreground.
- Types: `Info` foreground + bold.
- Booleans/nulls: `Error` foreground + bold.
- Markdown styles do not set backgrounds; they inherit/rely on the message row background (`BaseBg` or `PanelBgAlt`).

### Composer

Location: `agent-communicator-tui/view.go:14-16`, `view.go:623-671`

- Desktop composer: `composerBoxStyle` = `InputBg` background + `Text` foreground + padding `(1,2)`.
- Mobile composer: `mobileComposerBoxStyle` = `InputBg` background + padding `(1,1)`; no explicit foreground on the box, but inner text styles set colors.
- Composer mode prefix (`/msg`, `/text`, `/keys`): `InputBg` background + `Accent` foreground + bold.
- Cursor: `selectedStyle` = `Success` foreground + bold.
- Placeholder/help lines: `Muted` foreground; inside composer box.

### Right column

Location: `agent-communicator-tui/view.go:61-72`

- Composed of current-agent panel, switcher panel, and registry status line.
- Registry status line: explicit `RightColumnBg` background + `Muted` foreground.

### Current-agent card / hero

Location: `agent-communicator-tui/view.go:75-100`

- Panel background: `RightColumnBg`.
- App title: `shellTitleStyle` = `AccentAlt` foreground + bold.
- Host metadata: `Muted` foreground.
- Status dot: semantic foreground only (`Success`, `Warning`, `Error`, or `Muted`).
- Hero block: `SelectedBg` background + `SelectedFg` foreground + bold.
- Status badge inside hero: `RightColumnBg` background + `Accent` foreground.
- Host/provider line inside hero: `SelectedFg` foreground + faint.

### Agent switcher panel

Location: `agent-communicator-tui/view.go:102-118`, `view.go:369-421`

- Panel background: `RightColumnBg`.
- Header title: `Accent` foreground + bold.
- Header count: `Muted` foreground.
- Filter row: explicit `PanelBg` background + `Muted` foreground.
- Group headings (`LOCAL`, `REMOTE`): `TextSubtle` foreground + bold.
- Empty/overflow hints: `Muted` foreground.

### `agentCard`

Location: `agent-communicator-tui/view.go:301-355`

Background selection:

1. Normal card: `RightColumnBg`.
2. Selected card: `SelectedBg`.
3. Unread, not selected: `PanelBgAlt`.

Text/details:

- Status dot: semantic foreground; detection-blocked overrides to `Error`.
- Name on selected card: `SelectedFg` foreground + bold.
- Name on unread card: `TextStrong` foreground + bold.
- Normal name: `Text` foreground.
- Hidden indicator `◌`: `Muted` foreground.
- Unread badge: `Warning` background + `SelectedFg` foreground + bold.
- Metadata line (`provider · host status`): `Muted` foreground.
- The outer card applies background over full card width with horizontal padding.

### Command palette

Location: `agent-communicator-tui/palette.go:292-359`

- Palette panel: `PopupBg` background + `PopupBorder` border.
- Query input: `InputBg` background + `Text` foreground.
- Normal command rows: `PopupBg` background + `Text` foreground.
- Category headings: `PopupBg` background + `TextSubtle` foreground + bold.
- Selected command row: `SelectedBg` background + `SelectedFg` foreground + bold.
- Subtitles/no results: `PopupBg` background + `Muted` foreground.
- Overlay replaces only the horizontal band around the palette with `PopupBg` scrim; the rest of the screen remains the base UI, not default terminal background.

### Prompt/config menus

Location: `agent-communicator-tui/view.go:816-883`

- Both render through `box()`, which uses `panelBoxStyle`: `PanelBg` background + horizontal padding.
- Prompt/config normal rows: `Text` foreground.
- Selected row: `SelectedBg` background + `SelectedFg` foreground.
- Prompt empty warning: `Warning` foreground.
- Config empty error: `Error` foreground.
- Config scope prefix: local uses `Success`; remote/default uses `Muted`.

### Save-agent form

Location: `agent-communicator-tui/save_form.go:134-179`

- Form box: rounded border with `Info` border foreground, padding, width 60.
- The form box does **not** set a background.
- Focused label: `Info` foreground.
- Active Save button: `Info` background + `BaseBg` foreground.
- Active Cancel button: `Error` background + `BaseBg` foreground.
- Inactive buttons: border with `Muted` foreground, no background.

## Where default/transparent terminal background is used

The active main layout mostly paints explicit backgrounds (`BaseBg`, `RightColumnBg`, `InputBg`, `PopupBg`). The places that intentionally or accidentally use transparent/default terminal background are:

1. Initial loading state: `View()` returns raw `"loading..."` before dimensions are known (`view.go:24-26`).
2. Save-agent form: `renderSaveForm()` has a colored border but no background on the box; outside and inside unstyled gaps use terminal default (`save_form.go:134-179`).
3. Prompt/config menu outer margins: `box()` renders a `PanelBg` rectangle smaller than the full requested screen (`view.go:773-779`); remaining terminal area can stay default.
4. Foreground-only shared styles (`titleStyle`, `mutedStyle`, `sectionHeaderStyle`, `agentStyle`, status dots, markdown styles) have no background of their own. In normal panels they visually rely on the parent panel background.
5. Sent message bodies, message rails/headers, receipts, and markdown spans do not set backgrounds directly; they rely on the conversation panel `BaseBg`.
6. `renderBubble()` is unused, but if re-enabled it draws foreground-only borders/cells without background.
7. `footer()`/`runtimeStatusLine()` styling is foreground-only; it is not included in the current `baseView()` path but would need a parent background if reintroduced.

## Debug finding / risk

Because many child spans are foreground-only and rendered with Lip Gloss inside a parent that supplies the background, visual correctness depends on ANSI nesting behaving as expected. If a nested foreground style emits a reset that clears the parent background before the line ends, small patches may show the terminal's real default background. The safest places to harden are message rows and modal forms, because they have many nested styled fragments.

Recommended hardening if background leaks are visible:

- Give `renderSaveForm()` a `Background(colors.PopupBg)` or wrap it in a full-screen `BaseBg`/`PopupBg` overlay.
- Make `box()` return a full `Width(w).Height(h)` background, or wrap prompt/config menus in `BaseBg`.
- For chat message lines, render complete rows through a style with `Background(colors.BaseBg)`; for incoming highlighted bodies use `PanelBgAlt` only on the intended segment.
- Avoid relying on foreground-only child styles for padding/fill regions that should have a fixed background.
