# Memory Management Tab Implementation Plan

## Goal

Replace the current modal-style Memory Approvals popup with a first-class `Memory Management` tab in `agent-communicator-tui`. The tab should manage pending and active memory from the existing `broccoli-comms memory ...` CLI/API surface while following the Simple Chat layout patterns in `DESIGN.md`.

## Current scope to replace

Current implementation lives primarily in:

- `memory_manager.go`: loads `memory approvals --json`, renders a centered popup, handles `a/e/d/r` actions.
- `memory_actions.go`: defines `memoryRecord` and selected-message memory actions.
- `palette.go`: exposes `Memory Approvals` as a command-palette popup action.
- `app.go`, `view.go`, `update_key.go`: hold popup state and route key/input handling.

The replacement should keep existing backend action behavior working but move browsing and actions into a persistent tab instead of a modal overlay.

## DESIGN.md patterns to follow

- Use the bottom tab system for global navigation; add a registered tab rather than another overlay.
- On wide screens (`>= 70`), use a two-column shell: primary memory list/content on the left, filters/details/actions in the right column.
- On narrow screens, render only the primary memory panel and avoid horizontal scrolling.
- Use shared tokens only: `colors.BaseBg`, `colors.RightColumnBg`, `colors.PanelBg`, `colors.PanelBgAlt`, `colors.InputBg`, `colors.SelectedBg`, `colors.SelectedFg`, `colors.Muted`, `colors.Success`, `colors.Warning`, `colors.Error`.
- Use Simple Chat selection language: selected rows use `SelectedBg/SelectedFg`, concise hints, stable scroll keys, and full-width background-safe lines.
- Keep persistent chrome quiet; put global feedback in status/error lines above the bottom tabs.

## Proposed tab UX

### Tab entry

- Add a `memoryView` mode and a registered tab:
  - Label: `Memory Management`
  - Short label: `Memory`
  - Help: `review and maintain durable memory`
  - `CanCompose: false`
  - Load command: `loadMemoryManagementCmd()`
- The command-palette `Memory Approvals` action should switch to this tab and load memory, instead of opening the popup.

### Data model and CLI/API calls

Initial low-risk implementation should reuse the existing payload:

- `broccoli-comms memory approvals --json`
  - `pending`: pending proposals
  - `approved`: active/approved memories

Actions continue using existing trusted CLI wrappers:

- New memory proposal:
  - `memory propose --type <type> --title <title> --body <body> --source-task <task> --agent <agent> --json`
  - Optional fields: `--scope`, `--subject-agent`, repeated `--tag`, `--metadata-json`, and `--trusted-manual` only when the local trusted path is explicitly available/appropriate.
- Pending memory:
  - approve: `memory approve <id> --expected-version <version> --json`
  - reject/delete: `memory reject <id> --expected-version <version> --json --reason ...`
  - Delete semantics: pending memory is rejected, not revoked.
- Active memory:
  - revoke/delete: `memory revoke <id> --expected-version <version> --json --reason ...`
  - Delete semantics: active memory is revoked, not rejected.
  - rollback: `memory rollback <id> --to-version <version-1> --expected-version <version> --json`
  - edit: editor-backed flow using `$EDITOR` (default `nvim`) that writes title/body to a temporary file and submits `memory edit <id> --title <title> --body <body> --expected-version <version> --json` after the editor exits successfully. The earlier in-tab edit/propose-edit form plan is superseded by the user clarification that all edit operations must use EDITOR/nvim.

Initial loading can reuse `memory approvals --json` for pending and active records. If that payload is insufficient for full management UX (for example missing revoked/superseded records, omitted active memory due budget, or search across all memory), the tab should switch the relevant phase to `memory list --status <status> --type <type> --agent <agent> --json` and/or `memory search --query <query> --json` instead of expanding the TUI with incomplete data.

### Primary content layout

Left/primary column:

1. Title: `Memory Management`
2. Filter/search strip using `colors.InputBg`:
   - query text
   - status filter (`all`, `pending`, `active`)
   - type filter if implemented in phase 2
3. Scrollable memory rows:
   - line 1: status badge, memory id, type, agent, version
   - line 2: title or fallback id, truncated
   - selected row uses `SelectedBg/SelectedFg`
   - pending rows can include a warning/accent marker; active rows can include success/neutral marker
4. Empty/error states:
   - `No memory records match this filter.`
   - `Memory load failed · r retry`

Right column on wide screens:

1. Selected memory detail card:
   - title
   - id/status/type/scope/agent/version
   - source task if available later
2. Body preview:
   - wrapped text, capped to available height
