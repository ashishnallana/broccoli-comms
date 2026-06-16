# Swarm Mode Design

Swarm Mode is the supported group-agent view in `agent-communicator`. It keeps the user-facing model small:

- A swarm has one intended **main** agent and zero or more **subagents**.
- In Simple Chat, the user talks to a selected agent.
- In Swarm Mode, the user talks only to the selected swarm's main agent.
- The timeline shows traffic among swarm members as `sender → recipient`.

## Supported setup flows

### 1. Create a swarm from live local agents

Use this when the agents are already running in the local Broccoli runtime.

From the TUI Swarm Mode composer:

```text
/swarm create backend-fix --main planner --subagent coder-a --subagent reviewer
```

Equivalent CLI:

```sh
broccoli-comms agent assign-swarm backend-fix \
  --main planner \
  --subagent coder-a \
  --subagent reviewer
```

This assigns swarm metadata to existing live local agents through the tracker. It does not create, configure, or restart agents.

### 2. Start a configured swarm

Use this when the swarm is declared in Broccoli Comms `config.json` and members are configured agents.

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

Start/reconcile the configured members:

```sh
broccoli-comms agent start-swarm backend-fix
```

`start-swarm` starts configured local members that are not already running and reports which members were launched versus already running.

## Unsupported or deprecated setup paths

- Legacy per-agent swarm launch metadata is not the configured-swarm startup model.
- Configured swarms belong in top-level `swarms.<name>.members`.
- Per-agent `agents.<name>.swarms` metadata may be read for compatibility by lower layers, but `agent start-swarm` requires top-level `swarms` config.
- Transient watch leases are not the persistence model for swarm timelines. Durable journal/timeline APIs are the supported direction.

## Runtime/API behavior

- `list_swarms` returns configured, running, and visible swarm members with warnings such as missing or duplicate main agents.
- `assign_live_swarm` is the canonical live-assignment RPC; `assign_swarm` is a compatibility alias.
- `get_swarm_timeline` returns durable timeline rows for the selected swarm.
- Transient watch APIs are compatibility plumbing and should not be required for local durable timeline persistence.

## TUI behavior

- Empty state shows the two supported setup paths: `/swarm create ...` and `broccoli-comms agent start-swarm ...`.
- Composer placeholder is short and Simple Chat-like.
- Composer is disabled when no swarm is selected, the main agent is missing, or the main agent is offline/no-target.
- Sidebar shows selected swarm, main, member count, warnings, and members using existing Simple Chat style tokens.

## Validation focus

- Live assignment: `/swarm create` and `agent assign-swarm` assign running local agents.
- Configured startup: `agent start-swarm` launches top-level configured swarm members and rejects missing/legacy-only configs clearly.
- TUI guidance: no obsolete per-agent swarm launch hints.
- Timeline: messages are rendered as `sender → recipient` and remain available through durable timeline APIs.
