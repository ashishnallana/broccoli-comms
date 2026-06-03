# TUI Background Hardening Task List

Date: 2026-06-03
Scope: remove accidental/default terminal background leaks from `agent-communicator-tui`.

## Current state re-check

- Existing color report: `docs/tui_color_report.md`
- Tests currently pass:
  - `cd agent-communicator-tui && nix develop . -c go test ./...`
- Only current uncommitted artifact from this investigation is documentation.

## Root cause

Many components apply a background only on an outer Lip Gloss container, then insert child strings that have their own ANSI styles. Those child styles often end with ANSI reset (`\x1b[0m`), which clears the parent background. Any raw spaces or foreground-only text after that reset can render on the terminal's default background.

This is visible in:

- Composer/input box: raw gaps and cursor/text segments inside the `InputBg` box.
- Agent card: status dot, name, separator spaces, hidden indicator, metadata text.
- Message timeline: rail/header/body/receipt lines, especially outgoing messages and headers.

General rule for the fix: **any rendered segment that appears inside a colored region must either have the intended background itself, or be composed as plain text first and then styled once as a full line with background.** Do not rely only on parent background for nested styled spans.

---

## P0 tasks: visible leaks reported by user

### 1. Harden composer/input box background

Files:

- `agent-communicator-tui/view.go`
- Tests: `agent-communicator-tui/composer_wrap_test.go` or new `background_test.go`

Problem areas:

- `composerBoxStyle` has `Background(colors.InputBg)`, but `composerView()` returns nested styled pieces.
- `composerPrefix()` sets `InputBg`, but the raw space after prefix and cursor/placeholder styles can reset to default background.
- `selectedStyle` cursor currently has foreground only.
- `mutedStyle` placeholder/help text has foreground only.

Implementation tasks:

- Add a helper like:
  - `styleWithBg(style lipgloss.Style, bg lipgloss.Color) lipgloss.Style`
  - or dedicated styles: `composerTextStyle`, `composerMutedStyle`, `composerCursorStyle`, all with `Background(colors.InputBg)`.
- In `composerLines()` ensure every segment has `InputBg`:
  - prefix label background: `InputBg`
  - separator spaces: `InputBg`
  - typed text: `InputBg` + `Text`
  - cursor: `InputBg` + `Success` or `Accent`
  - placeholder: `InputBg` + `Muted`
  - right-side padding/fill: `InputBg`
- Prefer building each composer line through a full-width renderer:
  - `renderComposerLine(content string, width int) string`
  - It should fill to width with spaces styled as `InputBg`.
- Apply same fix to mobile composer path.

Acceptance criteria:

- Every visible cell inside composer box uses `InputBg`.
- No raw unstyled spaces between `/msg`, cursor, typed text, placeholder, and padding.
- Existing composer wrapping tests still pass.

Suggested tests:

- Render `m.composerInputBox(40)` with empty composer and non-empty composer.
- Assert that typed text/cursor/placeholder are rendered with `InputBg` in ANSI output.
- Add a helper that detects known leak patterns such as `\x1b[0m ` in the middle of colored components, or more robustly verifies all printable spaces in a component are inside an active background span.

---

### 2. Harden `agentCard` background, including agent-name background

Files:

- `agent-communicator-tui/view.go` (`agentCard`)
- `agent-communicator-tui/style.go` (`agentStatusDotStyle`, shared helpers)
- Tests: `agent-communicator-tui/agent_card_test.go`

Problem areas:

- Outer card style sets `Background(bg)`, but child segments reset it:
  - `agentStatusDotStyle(row).Render("●")`
  - raw separator space after dot
  - `nameStyle.Render(...)`
  - `mutedStyle.Render(" ◌")` hidden marker
  - `unreadCountBadge(...)`
  - metadata line via `mutedStyle`
- This causes agent-name and metadata cells to show terminal default background.

Implementation tasks:

- Make `agentCard` pass the resolved card background (`bg`) into all child segment styles.
- Add local helpers in `agentCard`:
  - `cardFg(fg lipgloss.Color) lipgloss.Style { return lipgloss.NewStyle().Foreground(fg).Background(bg) }`
  - `cardFill(width int) string { return lipgloss.NewStyle().Background(bg).Render(strings.Repeat(" ", width)) }`
- Render status dot with both foreground and `Background(bg)`.
- Render separator spaces with `Background(bg)`.
- Render name text with `Background(bg)` in all states:
  - selected: `SelectedFg` + bold + `bg`
  - unread: `TextStrong` + bold + `bg`
  - normal: `Text` + `bg`
- Render hidden indicator with `Muted` + `bg`.
- Render metadata with `Muted` + `bg`.
- Keep unread badge intentionally on `Warning` background, but ensure adjacent spaces return to `bg`.
- Consider composing each card line from styled segments, then applying a final full-width background fill to any remaining cells.