3. Action help:
   - pending: `a approve · d reject · e edit in editor`
   - active: `d revoke · R rollback · e edit in editor` when version > 1; show rollback unavailable/no previous version when version is 1
   - creation: `n new memory`
   - global: `/ search · s status · c clear · r refresh`
4. Destructive confirmation strip when needed:
   - first `d` on pending sets `confirmAction=reject`; second `d` confirms, `esc` cancels.
   - first `d` on active sets `confirmAction=revoke`; second `d` confirms, `esc` cancels.
   - first `R` sets `confirmAction=rollback`; second `R` confirms, `esc` cancels.
   - Use concise copy such as `confirm reject mem-123 · d confirm · esc cancel`.

Narrow screens:

- Hide the right column.
- Include a compact selected-memory preview below the list or inline under the selected row, capped to 2-3 lines.
- Use compact bottom tab label `Memory`.

### Keyboard interactions

- `ctrl-y` / `ctrl-t`: keep existing tab switching behavior.
- `up/down` or `ctrl-p/ctrl-n`: move selected memory row.
- `ctrl-u/ctrl-d`: page the memory list.
- `/`: focus search/filter input.
- `esc`: leave search mode, cancel a form, or cancel an in-progress confirmation; it should not close the tab.
- `r`: refresh memory list when not editing/searching.
- `n`: open the new-memory form.
- `a`: approve pending memory only.
- `d`: start/confirm delete for selected memory; pending means reject, active means revoke.
- `e`: open the selected memory in `$EDITOR`, defaulting to `nvim` when `EDITOR` is unset. Do not open an in-tab edit/propose-edit form.
- `R`: start/confirm rollback of active memory to previous version.

### New memory form

`n` opens an in-tab form that follows the existing composer/form visual pattern (`colors.InputBg`, selected field highlight, short help line). The form should be keyboard-first and cancellable with `esc`.

Fields:

1. `type`: one of `fact`, `habit`, `episode`, `expertise`, `skill`.
2. `title`: required, non-empty.
3. `body`: required, multi-line via editor or textarea-style field; preserve newlines.
4. `agent` / proposer: defaults to the current/own agent where available; used for `--agent`.
5. `subject-agent`: optional target agent for scoped memories.
6. `tags`: optional comma-separated tags, emitted as repeated `--tag` flags.
7. `source task`: required unless using an explicitly trusted manual path; default to selected/current task when available.
8. `trusted path`: explicit yes/no toggle for `--trusted-manual`; only enable in local trusted-user contexts, never silently.

Submit behavior:

- Validate required fields before invoking CLI; show inline errors in the status strip.
- Build `broccoli-comms memory propose ... --json` with only populated optional fields.
- On success, close the form, refresh memory records, and show `memory proposed` status.
- On error, keep the form open and show the CLI error without discarding user input.

### Editor-backed edit flow

Supersedes the earlier in-tab edit/propose-edit form plan. `e` opens the selected memory in `$EDITOR`, defaulting to `nvim` when `EDITOR` is unset, because the user clarified that all Memory Management edit operations must use the external editor flow.

Behavior:

- Create a temporary edit file containing the selected title, a stable `--- body ---` separator, and the selected body.
- Run `$EDITOR <tempfile>` or `nvim <tempfile>` when `EDITOR` is unset.
- After the editor exits successfully, parse the title/body around the separator and submit `memory edit <id> --title <title> --body <body> --expected-version <version> --json`.
- On success, refresh memory records.
- On editor/parse/CLI error, show the error without opening an inline edit form.
- There is no in-tab `propose-edit` shortcut in this implementation; the stale proposal-edit form/help/tests are removed rather than left reachable.
- Tests should cover editor command selection/default `nvim`, the tab `e` path returning an editor command without opening a form, and the absence of stale propose-edit help.

### Destructive confirmations

Do not perform reject, revoke/delete, or rollback on the first keypress. Use a lightweight in-UI confirmation state rather than a separate heavy modal:

- `d` on pending: show `confirm reject <id> · d confirm · esc cancel`.
- `d` on active: show `confirm revoke <id> · d confirm · esc cancel`.
- `R` on active version > 1: show `confirm rollback <id> to v<version-1> · R confirm · esc cancel`.
- Any selection movement, search input, refresh, form open, or `esc` cancels confirmation.
- Tests should prove first keypress does not call CLI and second matching keypress does.

## Low-risk implementation phases

### Phase 1 — Design artifact only

Deliver this plan and request review before coding. No UI code changes beyond the markdown plan.

Validation:

