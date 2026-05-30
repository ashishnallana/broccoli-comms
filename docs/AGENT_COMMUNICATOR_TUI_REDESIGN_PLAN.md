# Agent Communicator TUI redesign implementation plan

See also the milestone execution plan: [`AGENT_COMMUNICATOR_TUI_MILESTONE_PLAN.md`](./AGENT_COMMUNICATOR_TUI_MILESTONE_PLAN.md).

## Scope

Update the Go Bubble Tea `agent-communicator-tui` so multi-agent workflows make agent model, machine, health, unread state, and message attribution visible. The current repository does **not** have Go `tracker.go` / `registry.go` files as described in the draft; backend support lives in:

- `agent-tracker/` — Python Unix-socket JSON-RPC tracker plus local state/inbox files.
- `agent-registry/` — Python HTTP registry for remote trackers/agents/deliveries/events.
- `wrapper/agent-wrapper.sh` — records spawned agent metadata into tracker/tmux metadata.
- `agent-communicator-tui/` — existing Go TUI.

The UI chunks can proceed only after a small backend/API normalization pass, because the new screens require structured fields that should not be inferred from display names.

---

## Current backend support relevant to the new UI

Already present:

- Local tracker state stores stable `agent_id`, `name`, `status`, `agent_type`, `agent_cmd`, `tmux_pane`, `cwd`, `aliases`, and local inboxes.
- `agent-wrapper.sh` passes `agent_type` and `agent_cmd` during registration.
- Registry publishes remote agents with `agent_id`, `name`, `aliases`, `status`, `agent_type`, `agent_cmd`, `cwd`, `hostname`, `tracker_id`, and `last_seen`.
- Tracker `list` can merge remote registry agents when `include_remote` is set.
- Tracker messages already carry `sender`, `sender_agent_id`, `sender_tracker_id`, `message_id`, read/delivery flags, and timestamps.
- `ensure_mailbox` exists in tracker but is not wired into the Go TUI client/startup path.
- `wait_events`, registry tracker events, and remote watch leases exist for push-style updates.

Gaps to close:

- No explicit canonical `model_type`; UI would currently have to infer from `agent_type` / `agent_cmd`.
- Local `list` rows do not consistently include local `hostname` / `tracker_id` / tracker status.
- Message records do not denormalize sender model/machine metadata.
- Unread state is only a local TUI boolean, not a per-conversation count contract.
- Registry/tracker health is not exposed as one UI-friendly RPC contract.
- JSON-RPC errors return raw strings rather than typed UI-actionable error data.
- Agent lifecycle/status events are incomplete for system annotation rows.

---

## Backend/API additions required before or alongside UI chunks

### B0. Canonical agent model metadata

**Goal:** every agent row/message can render a stable badge: `Cl`, `Cx`, `Pi`, or `??`.

Files:

- `wrapper/agent-wrapper.sh`
- `agent-tracker/state.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/registry_client.py`
- `agent-registry/server.py`
- `agent-communicator-tui/internal/tracker/types.go`
- `agent-communicator-tui/agent_list.go`

Plan:

1. Add `model_type` as a first-class optional field on agent records.
2. Normalize it at registration time from, in order:
   - explicit `model_type` param,
   - `agent_type`,
   - command basename / `agent_cmd`.
3. Keep `agent_type` and `agent_cmd` for compatibility; treat `model_type` as UI-facing.
4. Include `model_type` in:
   - local `list` RPC responses,
   - registry heartbeat/register agent payloads,
   - registry `GET /agents`,
   - remote agents merged by tracker `list`.
5. Add Go fields on `tracker.Agent` and `ctlAgent`, copied into `agentRow`.

Initial mapping:

| Input | `model_type` | Badge |
|---|---|---|
| `claude`, `claude-code` | `claude` | `Cl` |
| `codex` | `codex` | `Cx` |
| `pi`, `pi-coding-agent` | `pi` | `Pi` |
| unknown/other | `unknown` | `??` |

Open decision: if `jetski`/`gemini` should map to `codex`, add that as a product decision rather than guessing in the UI.

Acceptance:

- Existing agents without `model_type` still list successfully.
- New spawned agents show a deterministic `model_type`.
- Registry state preserves and serves `model_type`.

### B1. Machine/tracker metadata for grouping and health

**Goal:** sidebar can group by machine and status bar can show per-machine RPC/registry health.

Files:

- `agent-tracker/rpc_handler.py`
- `agent-tracker/registry_client.py`
- `agent-registry/server.py`
- `agent-communicator-tui/internal/tracker/types.go`

Plan:

1. Ensure all local `list` rows include:
   - `scope: "local"`,
   - `hostname`,
   - `tracker_id`,
   - `target_address`,
   - `tracker_status: "active"`.
