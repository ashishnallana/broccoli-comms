# Swarm Durable Timeline Implementation Plan

## Goal

Make Swarm Mode timelines reliable and durable without depending on an active TUI tab, focus state, or group-watch lease.

Messages among swarm agents should be retained even when:

- the TUI is closed,
- Swarm Mode is not selected,
- a swarm has no active window,
- an agent unregisters later,
- members are spread across registry-connected trackers.

## Design principles

1. **Agents are independent launchable units.**
   - Agent config owns `cwd`, `command`, `autostart`, env, and launch details.
   - An agent can run in Simple Chat / standalone mode even if it is also a swarm member.
   - Starting a swarm is orchestration over existing agent configs, not a new process container.

2. **Swarms reference configured agents.**
   - Durable local swarm membership should point to entries in the agent list/config.
   - This lets the system show offline/configured members and launch them when needed.
   - Remote discovered members may be non-launchable locally.

3. **Message capture is automatic and durable.**
   - Do not require `watch_swarm` / group-watch leases for persistence.
   - Every tracker-mediated message is journaled at send/receive time.
   - Swarm timelines are indexed/derived from the durable journal.

4. **Historical timelines survive membership changes.**
   - Each message stores a membership/swarms snapshot at message time.
   - Removing a swarm or agent later should not delete historical timeline records.

5. **Registry propagation is idempotent.**
   - Cross-tracker message events are de-duped by `message_id` or event id.
   - Re-delivery/retry must not duplicate timeline rows.

## Target data model

### Agent config: launch source of truth

```json
{
  "agents": {
    "planner": {
      "cwd": "/repo",
      "command": "pi",
      "autostart": false
    },
    "coder-a": {
      "cwd": "/repo",
      "command": "pi",
      "autostart": false
    }
  }
}
```

### Swarm config: references agents

Canonical future shape:

```json
{
  "swarms": {
    "backend-fix": {
      "name": "backend-fix",
      "members": [
        {"agent": "planner", "role": "main"},
        {"agent": "coder-a", "role": "subagent"}
      ],
      "created_at": "2026-06-06T00:00:00Z"
    }
  }
}
```

Compatibility:

- Existing `agents.<name>.swarms = [{name, role}]` remains accepted.
- A normalization/migration helper can derive canonical `swarms` from legacy per-agent membership.
- During launch/register, the wrapper can still pass swarm metadata derived from canonical config.

### Swarm member runtime row

`list_swarms` should eventually include configured, running, remote, and historical states:

```json
{
  "name": "backend-fix",
  "main": {
    "name": "planner",
    "role": "main",
    "configured": true,
    "running": false,
    "launchable": true,
    "target_address": null
  },
  "members": [
    {
      "name": "planner",
      "role": "main",
      "configured": true,
      "running": false,
      "launchable": true
    },
    {
      "name": "coder-a",
      "role": "subagent",
      "configured": true,
      "running": true,
      "launchable": true,
      "target_address": "coder-a"
    },
    {
      "name": "remote-host/reviewer",
      "role": "subagent",
      "configured": false,
      "running": true,
      "launchable": false,
      "target_address": "remote-host/reviewer"
    }
  ],
  "warnings": []
}
```

## Durable message journal

### Local journal

Add a durable tracker-side message journal. Start with JSONL for small changes; consider SQLite once query complexity grows.

Candidate path:

```text
$CACHE_DIR/agent-tracker/message_journal.jsonl
```

Message event schema:

```json
{
  "message_id": "uuid-or-existing-id",
  "timestamp": "2026-06-06T00:00:00Z",
  "sender": {
    "agent_id": "a1",
    "name": "planner",
    "hostname": "host1",
    "tracker_id": "t1"
  },
  "recipient": {
    "agent_id": "a2",
    "name": "coder-a",
    "hostname": "host1",
    "tracker_id": "t1"
  },
  "message": "body text",
  "attachments": [],
  "swarms": [
    {"name": "backend-fix"}
  ],
  "membership_snapshot": {
    "backend-fix": {
      "sender_role": "main",
      "recipient_role": "subagent"
    }
  },
  "direction": "local|outbound|inbound",
  "source": "send_message|registry_delivery",
  "schema_version": 1
}
```

### Classification rule

At message time:

1. Resolve sender membership set.
2. Resolve recipient membership set.
3. `message_swarms = intersection(sender_swarms, recipient_swarms)`.
4. Append one journal row with `swarms` and role snapshot.

If a message is user → swarm main, include the selected swarm context when available. If no explicit swarm context exists, classify by membership intersection only.

## Cross-tracker / registry design

### Registry message event endpoint

Add append-only message event ingestion:

```http
POST /message-events
```

Payload:

```json
{
  "message_id": "uuid",
  "timestamp": "...",
  "sender_tracker_id": "t1",
  "sender_hostname": "host1",
  "sender_agent_id": "a1",
  "sender_agent_name": "planner",
  "recipient_tracker_id": "t2",
  "recipient_hostname": "host2",
  "recipient_agent_id": "a2",
  "recipient_agent_name": "coder-b",
  "swarms": [{"name": "backend-fix"}],
  "message": "body text"
}
```

Registry behavior:

- Store append-only, de-duped by `message_id`.
- Include query endpoint:

```http
GET /message-events?swarm=backend-fix&limit=200
```

or:

```http
GET /swarms/backend-fix/timeline?limit=200
```

### Publishing rules

For remote messages:

- Sender/origin tracker creates the canonical message event before/while queueing delivery.
- Target tracker records inbound copy idempotently on delivery.
- Registry stores canonical cross-tracker event for later timeline queries.

For local-only messages:

- Local tracker journal is sufficient.
- If registry is configured, optionally publish metadata/body so other machines can inspect shared swarm timelines.

### Privacy modes

Initial trusted/dev mode may store plaintext bodies in registry.

Future modes:

1. **Metadata-only registry**: registry stores participants/timestamps/swarms, body remains on trackers.
2. **Encrypted body**: registry stores ciphertext, swarm participants decrypt locally.

## API changes

### Keep

```json
list_swarms {}
get_swarm_timeline {"swarm": "backend-fix", "last_n": 200}
```

### Change semantics

`get_swarm_timeline` should read durable journals, not group-watch cache:

- local journal rows for `swarm`,
- plus registry message events for `swarm`,
- de-duped and sorted by timestamp.

### Deprecate / compatibility only

```json
watch_swarm
watch_group
update_watchlist mode=group
```

These can remain for live UI refresh compatibility but should no longer be required for persistence.

## Implementation phases

### Phase 1: config and swarm model refinement

- Add canonical top-level `swarms` config support.
- Keep legacy `agents.<name>.swarms` support and normalize both shapes.
- Ensure each local durable swarm member references a configured agent.
- Extend `list_swarms` to include configured-offline members.
- Add launchability fields: `configured`, `running`, `launchable`.

Tests:

- Configured offline swarm member appears in `list_swarms`.
- Removing swarm membership does not delete agent config.
- Removing agent removes/invalidates local swarm member reference.
- Agent without swarm launches/runs normally.

### Phase 2: local durable message journal

- Add append/read helpers in tracker state or a new `message_journal.py`.
- Journal every local `send_message` / `deliver_local_message` path.
- Classify swarm membership at message time.
- Update `get_swarm_timeline` to read from journal.
- Stop relying on active group watches for local swarm persistence.

Tests:

- Message between two swarm members is journaled without `watch_swarm`.
- Message is still present after `list_swarms` no longer has active/running members.
- Duplicate `message_id` is idempotent.
- Non-swarm message does not appear in swarm timeline.

### Phase 3: registry message events

- Add registry `POST /message-events` and query endpoint.
- Store events durably and de-dupe by `message_id`.
- Include swarm metadata in event rows.
- Add retention-safe schema versioning.

Tests:

- Posting a message event persists it.
- Duplicate post does not duplicate.
- Query by swarm returns matching events only.
- State reload preserves events.

### Phase 4: tracker registry publication and merge

- On remote send, publish canonical message event to registry.
- On inbound remote delivery, append local journal copy idempotently.
- `get_swarm_timeline` merges local journal + registry events.
- De-dupe merged results by `message_id`.

Tests:

- Remote sender publishes registry message event with swarms.
- Receiving tracker records inbound event.
- Timeline merge includes remote events when local TUI was never watching.
- Registry temporarily unavailable does not break local delivery; failed publish is queued/retried if possible.

### Phase 5: TUI integration contract

Backend contract for TUI:

- `list_swarms`: configured/running/remote/historical membership rows.
- `get_swarm_timeline`: durable timeline, no watch required.
- Optional live updates can still use existing event polling or a future message-journal cursor.

TUI should:

- Show offline configured members and launch actions.
- Show remote non-launchable members.
- Not require Swarm Mode focus for data capture.

### Phase 6: group-watch deprecation cleanup

- Mark group-watch swarm persistence as deprecated.
- Keep existing RPCs temporarily for compatibility.
- Remove group-watch dependency from Swarm Mode documentation.
- Optionally migrate old group timeline files into message journal.

## Risks / open questions

1. Registry plaintext message body policy: acceptable initially or require metadata-only/encryption?
2. Retention: how long should registry message events persist?
3. Conflict: if two trackers publish same `message_id` with different bodies, which wins?
4. Historical swarm membership: should removed swarm configs remain as archived swarm identities?
5. Agent identity: should swarm config reference local agent name, stable config ID, or agent UUID?

## Recommended next milestone

Start with **local durable journal + configured-offline swarm members** before registry message events. This gives the biggest reliability improvement locally and simplifies TUI behavior immediately:

- no active watch needed,
- swarm timelines survive TUI closure,
- offline members are visible and launchable,
- agents remain independently runnable.