```bash
git -C /Users/tanmayvijay/broccoli-comms diff -- agent-communicator-tui/MEMORY_MANAGEMENT_TAB_PLAN.md
```

### Phase 2 — Tab registration and routing skeleton

- Add `memoryView` to `viewMode`.
- Register `Memory Management` in `registeredAppTabs`.
- Replace command-palette popup action with `setMode(memoryView)` and `loadMemoryManagementCmd()`.
- Keep the old popup code temporarily for easy rollback, but stop opening it from the palette.
- Add tests for tab registration, palette switching, and composer-disabled behavior.

Validation:

```bash
nix develop --command bash -lc "cd agent-communicator-tui && go test ./..."
```

### Phase 3 — Data loading and list state

- Rename or wrap `loadMemoryApprovalsCmd()` as `loadMemoryManagementCmd()` while preserving current CLI args.
- Add state for memory query/filter/offset/selection without overloading message scroll state.
- Add filtering helpers by status, type, agent, id, and title/body substring.
- If `memory approvals --json` lacks records needed by filters/search, switch loading to `memory list --status ... --type ... --agent ... --json` or `memory search --query ... --json` for that filter path.
- Add tests for loading, filtering, list/search fallback command selection, selection clamping, and scroll bounds.

Validation:

```bash
nix develop --command bash -lc "cd agent-communicator-tui && go test ./..."
```

### Phase 4 — Full tab view

- Implement `memoryManagementView(width, height)` using Simple Chat layout rules.
- On wide screens, render list + right details/action column.
- On narrow screens, render primary list + compact selected preview only.
- Use background-safe helpers (`padStyledLine`, `fgOnBg`, `bgSpaces`) for every non-base background.
- Add layout tests for key text, selected-row styling markers, truncation, and narrow behavior.

Validation:

```bash
nix develop --command bash -lc "cd agent-communicator-tui && go test ./..."
```

### Phase 5 — New memory form, editor-backed editing, actions, and confirmations

- Add `n new memory` form state and rendering.
- Build `memory propose ... --json` from validated fields: type/title/body/agent or subject-agent/tags/source task/trusted path.
- Keep edit operations editor-backed: `e` opens `$EDITOR`/`nvim`, parses the edited temp file, and submits `memory edit ... --expected-version ... --json`; do not add an in-tab edit/propose-edit form.
- Reuse `memoryManagerActionCmd` for approve/reject/revoke/rollback command execution.
- Route tab keys to memory actions only when `mode == memoryView`.
- Add lightweight confirmation state for reject/revoke/delete and rollback before invoking CLI.
- Refresh memory after successful actions and preserve selection where possible.
- Add tests for propose command args, new required-field validation, CLI errors preserving new-form input, editor command selection/default `nvim`, tab `e` launching editor without opening an inline form, approve command args, pending delete=reject, active delete=revoke, rollback args/help availability, and confirmation first/second key behavior.

Validation:

```bash
nix develop --command bash -lc "cd agent-communicator-tui && go test ./..."
```

### Phase 6 — Remove popup-specific state and polish

- Remove `showingMemoryApprovals` overlay routing once the tab reaches parity.
- Rename user-facing labels from `Memory Approvals` to `Memory Management` where appropriate.
- Keep slash `/memory approve|reject|edit` commands for message-card workflows unless a separate task explicitly removes them.
- Update tests that currently expect popup behavior.

Validation:

```bash
nix develop --command bash -lc "cd agent-communicator-tui && go test ./..."
```

## Out of scope for first implementation chain

- Backend schema changes.
- Bulk memory operations.
- Full memory history diff viewer.
- Heavy modal confirmation dialogs; use the lightweight in-tab confirmation state described above instead.
- Replacing `/memory` slash commands used in message cards.

## Review checklist

- The tab follows `DESIGN.md` Simple Chat layout and tokens.
- Existing memory approve/edit/delete/rollback behavior remains covered by tests, including pending delete=reject and active delete=revoke semantics.
- Editor-backed edit flow is covered by tests for `$EDITOR`/default `nvim` selection, tab `e` launching the editor path without opening an inline form, and stale propose-edit help/form paths staying removed.
- New memory proposal flow is covered by tests for form validation and `memory propose ... --json` CLI args.
- Destructive action confirmation is covered by tests: first keypress arms confirmation, second matching keypress invokes CLI, `esc` cancels.
- The popup is replaced only after tab parity exists.
- Narrow terminals remain usable without horizontal scrolling.
- Validation command remains `nix develop --command bash -lc "cd agent-communicator-tui && go test ./..."` for implementation phases.
