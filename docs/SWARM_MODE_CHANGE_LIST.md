# Swarm Mode Change List

This breaks the Swarm Mode design into concrete work areas for the TUI, local `agent-tracker`, and optional `agent-registry`.

## 1. Agent Communicator TUI changes

### Tab/model changes

- Replace user-visible `Advanced Chat` tab with `Swarm Mode`.
- Add/rename view mode:
  - preferred: introduce `swarmView`
  - transitional option: keep `advancedView` internally but render `Swarm Mode`
- Extend the existing data-driven tab registry:

```go
{ID: "simple", Mode: simpleView, Label: "Simple Chat", CanCompose: true}
{ID: "swarm", Mode: swarmView, Label: "Swarm Mode", CanCompose: true}
{ID: "saved", Mode: savedView, Label: "Saved Messages", CanCompose: false}
```

### TUI state

Add small, focused state fields:

```go
type swarmRow struct {
    Name        string
    Main        agentRow
    Members     []agentRow
    MainMissing bool
    Warning     string
}

swarms       []swarmRow
selectedSwarm int
swarmMessages []tracker.Message // or a SwarmTimelineMessage type
```

### Loading commands/client methods

Add tracker client calls:

- `ListSwarms()`
- `GetSwarmTimeline(swarmName, lastN)`
- `WatchSwarm(swarmName)` or reuse a generic group-watch RPC wrapper

### Navigation behavior

- In `swarmView`, `Ctrl-N` / `Ctrl-P` changes `selectedSwarm`.
- In simple chat, `Ctrl-N` / `Ctrl-P` continues to change agents.
- Bottom `Tab` / `Shift-Tab` continues to switch top-level tabs.

### Composer/send behavior

Add a generic target resolver:

```go
func (m model) currentSendTarget() (agentRow, bool)
```

- `simpleView`: selected agent.
- `swarmView`: selected swarm main agent.
- `savedView`: no target.

Swarm composer:

- Placeholder: `message main agent in <swarm>`.
- Enter sends only to the main agent.
- If main is missing, composer is disabled with a warning.

### Rendering

- Conversation panel shows swarm timeline: `sender → recipient` labels.
- Sidebar/current panel shows:
  - selected swarm name
  - main agent
  - subagent list
  - warnings: no main, duplicate main, offline members
- Empty state gives setup examples using `--swarm` and `--role`.

### TUI tests

- `Swarm Mode` tab renders instead of `Advanced Chat`.
- `Ctrl-N` / `Ctrl-P` changes swarms in swarm mode.
- Composer sends to main agent only.
- Missing main disables composer.
- Swarm timeline renders sender → recipient labels.

## 2. Local agent-tracker changes

### Agent metadata

Store swarm memberships on each agent:

```json
"swarms": [
  {"name": "backend-fix", "role": "main"},
  {"name": "review", "role": "subagent"}
]
```

Required changes:

- `register` accepts `swarms`.
- `update_agent` can update `swarms` if needed.
- `list` includes `swarms` on each agent row.
- State recovery should preserve swarm metadata where possible.

### New tracker RPCs

Add derived read APIs:

- `list_swarms`
  - derives swarms from current agent metadata
  - returns main/member rows and warnings
- `get_swarm_timeline`
  - wrapper around existing group timeline reads
- `watch_swarm`
  - wrapper around existing group watch logic using swarm members

### Group timeline integration

Reuse existing primitives:

- `state.update_group_watch(...)`
- `state.record_to_matching_group_timelines(...)`
- `state.read_group_timeline(...)`

Suggested group id:

```text
swarm:local:<swarm-name>
```

### Cleanup/removal behavior

Because swarms are derived from agent metadata:

- `unregister` removes the agent from all swarms automatically.
- `delete_agent` / remove-by-pane should naturally remove the membership.
- Group watch leases should refresh on `agent_registered`, `agent_updated`, and `agent_unregistered` events.

### Validation rules

- Swarm name format: conservative agent-name-like regex.
- Role enum: `main`, `subagent`.
- Duplicate main in one swarm:
  - tracker returns a warning in `list_swarms`
  - config layer may reject where deterministic

### Tracker tests

- Register/list includes swarm metadata.
- `list_swarms` derives main/subagents correctly.
- Agent in multiple swarms appears in each.
- Unregister removes agent from all derived swarms.
- Missing main and duplicate main warnings are produced.
- `watch_swarm` records observed messages among members.

## 3. Launcher / wrapper / CLI changes

These are not tracker internals, but they are required glue.

### `broccoli-comms track`

Add:

```sh
--swarm SWARM_NAME
--role main|subagent
```

Allow repeated swarm/role pairs for multi-swarm membership.

### `broccoli-comms agent add`

Add same flags and persist normalized config:

```json
"swarms": [{"name": "backend-fix", "role": "main"}]
```

### Managed launch/env

- Pass swarm membership metadata from `agent add` config to `broccoli-comms track`.
- Pass metadata through the wrapper environment or wrapper args.
- `agent-wrapper` includes `swarms` in the `register` RPC payload.

### CLI/config tests

- `agent add --swarm s --role main` persists normalized swarms.
- Repeated pairs persist multiple memberships.
- `--role` without `--swarm` fails.
- Invalid role/swarm name fails.
- Managed launch command includes swarm metadata.

## 4. Registry changes

### Phase 1: local-only swarms

No registry changes are strictly required for a local-only first milestone.

The local tracker can derive swarms from local agents and use local group timelines.

### Phase 2: remote/cross-machine swarms

For remote swarms, registry should carry swarm metadata in agent heartbeat/discovery rows.

Required changes:

- Accept and store agent `swarms` in tracker heartbeats.
- Include `swarms` in `/agents` responses.
- Preserve `swarms` in queued/discovered remote agent rows.

### Remote group watch delegation

The code already has delegated group watch/event paths. Swarm Mode should reuse them for cross-machine members:

- Local tracker resolves swarm members by `host/agent` or stable `agent_id`.
- Local tracker delegates `watch_group_request` to remote trackers for remote members.
- Remote trackers publish `group_message_observed` events back.
- Local tracker appends those events to the swarm timeline.

### Registry tests

- Heartbeat with agent `swarms` persists metadata.
- `/agents` includes swarm membership metadata.
- Remote `list_swarms`/TUI discovery can see remote swarm members.
- Delegated watch request works with swarm group ids.

## Recommended implementation order

1. CLI/config/wrapper metadata plumbing.
2. Tracker state + `list_swarms`.
3. TUI Swarm Mode local-only rendering and send-to-main.
4. Tracker `watch_swarm` + timeline wiring.
5. Registry metadata propagation.
6. Remote delegated swarm watches.

This keeps the first milestone useful without making registry support a blocker.
