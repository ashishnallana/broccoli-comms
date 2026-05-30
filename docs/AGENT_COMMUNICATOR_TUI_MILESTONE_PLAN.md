# Agent Communicator TUI redesign — milestone plan

## Coordination model

Lead agent: `broccoli-comms-agent-1`

Working agents:

- Coder: `tui-redesign-coder` — implements code only for the currently dispatched milestone.
- Reviewer: `tui-redesign-reviewer` — reviews coder diffs/tests and sends approve/blocking feedback.

Rules:

1. Only the lead dispatches new milestones.
2. The coder must not start the next milestone until the lead explicitly sends the next dispatch.
3. The lead does not perform code review. The reviewer owns code review.
4. The lead may run smoke tests, inspect command results, capture TUI panes, and coordinate retries, but should not approve code quality.
5. Each milestone must preserve existing behavior unless the milestone explicitly changes it.
6. Prefer small commits per milestone. Commit message prefix: `feat(tui):`, `fix(tui):`, or `test(tui):`.
7. Required baseline test for every milestone touching Go TUI code:

```sh
(cd agent-communicator-tui && go test ./...)
```

8. Required baseline test for milestones touching Python tracker/registry code:

```sh
python -m pytest agent-tracker agent-registry
```

9. Major UI milestones require an interactive smoke pass using tracker pane tools against `agent-communicator` or a freshly launched TUI:

```sh
agent-tracker-ctl capture-pane agent-communicator --last 100 --format text
agent-tracker-ctl send-key agent-communicator Tab
agent-tracker-ctl send-key agent-communicator Down
agent-tracker-ctl send-key agent-communicator Enter
agent-tracker-ctl capture-pane agent-communicator --last 100 --format text
```

Use only safe navigation keys for smoke testing unless a milestone explicitly requires send behavior.

---

## Milestone sequence

The sequence intentionally converts the current UI shell first, then adds richer backend-backed features incrementally.

### M0 — assignment, branch, and baseline snapshot

Goal: establish a clean baseline and avoid accidental unrelated work.

Coder tasks:

- Confirm current branch and working tree status.
- Run TUI tests:

```sh
(cd agent-communicator-tui && go test ./...)
```

- Capture current TUI visual baseline:

```sh
agent-tracker-ctl capture-pane agent-communicator --last 120 --format text > /tmp/agent-communicator-before-m1.txt || true
```

- Create branch:

```sh
git checkout -b feat/tui-redesign-m1-shell
```

Reviewer tasks:

- Stay idle until coder reports M1 ready for review.

Acceptance:

- Baseline test result and visual baseline path are reported to lead.

### M1 — new UI shell using existing data only

Goal: make the current TUI look like the proposed new UI without requiring tracker/registry API changes.

Scope:

- `agent-communicator-tui/view.go`
- `agent-communicator-tui/style.go`
- small helper files/tests as needed

Features:

- Replace the current two-column visual treatment with the new shell:
  - left sidebar with section headers,
  - main conversation column,
  - persistent status/error footer,
  - composer area with persistent mode hint line.
- Use existing `agentRow` fields only:
  - model badge can be derived temporarily from `AgentCmd` / `agent_type` equivalent already available in rows,
  - machine grouping can use existing `Scope` / `Hostname` / `TargetAddress` fallbacks,
  - status dot can use existing `Status`,
  - unread can use existing boolean unread state.
- Replace ambiguous `hidden` divider with explicit `Hidden` / `Filtered` label and count where possible.
- Keep all existing keybindings and send semantics unchanged.
- Keep narrow/mobile rendering functional.

Non-goals:

- No backend changes.
- No new tracker RPCs.
- No behavior change for sending messages, direct text, direct keys, save, config, prompts, hidden agents, or message read status.

Tests:

```sh
(cd agent-communicator-tui && go test ./...)
```

Major milestone smoke test:

```sh
agent-tracker-ctl capture-pane agent-communicator --last 100 --format text
agent-tracker-ctl send-key agent-communicator Tab
agent-tracker-ctl send-key agent-communicator Down
agent-tracker-ctl send-key agent-communicator Enter
agent-tracker-ctl capture-pane agent-communicator --last 100 --format text
```

Acceptance:

- Existing tests pass.
- TUI renders the new shell from existing data.
- Existing interactions still work.
- Reviewer approves the diff.

### M2 — formal TUI view models and style tokens

Goal: de-risk later features by separating data derivation from rendering.

Scope:

- TUI-only.
- Add small view-model helpers, not a full rewrite.

Features:

- Add helper/view types such as `AgentView`, `MachineGroup`, `MessageView`, and `UIError` inside the current package.
- Centralize badge/status styles in `style.go` or a new `styles` helper file.
- Keep current `model` as the Bubble Tea root for now.
- Add unit tests for:
  - model badge mapping,
  - grouping rows by machine,
  - hidden count derivation,
  - status dot mapping.

Acceptance:

- No backend changes.
- TUI shell still works.
- Tests cover core derivations.
- Reviewer approves.

### M3 — tracker/registry metadata contract: `model_type` and machine fields

Goal: stop the UI from guessing model and machine identity.

Scope:

- `wrapper/agent-wrapper.sh`
- `agent-tracker/state.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/registry_client.py`
- `agent-registry/server.py`
- `agent-communicator-tui/internal/tracker/types.go`
- `agent-communicator-tui/agent_list.go`

Features:

- Add canonical `model_type`.
- Normalize from explicit param, `agent_type`, or command basename.
- Include `model_type` in local list responses, registry heartbeat/register payloads, registry `GET /agents`, and merged remote rows.
- Ensure local rows include `hostname`, `tracker_id`, and `scope: local`.
- Ensure remote rows preserve `hostname`, `tracker_id`, and registry name.
- Update TUI to prefer `model_type` and fall back to M1/M2 inference.

