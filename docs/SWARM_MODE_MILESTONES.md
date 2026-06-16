# Swarm Mode Milestones

This document tracks the simplified Swarm Mode path that is currently supported.

## Milestone 0: audit and contract

Validated outcome:

- Live swarm assignment uses running local agents.
- Configured swarm startup uses top-level `swarms.<name>.members` in Broccoli Comms `config.json`.
- Per-agent swarm membership remains compatibility metadata, not the configured startup source of truth.
- Durable timelines should not depend on transient watch leases.

## Milestone 1: simplified backend/CLI

Supported commands:

```sh
broccoli-comms agent assign-swarm backend-fix --main planner --subagent coder-a
broccoli-comms agent start-swarm backend-fix
```

Backend/API contract:

- `assign_live_swarm` assigns existing live local agents.
- `assign_swarm` is a compatibility alias for `assign_live_swarm`.
- `agent start-swarm` reads top-level configured swarm members and reconciles those agents.
- Unsupported legacy-only configured startup errors clearly.

Validation:

- Focused app CLI tests.
- Tracker alias test.
- `nix flake check`.

## Milestone 2: TUI Swarm Mode UX

Supported UI guidance:

- Empty state shows `/swarm create ...` for live agents.
- Empty state shows `broccoli-comms agent start-swarm ...` for configured swarms.
- Composer sends only to the selected swarm main.
- Obsolete setup hints are hidden.

Validation:

- TUI tests assert new hints and reject obsolete hints.
- `cd agent-communicator-tui && nix develop --command go test ./...`.
- `nix flake check`.

## Milestone 3: docs and skills

Docs/skills should describe only supported simplified flows:

- Live: `/swarm create ...` or `broccoli-comms agent assign-swarm ...`
- Configured: top-level `swarms.<name>.members` plus `broccoli-comms agent start-swarm ...`

Remove or rewrite references to unsupported per-agent swarm launch flags and transient-watch-as-persistence guidance.

## Future work

- Remote swarm visibility and registry propagation.
- Historical/archived swarm identities.
- Additional migration helpers for old per-agent swarm metadata.