2. Ensure remote merged rows include:
   - `scope: "remote"`,
   - `hostname`,
   - `tracker_id`,
   - `target_address`,
   - `tracker_status` from registry tracker status.
3. Extend registry `GET /trackers` to include UI useful fields:
   - `last_heartbeat`,
   - `age_seconds`,
   - `agent_count`.
4. Add a tracker RPC such as `ui_health` or `registry_status` returning a frontend-friendly health snapshot:

```json
{
  "local": {"hostname": "tanmay-local", "tracker_id": "...", "status": "active"},
  "registries": [{"name": "mundus", "url": "https://...", "status": "ok", "last_success": 1234567890}],
  "trackers": [{"hostname": "dawnstar-qrf", "tracker_id": "...", "status": "active", "agent_count": 2}]
}
```

5. Keep current `list_trackers` for compatibility; the TUI should prefer the new health snapshot once present.

Acceptance:

- TUI can group local and remote agents without parsing `name`.
- TUI can render `rpc · ok/fail` per machine without reading tracker internals or registry status files directly.

### B2. Stable communicator mailbox startup

**Goal:** remove the raw `tracker rpc get_inbox failed: Agent 'agent-communicator' not found` failure mode.

Files:

- `agent-communicator-tui/internal/tracker/client.go`
- `agent-communicator-tui/main.go` / `app.go`
- already-present backend: `agent-tracker/rpc_handler.py::handle_ensure_mailbox`

Plan:

1. Add Go client method `EnsureMailbox(ctx, agentName)` for tracker RPC `ensure_mailbox`.
2. On TUI startup, call `ensure_mailbox` for `ownName` before the first inbox read.
3. If mailbox registration fails, surface a structured UI error but do not repeatedly call `get_inbox` for a missing mailbox.
4. Keep mailbox records `no_registry` by default unless remote addressability for the communicator is explicitly requested.

Acceptance:

- Launching TUI outside an agent pane still creates/uses `agent-communicator` mailbox.
- Inbox reads no longer fail solely because the frontend identity was missing.

### B3. Message sender metadata enrichment

**Goal:** message bubbles can show sender model badge + name + machine without cross-referencing every render.

Files:

- `agent-tracker/rpc_handler.py`
- `agent-tracker/registry_client.py`
- `agent-registry/server.py`
- `agent-communicator-tui/internal/tracker/types.go`

Plan:

1. Add optional fields to inbox message payloads:

```json
{
  "sender": "coder-1",
  "sender_agent_id": "...",
  "sender_tracker_id": "...",
  "sender_hostname": "tanmay-local",
  "sender_model_type": "codex",
  "sender_agent_type": "codex",
  "sender_agent_cmd": "codex",
  "kind": "text"
}
```

2. For local sends, enrich from `state.get_agent(sender_id/name)`.
3. For remote sends, include sender metadata in registry `/messages` payload and preserve it through queued delivery.
4. Registry should add `sender_hostname` from the source tracker when absent.
5. Inbox reads should tolerate legacy messages missing these fields; TUI can fall back to row lookup or `unknown`.
6. Add `kind` only as an extensible hint (`text`, `system`, `code`), not as a strict renderer dependency yet.

Acceptance:

- New inbound messages from local and remote agents include sender model/machine metadata.
- Existing stored inbox files remain readable.

### B4. Unread counts contract

**Goal:** sidebar can show count badges, not just boolean local highlights.

Files:

- `agent-tracker/rpc_handler.py`
- `agent-tracker/state.py` or helper module for inbox scanning
- `agent-communicator-tui/internal/tracker/client.go`

Plan options:

- Preferred: add `get_unread_counts` RPC:

```json
{"agent_name": "agent-communicator", "group_by": "sender"}
```

returns:

```json
{
  "counts": [
    {"sender_agent_id": "...", "sender_tracker_id": "...", "sender": "coder-1", "count": 3}
  ]
}
```

- Alternative: add `include_unread_for: "agent-communicator"` to `list`, returning `unread_count` per agent row.

The preferred standalone RPC keeps `list` cheap and lets the UI poll/refresh unread counts independently.

Acceptance:

- Counts are computed from durable inbox `read` flags.
- Reading a conversation marks the returned messages read via existing inbox semantics, then count drops to zero.
- Remote same-name agents count separately by `sender_tracker_id + sender_agent_id`.

### B5. Typed UI errors and retryability

**Goal:** errors can be rendered inline by agent/machine and in a persistent retry bar.

Files:

- `agent-tracker/rpc_handler.py`
- `agent-communicator-tui/internal/tracker/client.go`
- optional: `agent-registry/server.py` error payload consistency

Plan:

1. Extend JSON-RPC error response to include `data` while preserving `code` and `message`.
2. For common UI failures, return machine/action context:

```json
{
  "code": -32004,
  "message": "Agent 'agent-communicator' not found",
  "data": {
    "error_code": "agent_not_found",
    "agent": "agent-communicator",
    "model_type": "pi",
    "hostname": "dawnstar-qrf",
    "operation": "get_inbox",
    "retryable": true
  }
}
```

3. Go client should expose a typed error preserving raw text for compatibility.
4. Registry HTTP errors already include `error` and `message`; add `hostname`, `tracker_id`, and `retryable` where useful for target-not-found/offline cases.

Acceptance:

- TUI can render `Pi · dawnstar-qrf · agent-communicator not found · r retry` without string parsing.
- Existing CLI output remains readable.

### B6. Lifecycle/system event stream

**Goal:** chat viewport can render system rows like agent spawned, status changed, retry, delivery/read acknowledgements.

Files:

- `agent-tracker/state.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/registry_client.py`

Plan:

1. Publish structured events for:
   - `agent_registered`,
   - `agent_unregistered`,
   - `agent_status_changed`,
   - `message_delivered`,
   - `message_read`,
   - `remote_agent_event`,
   - `rpc_retry` / registry reconnect events if exposed by tracker health.
2. Include `agent_id`, `agent_name`, `tracker_id`, `hostname`, `model_type`, timestamp, and display-safe message.
3. Keep `wait_events` as the transport; add fields rather than changing cursor semantics.

Acceptance:

- TUI can synthesize system annotation rows from events.
- Existing event consumers ignore unknown fields.

### B7. Broadcast support (Phase 3 / after core UI)

**Goal:** `/broadcast` input mode has a backend primitive.

Files:

- `agent-tracker/rpc_handler.py`
- `agent-tracker/registry_client.py`
- `agent-registry/server.py` only if a true registry-side fanout endpoint is desired
- `agent-communicator-tui/internal/tracker/client.go`

Plan:

1. Add `broadcast_message` tracker RPC accepting explicit target filters or `all_registered`.
2. Implement initially as tracker-side fanout over local `list(include_remote=true)` using existing `send_message` paths.
3. Return per-target results, not a single boolean.
4. Require explicit confirmation/guardrails in UI before sending to large sets.

Acceptance:

- Partial failures are visible per agent/machine.
- Remote delivery uses existing registry auth/routing.

---

## Updated phase plan

### Phase 1 — backend contract normalization (new prerequisite)

1. **B0:** Add `model_type` normalization and propagation.
2. **B1:** Add complete machine/tracker metadata and health snapshot.
3. **B2:** Wire stable communicator mailbox into Go TUI startup.
4. **B3:** Enrich new message payloads with sender model/machine metadata.
5. **B4:** Add unread counts RPC or `list` augmentation.
6. **B5:** Add typed RPC error data for actionable UI errors.
7. **B6:** Add lifecycle/system event fields.

Validation:

```sh
python -m pytest agent-tracker agent-registry
(cd agent-communicator-tui && go test ./...)
agent-tracker-ctl list | jq
agent-tracker-ctl registry-status
```

### Phase 2 — Bubble Tea UI redesign

#### Chunk 2.1: sidebar model

- Group by `hostname` / `scope`, not by name parsing.
- Render model badge from `model_type`.
- Render status dot from `tracker_status` + agent runtime status.
- Render unread count from B4.
- Replace ambiguous hidden divider with machine headers and explicit hidden count.

#### Chunk 2.2: chat viewport

- Left-align agent messages and right-align user/outbox messages.
- Use message `sender_model_type`, `sender_hostname`, and `sender` for sender tag.
- Render B6 system events as dashed annotation rows.
- Keep legacy-message fallbacks.

#### Chunk 2.3: input bar

- Preserve existing `/msg`, `/text`, `/key` behavior.
- Add persistent mode tabs above input.
- Add sending context from active row: agent name + model + hostname.
- Defer true `/broadcast` send until B7; UI may show disabled tab before backend is present.

#### Chunk 2.4: status + error bar

- Use B1 health snapshot for `rpc · ok/fail` and agent totals.
- Use B5 typed errors for persistent retry bar and inline agent annotation.
- `r` should retry the failing operation, not merely reload the whole app.

#### Chunk 2.5: root model + composition

- Compose sidebar, chat, input, and statusbar.
- Keep narrow/mobile fallback.
- Preserve existing save prompts/config/hidden-agent features unless explicitly removed.

### Phase 3 — remote and broadcast hardening

- Implement B7 broadcast if not done.
- Review remote watcher privacy; do not broaden passive remote observation just to power sidebar counts.
- Ensure machine health degrades gracefully for stale/gone trackers.

---

## Non-goals / constraints

- Do not require registry access for purely local TUI usage.
- Do not parse model identity from agent display names.
- Do not make remote direct pane input enabled by default.
- Do not break existing inbox files, outbox files, or `agent-tracker-ctl` JSON shapes; only add fields.
- Do not rely on raw ANSI escapes outside rendering helpers.
