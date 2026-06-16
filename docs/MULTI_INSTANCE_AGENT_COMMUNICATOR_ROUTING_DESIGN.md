# Reliable Multi-Instance Agent-Communicator Routing Design

## Status

Design proposal for `task-45e0724f9a1d`. This document is architecture-only. Implementation follow-ups must be created separately and must receive explicit user/coordinator approval after this design is reviewed.

## Problem

Broccoli Comms currently uses two different notions of an agent target:

1. A logical display/service name such as `agent-communicator`, `broccoli-agent`, or `coder`.
2. A concrete running endpoint: one pane/mailbox on one tracker/host with a stable runtime `agent_id`/`uuid`.

For normal single-instance local agents these often coincide. For shared service identities, especially `agent-communicator`, there is one local service per tracker/host and many concrete instances across a registry. A bare send to `agent-communicator` is local-only today, while task updates need all active communicator services to receive the same typed task-update message. Recent fixes manually enumerate remote `<hostname>/agent-communicator` targets for task updates, but that policy is embedded in task notification code rather than a reusable routing layer.

The desired end state is a single routing contract that makes local delivery, remote delivery, fanout, per-recipient status, deduplication, and task-update broadcast explicit and testable.

## Goals

- Separate logical identities from concrete instances.
- Define explicit delivery modes for local-only, direct concrete delivery, registry-qualified remote delivery, and shared-service fanout.
- Make bare-name behavior safe and backwards-compatible: a bare normal agent name remains local-first/local-only unless the caller opts into fanout.
- Route shared service identities through a common layer instead of custom task-update code.
- Persist auditable per-recipient delivery records with stable delivery IDs and idempotency keys.
- Deduplicate at registry queue, tracker delivery, and inbox write boundaries.
- Preserve structured metadata such as task-update `content_type`, `kind`, `task_id`, `task_status`, `delivery_scope`, and recipient fields.
- Provide clear failure modes and migration steps.

## Non-goals

- Do not make all bare names global by default.
- Do not allow direct pane input to shared UI/mailbox identities.
- Do not remove current `agent_name` and `target_address` CLI/API compatibility in the first implementation.
- Do not require global consensus or exactly-once distributed delivery; use at-least-once transport with idempotent receipt.

## Identity Model

### Logical identity

A logical identity is the user-facing or service-facing name, e.g.:

- `agent-communicator`
- `broccoli-agent`
- `broccoli-review`
- `coder`

Logical identities are not globally unique. They may be:

- `single_instance`: expected to have at most one active local instance.
- `profile`: an agent profile that may have multiple concrete instances, often represented as `profile@instance`.
- `shared_service`: one service instance per tracker/host; `agent-communicator` is the primary example.

Add a small identity policy table/config, initially code-backed and later configurable:

```json
{
  "agent-communicator": { "kind": "shared_service", "default_delivery": "fanout_active_trackers" }
}
```

Unknown identities default to `single_instance`/local-only compatibility.

### Concrete instance

A concrete instance is a routable endpoint with:

- `tracker_id`
- `hostname`
- `agent_id` / `uuid`
- current local display name
- aliases
- status (`active`, `stale`, `gone`, etc.)
- capabilities (`mailbox`, `pane_input`, `direct_input_disabled`, `shared_service`)

Canonical concrete address forms:

- `local/<agent-id-or-name>`: force local resolution.
- `<hostname>/<agent-id-or-name>`: route to a concrete remote host through the selected registry.
- `<registry>:<hostname>/<agent-id-or-name>`: route through a named registry.
- `agent_id:<uuid>` may be added later as an unambiguous local-or-registry lookup key, but should not replace host-qualified routing initially.

### Message sender identity

Sender fields must retain both logical and concrete sender data:

- `sender_agent_name`
- `sender_agent_id`
- `sender_tracker_id`
- `sender_hostname`
- optional `sender_logical_identity`

Reply routing should prefer the concrete sender tuple from the received message, not a bare sender name.

## Delivery Modes

Introduce an internal routing request object used by CLI, tracker RPC, task notifications, and future TUI code:

