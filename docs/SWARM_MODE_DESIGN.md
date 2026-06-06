# Swarm Mode Design

## Goal

Replace the current `Advanced Chat` tab/view with a **Swarm Mode** view.

A swarm is a named group of agents with one intended **main** agent and zero or more **subagents**. The user sends messages only to the main agent, while the UI shows the message traffic among all members of the selected swarm.

Example use cases:

- `backend-fix` swarm: `planner` is main, `coder-a`, `coder-b`, and `reviewer` are subagents.
- `research` swarm: `lead` is main, `searcher`, `summarizer`, and `critic` are subagents.
- One agent can belong to multiple swarms.

## User model

### Chat behavior

- In **Simple Chat**, the user talks to the selected agent as today.
- In **Swarm Mode**, the user talks only to the selected swarm's **main** agent.
- Swarm Mode displays:
  - user → main messages
  - main → subagent messages
  - subagent → main messages
  - subagent → subagent messages, if they happen
- In **Saved Messages**, behavior remains read-only.

### Navigation

- Bottom tabs remain generic/data-driven:
  - `Simple Chat`
  - `Swarm Mode`
  - `Saved Messages`
- In Swarm Mode:
  - `Ctrl-N` / `Ctrl-P` switch between swarms, not agents.
  - Agent switching remains available outside Swarm Mode, and any existing replacement binding like `Ctrl-G` can continue to handle agent sections.
- If no swarm exists, Swarm Mode shows an empty state with setup examples.

## CLI design

### `broccoli-comms track`

Add flags:

```sh
broccoli-comms track \
  --name planner \
  --swarm backend-fix \
  --role main \
  -- pi

broccoli-comms track \
  --name coder-a \
  --swarm backend-fix \
  --role subagent \
  -- pi
```

### `broccoli-comms agent add`

Add equivalent persisted config flags:

```sh
broccoli-comms agent add planner \
  --cwd ~/repo \
  --command 'pi' \
  --swarm backend-fix \
  --role main \
  --autostart

broccoli-comms agent add coder-a \
  --cwd ~/repo \
  --command 'pi' \
  --swarm backend-fix \
  --role subagent \
  --autostart
```

### Multiple swarm membership

An agent may belong to multiple swarms. Keep the initial CLI simple but extensible:

Option A, repeat paired flags:

```sh
broccoli-comms agent add shared-reviewer \
  --cwd ~/repo \
  --command 'pi' \
  --swarm backend-fix --role subagent \
  --swarm frontend-fix --role subagent
```

Option B, compact future form:

```sh
--swarm backend-fix:subagent --swarm frontend-fix:subagent
```

Recommendation: implement **Option A** first because it matches the requested `--swarm=swarm-name --role=main/subagent` shape. Internally normalize to a list of memberships.

Validation rules:

- `--role` is valid only with `--swarm`.
- Role enum: `main`, `subagent`.
- Swarm names use the same conservative character policy as agent names: letters, numbers, dot, underscore, dash.
- Multiple `main` agents in one swarm should be rejected by persisted config validation when possible. At runtime, if detected, UI should show a clear warning and choose the most recently registered main as the active target.

## Data model

### Config file

Extend configured agent specs in `$XDG_CONFIG_HOME/broccoli-comms/config.json`:

```json
{
  "agents": {
    "planner": {
      "cwd": "/home/user/repo",
      "command": "pi",
      "autostart": true,
      "swarms": [
        {"name": "backend-fix", "role": "main"}
      ]
    },
    "coder-a": {
      "cwd": "/home/user/repo",
      "command": "pi",
      "autostart": true,
      "swarms": [
        {"name": "backend-fix", "role": "subagent"}
      ]
    }
  }
}
```

Keep legacy/simple compatibility:

- CLI accepts `--swarm NAME --role ROLE`.
- Config stores normalized `swarms: [{name, role}]`.
- Do not store a single top-level `swarm` string long-term; it makes multi-swarm membership harder.

### Tracker agent metadata

On register/update/list, include swarm memberships on agent rows:

```json
{
  "name": "coder-a",
  "agent_id": "...",
  "swarms": [
    {"name": "backend-fix", "role": "subagent"}
  ]
}
```

For local agents, the launcher/wrapper passes swarm metadata to `register`.
For remote agents, registry heartbeat should publish the same metadata so cross-machine swarms can be displayed later.

### Derived swarm state

The tracker should derive swarm state from current agent metadata rather than treating swarms as separate long-lived agents:

```json
{
  "backend-fix": {
    "name": "backend-fix",
    "main": {
      "agent_id": "...",
      "name": "planner",
      "target_address": "planner"
    },
    "members": [
      {"agent_id": "...", "name": "planner", "role": "main"},
      {"agent_id": "...", "name": "coder-a", "role": "subagent"}
    ]
  }
}
```

This satisfies the removal requirement: when an agent unregisters/is removed, it disappears from all derived swarms automatically.

## Tracker/API design

### New or extended RPCs

Add a minimal read API for the TUI:

```json
list_swarms -> {"swarms": [...]} 
get_swarm_timeline {"swarm": "backend-fix", "last_n": 200} -> {"messages": [...]}
watch_swarm {"swarm": "backend-fix", "lease_seconds": 30} -> {"ok": true}
```

Implementation can reuse existing group timeline primitives:

- `state.update_group_watch(...)`
- `state.record_to_matching_group_timelines(...)`
- `get_group_timeline`

Swarm group id convention:

```text
swarm:<hostname-or-registry-scope>:<swarm-name>
```

Local-first initial version can use:

```text
swarm:local:<swarm-name>
```

### Message observation

When Swarm Mode is active, the UI leases a group watch for the selected swarm's member addresses. The tracker already records observed messages when both sender and recipient match group members.

Initial implementation:

1. TUI calls `list_swarms`.
2. TUI selects a swarm.
3. TUI calls `watch_group`/`watch_swarm` with current members and a renewable lease.
4. TUI calls `get_group_timeline`/`get_swarm_timeline` to render observed traffic.
5. TUI refresh/events update the timeline.

Longer-term implementation:

- Keep a tracker-side auto-watch for configured swarms so traffic is captured even when the UI is closed.
- Persist swarm timelines by swarm id.
- Add remote tracker delegation for cross-machine swarms using the existing delegated group watch path.

## Removal behavior

Requirement: if an agent is removed, it should be removed from all swarms.

Design:

- Swarm membership is stored on the agent config and agent tracker metadata.
- `broccoli-comms agent remove NAME` removes the agent config, kills/unregisters the agent, and therefore removes its memberships.
- Tracker `unregister` deletes the agent state; derived `list_swarms` no longer includes it.
- Group watch membership should be refreshed whenever `agent_registered`, `agent_unregistered`, or `agent_updated` events occur.
- If a removed agent was the main agent:
  - Swarm remains visible if other members still exist.
  - UI shows `No main agent configured/running`.
  - Composer is disabled for that swarm until a main is present.

## TUI design

### Tab replacement

Update tab registry:

```go
{ID: "simple", Mode: simpleView, Label: "Simple Chat", CanCompose: true}
{ID: "swarm", Mode: swarmView, Label: "Swarm Mode", CanCompose: true}
{ID: "saved", Mode: savedView, Label: "Saved Messages", CanCompose: false}
```

`advancedView` can either be renamed to `swarmView` or kept internally during migration. Preferred: introduce `swarmView` and remove/retire advanced naming in user-visible UI.

### Swarm row model

Add a small TUI model slice:

```go
type swarmRow struct {
    Name        string
    Main        agentRow
    Members     []agentRow
    MainMissing bool
    Warning     string
}
```

In `swarmView`:

- `Ctrl-N` / `Ctrl-P` changes `selectedSwarm`.
- Composer target is `swarm.Main`.
- Sidebar can show:
  - selected swarm
  - main agent badge
  - subagent list
  - warnings like missing main or duplicate main
- Conversation area shows swarm timeline messages with sender → recipient labels.

### Composer behavior

In `swarmView`:

- Composer placeholder: `message main agent in <swarm-name>`.
- `Enter` sends to `main.target_address`.
- If no main exists, composer is disabled and a status line explains why.

This can reuse the generic tab `CanCompose`, but final send eligibility needs an additional per-tab target check:

```go
func (m model) currentSendTarget() (agentRow, bool)
```

For simple view: selected agent.
For swarm view: selected swarm main agent.
For saved/read-only views: false.

## Implementation phases

### Phase 1: metadata and config

- Add `--swarm` and `--role` to `track` and `agent add`.
- Normalize config to `swarms: [{name, role}]`.
- Pass swarm metadata through managed launch env to wrapper.
- Extend wrapper register payload with `swarms`.
- Store `swarms` in tracker agent state and list output.
- Add tests for config normalization, CLI parsing, and register/list metadata.

### Phase 2: tracker swarm API

- Add `list_swarms` derived from current local agent rows.
- Add `get_swarm_timeline` wrapper over group timelines.
- Add `watch_swarm` wrapper over existing group watch functionality.
- Refresh/removal behavior comes from derived state; add tests for unregister cleanup.

### Phase 3: TUI Swarm Mode

- Replace `advancedView` user-facing tab with `swarmView` / `Swarm Mode`.
- Add swarm loading commands and model fields.
- Make `Ctrl-N` / `Ctrl-P` switch swarms only in `swarmView`.
- Render swarm timeline and member sidebar.
- Send composer messages to selected swarm main.
- Add focused tests for tab label, swarm selection, missing-main disabled composer, and send target selection.

### Phase 4: persistence and remote swarms

- Auto-watch configured swarms even without the UI open, if desired.
- Support remote members via registry-discovered target addresses.
- Delegate group watches to remote trackers using existing registry event paths.

## Minimal test plan

Backend/config:

- `agent add --swarm s1 --role main` stores normalized `swarms`.
- Repeated `--swarm/--role` stores multiple memberships.
- Invalid role is rejected.
- Agent register/list includes `swarms`.
- Unregistering/removing an agent removes it from `list_swarms`.
- Duplicate main produces a warning.

TUI:

- Bottom tab shows `Swarm Mode` instead of `Advanced Chat`.
- In swarm mode, `Ctrl-N` / `Ctrl-P` changes selected swarm.
- Composer sends to main agent, not arbitrary selected subagent.
- Missing main disables composer.
- Swarm timeline renders sender → recipient labels.

## Open questions

1. Should multiple main agents be a hard config error or a runtime warning?
2. Should the UI allow sending direct instructions to a subagent from Swarm Mode, or strictly main-only?
3. Should swarm timelines be captured only while UI is open in phase 1, or should tracker auto-watch all configured swarms?
4. How should cross-machine swarms name members: `host/agent`, `registry:host/agent`, or by stable agent id?
5. Should saved messages remember their source swarm?
