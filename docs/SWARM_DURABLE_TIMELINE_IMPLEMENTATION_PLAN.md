# Swarm Durable Timeline Implementation Plan

## Goal

Make Swarm Mode timelines reliable and durable without depending on an active TUI tab, focus state, or transient watch lease.

Messages among swarm agents should be retained when:

- the TUI is closed,
- Swarm Mode is not selected,
- a configured swarm is not currently running,
- an agent unregisters later,
- members are spread across registry-connected trackers.

## Supported setup model

### Live local agents

Assign already-running agents into a swarm:

```sh
broccoli-comms agent assign-swarm backend-fix --main planner --subagent coder-a
```

The TUI composer equivalent is:

```text
/swarm create backend-fix --main planner --subagent coder-a
```

### Configured local agents

Canonical config uses top-level swarm membership:

```json
{
  "agents": {
    "planner": {"cwd": "/repo", "command": "pi"},
    "coder-a": {"cwd": "/repo", "command": "pi"}
  },
  "swarms": {
    "backend-fix": {
      "members": [
        {"agent": "planner", "role": "main"},
        {"agent": "coder-a", "role": "subagent"}
      ]
    }
  }
}
```

Start/reconcile configured members:

```sh
broccoli-comms agent start-swarm backend-fix
```

Legacy per-agent swarm metadata can be normalized for display, but configured startup should require top-level `swarms.<name>.members` so membership and launchability are explicit.

## Design principles

1. Agents remain independent launchable units with their own `cwd`, `command`, `autostart`, env, and launch details.
2. Configured swarms reference configured agents instead of owning processes.
3. Every tracker-mediated message should be journaled at send/receive time.
4. Timeline rows include a swarm/membership snapshot so history survives later config changes.
5. Cross-tracker event propagation must be idempotent by `message_id` or event id.

## Runtime APIs

- `list_swarms`: returns configured/running/remote-visible swarm rows with main/member metadata and warnings.
- `assign_live_swarm`: assigns a swarm to already-running local agents.
- `assign_swarm`: compatibility alias for older clients.
- `get_swarm_timeline`: reads durable swarm timeline rows.

Transient watch APIs may remain for compatibility but are not the local persistence mechanism.

## Validation focus

- Configured offline members appear in `list_swarms`.
- `agent start-swarm` starts configured members and rejects missing or legacy-only config clearly.
- Message between two swarm members is journaled without requiring the TUI to be open.
- User-to-main messages include swarm context when sent from Swarm Mode.
- Non-swarm messages do not appear in swarm timelines.
- Registry message events merge with local rows without duplicates.