```python
RoutingRequest = {
  "sender": SenderRef,
  "target": TargetRef,
  "mode": "local" | "direct" | "fanout" | "auto",
  "message": str,
  "attachments": list,
  "metadata": dict,
  "idempotency_key": str | None,
  "allow_partial": bool,
}
```

### `local`

- Target: bare `agent_name`, `agent_id`, or `local/name`.
- Resolution: local tracker state only.
- Use for existing bare-name send compatibility.
- Missing local target returns a local target-not-found error; no remote fallback.

### `direct`

- Target: concrete instance, preferably host-qualified.
- Resolution: exact local endpoint or exact registry endpoint.
- Use for replies, direct chat, and participant notifications to known concrete remote addresses.
- If multiple registry endpoints can route the target hostname, require registry qualification or return an ambiguity error.

### `fanout`

- Target: logical shared service identity.
- Resolution: all active concrete instances matching the identity and policy.
- Default for `agent-communicator` task-update broadcasts.
- Fanout includes local matching service plus active remote tracker services unless caller requests local-only.
- Returns one aggregate result plus per-recipient delivery records.

### `auto`

- Compatibility shim for existing APIs.
- If target contains `/`, treat as `direct`.
- If target is a configured `shared_service`, use that identity's default policy. For `agent-communicator`, task-update callers use fanout; ordinary CLI sends can initially remain local unless they set `delivery_scope=shared_service_broadcast` or `mode=fanout`.
- Else use `local`.

## Default Policy for Shared Service Identities

For `agent-communicator`:

- Task update, memory update, approval, and chain-summary system messages: `fanout_active_trackers`.
- Direct user chat to bare `agent-communicator`: keep local-only initially for backwards compatibility; expose `--fanout`/metadata opt-in if needed.
- Direct pane input: disabled. UI/mailbox identities are mailbox targets only.
- Remote explicit target `<hostname>/agent-communicator`: direct delivery to that host's communicator only.
- Deduplicate local and remote aliases so `agent-communicator`, `local/agent-communicator`, and `<local-host>/agent-communicator` do not receive duplicates in one fanout.

## Registry Routing

### Current baseline

The registry already:

- stores trackers and registered agents,
- rejects bare global name delivery,
- requires hostname when resolving `target_agent_name`,
- queues per-target-tracker deliveries,
- requires sender and target to be on different trackers for remote sends,
- persists queued deliveries and acks by `message_id`.

### Proposed additions

1. **Registry target query API**
   - Add an endpoint or extend `/agents` filtering for `logical_identity`, `hostname`, `status`, and capability.
   - Trackers should publish `logical_identity` and `service_kind` for shared services in their agent registration payload.

2. **Fanout planning in the sender tracker**
   - Sender tracker asks registry for active matching concrete instances.
   - Sender tracker builds a fanout plan with one delivery recipient per concrete instance.
   - Local recipient is included from local state, not round-tripped through registry.

3. **Per-recipient delivery IDs**
   - Keep a stable group `message_id` for the logical message.
   - Add `delivery_id = sha256(message_id + recipient_tracker_id + recipient_agent_id + delivery_scope)`.
   - Registry queues by `delivery_id`, not just group `message_id`, so one fanout message can target multiple trackers/agents without key collision.
   - Inbox payload carries both `message_id` and `delivery_id`.

4. **Delivery records**
   - Sender tracker records a `delivery_group` row/event and one `delivery_attempt` row/event per recipient.
   - Registry stores queued/acked status by `delivery_id`.
   - Receiver tracker publishes `message_delivered` and `message_notified` with `delivery_id`, `message_id`, receiver fields, and final resolved local agent name.

5. **Status semantics**
   - `planned`: recipient selected.
   - `queued`: local inbox write completed or registry accepted remote queue.
   - `delivered`: receiver tracker wrote inbox.
   - `notified`: receiver tracker attempted pane notification.
   - `read`: receiver read inbox.
   - `failed`: permanent resolution/validation failure.
   - `retrying`: transient registry/network failure.
   - `expired`: not delivered before retention/TTL.

## Per-Recipient Delivery Record Shape