Tests:

```sh
python -m pytest agent-tracker agent-registry
(cd agent-communicator-tui && go test ./...)
```

Acceptance:

- Existing JSON clients still work; only additive fields.
- Sidebar badges/grouping use canonical metadata when available.
- Reviewer approves.

### M4 — communicator mailbox startup and actionable errors

Goal: eliminate raw missing-mailbox failures and make errors visible/actionable.

Scope:

- TUI client/startup.
- Tracker JSON-RPC error data where necessary.

Features:

- Add Go client method for `ensure_mailbox`.
- Call it for `ownName` on startup before first inbox read.
- Add typed/structured RPC error handling in Go client while preserving raw error strings.
- Render persistent error bar using existing/typed error data.
- Add retry keybinding `r` for the currently failing load/health operation.

Tests:

```sh
(cd agent-communicator-tui && go test ./...)
python -m pytest agent-tracker agent-registry
```

Major milestone smoke test:

- Start/refresh TUI with `agent-communicator` missing or no inbox available if easy to simulate.
- Confirm the UI does not bury a raw `get_inbox failed` string as the only feedback.

Acceptance:

- TUI startup is stable outside an agent pane.
- Error bar is visible and retryable.
- Reviewer approves.

### M5 — message attribution and sender metadata

Goal: conversation pane clearly shows who said what.

Scope:

- TUI message rendering.
- Tracker/registry message enrichment.

Features:

- Add optional message fields:
  - `sender_hostname`,
  - `sender_model_type`,
  - `sender_agent_type`,
  - `sender_agent_cmd`,
  - `kind`.
- Enrich local sends from tracker state.
- Preserve sender metadata through registry remote delivery.
- TUI message header uses sender badge + sender name + hostname + timestamp.
- User/outbox messages remain visually distinct from inbound agent messages.
- Legacy messages still render.

Tests:

```sh
python -m pytest agent-tracker agent-registry
(cd agent-communicator-tui && go test ./...)
```

Acceptance:

- New messages include metadata.
- Legacy inboxes still render.
- Reviewer approves.

### M6 — unread counts and next-unread navigation

Goal: make multi-agent activity visible.

Scope:

- Tracker unread count RPC or list augmentation.
- TUI sidebar and navigation.

Features:

- Add `get_unread_counts` RPC preferred, or additive `include_unread_for` option on list.
- Count by stable sender keys:
  - local: `agent_id`,
  - remote: `tracker_id + agent_id`.
- Sidebar renders count badges, not only a boolean dot.
- Add `n` keybinding for next unread while preserving existing `ctrl-n` behavior.

Tests:

```sh
python -m pytest agent-tracker agent-registry
(cd agent-communicator-tui && go test ./...)
```

Acceptance:

- Counts drop when conversation is read.
- Same-name remote agents do not collide.
- Reviewer approves.

### M7 — health/status bar and system events

Goal: status bar and conversation system rows reflect tracker/registry lifecycle.

Scope:

- Tracker health snapshot RPC or extension to existing tracker info/list trackers.
- TUI status bar.
- Event rendering.

Features:

- Add UI-friendly health snapshot for local tracker, registries, and remote trackers.
- Publish/consume lifecycle events:
  - `agent_registered`,
  - `agent_unregistered`,
  - `agent_status_changed`,
  - `message_delivered`,
  - `message_read`,
  - `remote_agent_event`.
- TUI renders system events as dashed annotation rows.
- Status bar shows active agent + model + machine, RPC health, online/total count, current time.

Tests:

```sh
python -m pytest agent-tracker agent-registry
(cd agent-communicator-tui && go test ./...)
```

Major milestone smoke test:

```sh
agent-tracker-ctl registry-status
agent-tracker-ctl capture-pane agent-communicator --last 120 --format text
agent-tracker-ctl send-key agent-communicator Tab
agent-tracker-ctl send-key agent-communicator Down
agent-tracker-ctl send-key agent-communicator Enter
agent-tracker-ctl capture-pane agent-communicator --last 120 --format text
```

Acceptance:

- Health degrades gracefully when registry/remote tracker is unavailable.
- System rows do not break message scrolling.
- Reviewer approves.

### M8 — input modes as real tabs and optional broadcast

Goal: complete the proposed input UX.

Scope:

- TUI input model.
- Optional tracker broadcast RPC if enabled in this milestone.

Features:

- Persistent tabs for `/msg inbox`, `/text`, `/key`, and `/broadcast`.
- F1-F4 or tab cycling for input modes if Bubble Tea terminal support is reliable.
- Sending context line: target name + model + machine.
- Keep direct pane input remote gates unchanged.
- If broadcast backend is implemented, return per-target results and surface partial failures.
- If broadcast backend is not implemented, tab is visible but disabled with clear help text.

Tests:

```sh
python -m pytest agent-tracker agent-registry
(cd agent-communicator-tui && go test ./...)
```

Acceptance:

- Normal Enter behavior remains safe and expected.
- Direct text/key modes remain explicit.
- Broadcast cannot accidentally send without explicit mode.
- Reviewer approves.

### M9 — polish, docs, and final integration

Goal: finish documentation and prepare merge.

Tasks:

- Update `docs/RUNTIME_API.md` with new additive fields/RPCs.
- Update README/TUI usage notes if keybindings changed.
- Run full tests.
- Run final TUI smoke capture/send-key pass.
- Reviewer performs final review.

Acceptance:

- Docs match implemented behavior.
- Tests pass.
- Major TUI interactions are smoke-tested.
- Reviewer approves final merge readiness.
