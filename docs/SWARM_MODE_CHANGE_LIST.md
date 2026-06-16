# Swarm Mode Change List

Current supported Swarm Mode work is scoped to two setup flows and the TUI that presents them.

## Supported user flows

1. **Assign live local agents**
   - TUI composer: `/swarm create backend-fix --main planner --subagent coder-a`
   - CLI: `broccoli-comms agent assign-swarm backend-fix --main planner --subagent coder-a`
   - Backend RPC: `assign_live_swarm` (`assign_swarm` remains a compatibility alias)
   - This updates already-running local agent swarm metadata; it does not launch agents.

2. **Start configured swarm members**
   - Config source of truth: top-level `swarms.<name>.members` in Broccoli Comms `config.json`
   - CLI: `broccoli-comms agent start-swarm backend-fix`
   - This reconciles/starts configured local member agents and reports launched vs already-running members.

## TUI changes

- Swarm Mode empty state should mention only `/swarm create ...` and `broccoli-comms agent start-swarm ...`.
- Composer sends only to the selected swarm main agent.
- Missing/offline/no-target main disables the composer with concise guidance.
- Sidebar shows swarm name, main, members, and warnings using Simple Chat style tokens.
- Obsolete per-agent swarm launch/persistence hints should not appear in user-facing Swarm Mode UI.

## Backend/CLI changes

- Keep `list_swarms` as the read API for configured/running/remote-visible swarm rows.
- Keep `get_swarm_timeline` as the durable timeline read API.
- Keep `assign_live_swarm` as the canonical live-assignment RPC.
- Keep `assign_swarm` only as a compatibility alias to avoid Method-not-found failures from older clients.
- `agent start-swarm` should reject missing top-level config, empty members, missing configured agents, and legacy per-agent-only membership with clear errors.

## Validation

- App CLI tests cover `agent assign-swarm`, `agent start-swarm`, and legacy-only rejection.
- Tracker tests cover `assign_swarm` alias parity.
- TUI tests cover new empty-state guidance and absence of obsolete setup hints.
- Full validation should include focused tests and `nix flake check`.