```json
{
  "message_id": "logical-message-uuid",
  "delivery_id": "recipient-stable-hash-or-uuid",
  "delivery_scope": "shared_service_broadcast",
  "delivery_mode": "fanout",
  "target_logical_identity": "agent-communicator",
  "target_tracker_id": "tracker-123",
  "target_hostname": "cloudtop",
  "target_agent_id": "agent-uuid",
  "target_agent_name": "agent-communicator",
  "status": "queued|delivered|notified|read|failed|expired",
  "attempt": 1,
  "error_code": null,
  "error_message": null,
  "created_at": "...",
  "updated_at": "..."
}
```

These records should be exposed through a small diagnostic CLI, e.g. `broccoli-comms agent-tracker delivery show MESSAGE_ID --json`, after the core data path exists.

## Deduplication and Idempotency

Dedupe must happen at every boundary because the transport remains at-least-once.

1. **Sender planning**
   - Canonical recipient key: `(tracker_id, agent_id)` if known, else `(registry_name, hostname, target_name)`.
   - Collapse aliases and local host-qualified forms into one local recipient.

2. **Registry queue**
   - Key queued deliveries by `delivery_id`.
   - `POST /messages` with the same `delivery_id` is idempotent if payload hash matches; conflicting payload for same ID returns `409 idempotency_conflict`.

3. **Receiver tracker**
   - Inbox write dedupes by `delivery_id` when present, else existing `message_id` fallback.
   - Message journal records by `delivery_id` for delivery attempts and by `message_id` for logical conversation timeline, preserving both.

4. **TUI/task UI**
   - Task update cards dedupe by `(task_id, task_status, created_event_seq or message_id)`; transport duplicates should not produce duplicate task rows.

## Task-Update Integration

Replace `_notify_shared_service_identity` custom enumeration with a shared routing layer:

1. `notify_task_update` builds the typed message and metadata exactly once.
2. For UI broadcast, it calls:
   - target: `agent-communicator`
   - mode: `fanout`
   - delivery_scope: `shared_service_broadcast`
   - recipient_kind: `shared_service`
3. The router adds per-recipient fields:
   - `recipient_agent`
   - `recipient_kind`
   - `target_logical_identity`
   - `delivery_id`
   - concrete target fields.
4. Participant notifications continue to use direct/local mode:
   - local active pane agents may prefer `send_input`, with `send_message` fallback.
   - host-qualified participants use direct registry message delivery.
5. The same shared router should be used later for memory proposal notifications, approval notifications, chain-summary notifications, and any future TUI system broadcast.

Metadata preservation is mandatory. The router must pass through all existing structured fields and the registry must include them in queued delivery payloads.

## Failure Modes

### Local target missing

- Local/direct mode: return `target_not_found`.
- Fanout mode: mark local recipient failed if it was planned; do not fail remote recipients unless `allow_partial=false`.

### Remote target missing

- Direct mode: return `agent_not_found`; do not fallback to a bare local name.
- Fanout mode: stale registry entries are excluded during planning if status is not active; if a planned target disappears before queueing, mark that recipient failed.

### Registry unavailable

- Local recipients still deliver.
- Remote fanout recipients become `retrying` or `failed` depending on caller policy.
- System notifications should return aggregate `sent=true` if at least one recipient succeeded, plus per-recipient failures for audit.

### Tracker stale/offline

- Registry should not accept new direct delivery to stale/gone trackers unless a future offline queue policy is explicit.
- Fanout planning excludes stale/gone trackers by default.

### Ambiguous host or registry

- If multiple registries know the same hostname and the target is not registry-qualified, return an ambiguity error with suggested `registry:hostname/name` choices.

### Duplicate shared identity on same tracker

- Prefer concrete `agent_id` uniqueness.
- If multiple active local `agent-communicator` endpoints exist on one tracker, fanout should deliver to all only if policy allows `multi_instance_per_tracker`; default is `one_per_tracker`, choose the newest healthy endpoint and mark the rest as suppressed/duplicate in delivery records.

### Receiver delivery succeeds but ack fails

- Registry redelivers.
- Receiver inbox dedupe by `delivery_id` prevents duplicate visible messages.
- Receiver still re-acks idempotently.

### Metadata too large or invalid

- Validate before fanout planning.
- Fail the whole group before partial sends if shared payload is invalid.