Acceptance criteria:

- Normal, selected, and unread cards are solid filled.
- Agent-name text never appears on terminal default background.
- The unread badge remains visually distinct on `Warning`.
- Existing card width/height tests continue to pass.

Suggested tests:

- Render normal card, selected card, unread card, and hidden-marker card.
- Verify no raw unstyled separator spaces are emitted between dot/name/badge/meta.
- Verify line width remains exactly requested width.

---

### 3. Harden message timeline/message bubble backgrounds

Files:

- `agent-communicator-tui/bubbles.go`
- `agent-communicator-tui/view.go` (`messageViewWithHeight`, receipt helpers)
- `agent-communicator-tui/markdown.go` if markdown spans need parent background
- Tests: `agent-communicator-tui/bubbles_test.go`, `agent-communicator-tui/view_test.go`

Problem areas:

- Header line: rail is foreground-only; spaces after rail are raw; header text is foreground-only.
- Incoming body on wide terminals has `PanelBgAlt` only around the body segment; rail and leading spaces are default.
- Outgoing body has no background and relies on chat panel `BaseBg`.
- Receipts use foreground-only styles and rely on chat panel `BaseBg`.
- Markdown spans apply foreground only and may reset the surrounding message background.

Implementation tasks:

- Add message row helpers:
  - `messageBaseStyle := lipgloss.NewStyle().Background(colors.BaseBg).Foreground(colors.Text)`
  - `messageRailStyle(selected bool)` with `Background(colors.BaseBg)`.
  - `messageHeaderStyle(colorKey)` with `Background(colors.BaseBg)`.
  - `messageMutedStyle(bg)` for timestamps/receipts with an explicit background.
- In `messageBubbleLines()` ensure every line is explicitly backgrounded end-to-end:
  - rail cell: `BaseBg`
  - indentation spaces: `BaseBg`
  - header: `BaseBg`
  - outgoing body: `BaseBg`
  - receipts: `BaseBg`
  - incoming body highlight: body block `PanelBgAlt`, surrounding rail/indent `BaseBg`
- Do not rely on `messageViewWithHeight()` alone, because nested child resets can still clear backgrounds inside the line.
- For incoming body, style internal markdown/text fragments with `PanelBgAlt` or render plain markdown first then apply `PanelBgAlt` to the complete body line.
- For outgoing body, apply `BaseBg` to complete body text lines.
- Consider removing/deleting unused `renderBubble()` or updating it to accept explicit backgrounds if it may be reintroduced.

Acceptance criteria:

- Message header and body lines never show terminal default background.
- Incoming highlighted body remains `PanelBgAlt`.
- Outgoing body and receipts sit on `BaseBg`.
- Markdown links/code/keywords still color correctly without clearing the intended row background.

Suggested tests:

- Render incoming message at width `80`; inspect header and body ANSI.
- Render outgoing message with read receipt; inspect body and receipt ANSI.
- Render markdown message with links/code/table; verify styled spans are on intended background.
- Existing bubbleless timeline tests continue to pass.

---

## P1 tasks: other likely background leaks

### 4. Harden current-agent panel/hero

Files:

- `agent-communicator-tui/view.go` (`currentAgentPanel`)

Problem areas:

- `statusDot(status)` is foreground-only inside hero line.
- `statusBadge` has `RightColumnBg`, then surrounding spaces and `nameText` may rely on hero parent `SelectedBg`.
- `line2` has foreground-only `SelectedFg`/faint inside hero.

Tasks:

- Render hero-internal text/spaces with explicit `SelectedBg` unless intentionally part of a badge.
- Render `statusBadge` with `RightColumnBg`, but style adjacent gap spaces with `SelectedBg`.
- Ensure outer current-agent panel's non-hero text/gaps are `RightColumnBg`.

### 5. Harden switcher panel/header/filter/list gaps

Files:

- `agent-communicator-tui/view.go` (`switcherPanel`, `agentList`)

Problem areas:

- Header uses `JoinHorizontal` of title + raw spaces + muted count.
- Group headings are foreground-only.
- Blank lines between cards may be default background.

Tasks:

- Render header full width with `RightColumnBg`.
- Style header gap spaces with `RightColumnBg`.
- Style group headings and blank separator lines with `RightColumnBg`.
- Ensure ellipsis/no-agents lines have `RightColumnBg`.

### 6. Harden command palette overlay

Files:

- `agent-communicator-tui/palette.go`

Problem areas:

- Palette line builder uses `PopupBg`, but nested muted text in title line can reset background around raw spaces.
- Overlay only scrims rows touched by the palette, not the full screen.

Tasks:

- Render every palette line as a full-width `PopupBg` line.
- Style title-left, title-right, and gap spaces with `PopupBg`.
- Decide whether modal open state should full-screen-scrim with `PopupBg`/dimmed background or keep base UI visible.
- If full-screen no-default-background is required, wrap untouched rows/columns too.

### 7. Harden prompt/config menus and generic `box()`

Files:

- `agent-communicator-tui/view.go` (`box`, `renderPromptMenu`, `renderConfigMenu`)

Problem areas:

- `box()` renders a smaller panel; outside area can be default terminal background.
- Rows inside menus use foreground-only styles.

Tasks:

- Make modal/menu views render a full-screen `BaseBg` or `PopupBg` backdrop.
- Ensure `box()` content lines are full-width `PanelBg`.
- Style selected/normal row prefixes and gap spaces with explicit background.

### 8. Harden save-agent form

Files:

- `agent-communicator-tui/save_form.go`

Problem areas:

- Form border has `Info`, but no background.
- Labels and button gaps may use terminal default.
- Text input components may have their own default styling.

Tasks:

- Add `Background(colors.PopupBg)` or `Background(colors.PanelBg)` to the form box.
- Add a full-screen backdrop when `showingSaveForm` is true.
- Style labels, blank lines, and button gap with form background.
- Configure Bubble text inputs to use explicit prompt/text/cursor backgrounds if supported.

### 9. Harden status/footer/runtime lines if reintroduced

Files:

- `agent-communicator-tui/view.go` (`footer`, `runtimeStatusLine`, status helpers)

Tasks:

- If footer/status bar is displayed, give it a full-width explicit background.
- Ensure error/status text styles include that background.

---

## P2 architecture cleanup

### 10. Add reusable background-safe rendering helpers

Recommended new file:

- `agent-communicator-tui/background.go`

Possible helpers:

```go
func bgStyle(bg lipgloss.Color) lipgloss.Style
func fgBgStyle(fg, bg lipgloss.Color) lipgloss.Style
func renderBgSpaces(width int, bg lipgloss.Color) string
func renderFullBgLine(width int, bg lipgloss.Color, segments ...string) string
func renderSegment(text string, fg, bg lipgloss.Color, opts ...styleOpt) string
```

Design goals:

- Avoid repeated ad-hoc `lipgloss.NewStyle().Background(bg)` blocks.
- Make it easy to style raw spaces explicitly.
- Keep line widths stable after styling.

### 11. Add ANSI/background regression tests

Recommended new test file:

- `agent-communicator-tui/background_test.go`

Test strategy options:

1. Practical pattern-based tests:
   - Render target components.
   - Fail on known bad patterns like reset followed by raw spaces/text inside components.
2. Better state-machine tests:
   - Parse SGR sequences enough to track active background.
   - For each printable cell in critical components, assert `activeBackground != none`, except explicitly allowed newlines.
3. Golden-ish tests:
   - Force truecolor output via termenv/lipgloss profile.
   - Check critical substrings include `48;2;...` background codes.

Coverage targets:

- Composer empty and non-empty.
- Agent card normal/selected/unread/hidden.
- Message incoming/outgoing/markdown/receipt.
- Current-agent hero.
- Command palette.
- Save form.

### 12. Audit all shared styles for safe contextual use

Files:

- `agent-communicator-tui/style.go`
- `agent-communicator-tui/markdown.go`

Tasks:

- Keep global semantic styles foreground-only only when they are used in contexts where default background is acceptable.
- For colored panels, prefer contextual styles that include the panel background.
- Avoid using `mutedStyle`/`titleStyle` directly inside colored full-width regions unless wrapped with a background-specific variant.

---

## Recommended implementation order

1. Add background test helper/state-machine in `background_test.go`.
2. Fix composer/input box.
3. Fix `agentCard`.
4. Fix message timeline/bubbles and markdown-in-message spans.
5. Fix current-agent panel and switcher gaps.
6. Fix save form and modal/menu backdrops.
7. Fix command palette full-line/scrim behavior.
8. Run full tests and manually inspect in a terminal with a high-contrast default background.

## Manual QA checklist

Run locally:

```bash
nix build .#agentCommunicator
BROCCOLI_COMMS_AGENT_COMMUNICATOR_TUI=$PWD/result/bin/agent-communicator broccoli-comms ui
```

Use a terminal profile with an obvious contrasting background color, then verify:

- Composer has no default-background holes around `/msg`, typed text, cursor, placeholder, or padding.
- Normal/selected/unread agent cards are solid blocks.
- Agent names and metadata sit on card background.
- Message headers, rails, outgoing bodies, incoming highlighted bodies, receipts, and markdown spans have explicit backgrounds.
- Save form and command palette do not reveal default terminal background.