## Migration and Backward Compatibility

### Phase 0: Document and test current behavior

- Keep existing APIs.
- Add regression tests around current task-update remote communicator visibility and metadata preservation.

### Phase 1: Internal router library

- Introduce a tracker-side routing module wrapping existing `send_message`, `send_input`, registry client, and local inbox delivery.
- No CLI behavior change except optional debug fields in JSON results.
- Reimplement `_notify_shared_service_identity` on top of router fanout.

### Phase 2: Delivery IDs and records

- Add `delivery_id` to local payloads, registry `/messages`, queued deliveries, inbox entries, and events.
- Keep accepting old payloads without `delivery_id`; dedupe by `message_id` fallback.
- Add diagnostic read API/CLI for delivery status.

### Phase 3: Registry discovery improvements

- Publish service metadata/capabilities in tracker registration.
- Add filtered registry query for shared service instances.
- Replace task notification's current `tracker_info` + `list_trackers` hostname enumeration with registry-backed recipient planning.

### Phase 4: CLI/API exposure

- Add optional `--delivery-mode local|direct|fanout|auto` and `--delivery-scope` to send-message surfaces.
- Preserve default bare-name local-only behavior.
- Add explicit `--fanout` shortcut for shared service broadcasts if needed.

### Phase 5: Cleanup

- Remove duplicated shared-service routing helpers after all system notification paths use the router.
- Update docs and examples to recommend host-qualified direct routing and explicit fanout for shared services.

## Validation Strategy

### Unit tests

- Address parsing:
  - bare local name remains local mode,
  - `local/name` stays local,
  - `host/name` direct routes through registry,
  - `registry:host/name` selects named registry.
- Shared service policy:
  - `agent-communicator` task update uses fanout,
  - bare non-service agent does not fan out,
  - duplicate aliases collapse to one recipient.
- Fanout planning:
  - includes local communicator and active remote communicators,
  - excludes stale/gone trackers,
  - handles duplicate communicator instances on same tracker per policy.
- Delivery IDs:
  - stable for same message and recipient,
  - distinct for different recipients,
  - idempotency conflict on same ID with different payload.
- Metadata preservation:
  - task-update metadata survives local, remote direct, and fanout delivery.

### Registry tests

- `/messages` accepts `delivery_id` and queues by delivery ID.
- Duplicate queue request with same delivery ID is idempotent.
- Conflicting duplicate returns a clear error.
- Multi-recipient fanout to two trackers creates two delivery records and does not overwrite by shared `message_id`.

### Tracker integration tests

- Remote delivery redelivery after ack failure is deduped in inbox by `delivery_id`.
- Receiver publishes `message_delivered`, `message_notified`, and read events with both `message_id` and `delivery_id`.
- Participant direct notifications still prefer `send_input` locally and fallback to inbox on failure.

### End-to-end tests

Extend `docs/E2E_ROUTING_TESTING_PLAN.md` with:

- Host and VM both run `agent-communicator`; one task update reaches both exactly once.
- Same task update metadata is visible in both TUIs.
- Explicit `<hostname>/agent-communicator` reaches only that host.
- Bare CLI send to `agent-communicator` remains local-only unless fanout is requested.
- Local and remote agents with the same display name do not cross-deliver.
- Registry outage still delivers local communicator task update and reports remote failures.

## Open Questions

1. Should shared service fanout include only `agent-communicator` or any registered service declaring `shared_service=true`?
2. Should fanout to stale trackers be queued for later or skipped by default? This design recommends skipping until offline delivery is explicitly designed.
3. How much delivery history should be retained locally and in the registry?
4. Should user-facing CLI expose delivery records immediately or only after implementation stabilizes?

## Implementation Follow-up Approval Gate

After this design is reviewed and accepted, do not start implementation automatically. The coordinator/user must explicitly approve implementation follow-up tasks and their scope. Suggested follow-ups:

1. Implement internal routing request/recipient planner and move task-update shared-service broadcast onto it.
2. Add `delivery_id` and per-recipient delivery records across tracker, registry, inbox, and events.
3. Add registry service metadata and filtered shared-service discovery.
4. Add CLI diagnostics and E2E coverage.
