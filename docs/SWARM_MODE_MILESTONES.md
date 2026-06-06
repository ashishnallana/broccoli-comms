# Swarm Mode Milestones

## Working model

- `swarm-tracker-coder`: owns CLI/config/wrapper/tracker/registry-adjacent backend work.
- `tabs-coder`: owns TUI Swarm Mode work.
- Reviewer: review changes after each milestone, keep scope small, and prevent backend/TUI contract drift.

## Milestone 0: lock the local contract

Goal: agree on the smallest local-only API and data shape before implementation.

Deliverables:

- Agent config shape:

```json
"swarms": [{"name": "backend-fix", "role": "main"}]
```

- Tracker list row includes:

```json
"swarms": [{"name": "backend-fix", "role": "subagent"}]
```

- `list_swarms` response shape:

```json
{
  "swarms": [
    {
      "name": "backend-fix",
      "main": {"name": "planner", "agent_id": "...", "target_address": "planner"},
      "members": [
        {"name": "planner", "role": "main", "agent_id": "...", "target_address": "planner"},
        {"name": "coder-a", "role": "subagent", "agent_id": "...", "target_address": "coder-a"}
      ],
      "warnings": []
    }
  ]
}
```

- Swarm timeline message shape:

```json
{
  "message_id": "...",
  "sender": "planner",
  "recipient": "coder-a",
  "timestamp": "...",
  "message": "..."
}
```

Acceptance:

- Both backend and TUI agents use these names/shapes.
- Local-only is the first target; registry/remote support is not a blocker.

## Milestone 1: backend metadata plumbing

Owner: `swarm-tracker-coder`

Goal: make swarm membership show up in local tracker agent rows.

Scope:

- Add `--swarm` and `--role main|subagent` to `broccoli-comms track`.
- Add same flags to `broccoli-comms agent add`.
- Normalize persisted config to `swarms: [{name, role}]`.
- Pass swarm metadata through managed launch → `track` → `agent-wrapper`.
- Include `swarms` in wrapper `register` RPC payload.
- Store `swarms` in tracker agent state.
- Include `swarms` in `agent-tracker list` output.

Tests:

- `agent add --swarm s1 --role main` persists normalized config.
- Invalid role rejected.
- `register` with swarms produces list output with swarms.
- Agent in multiple swarms is represented as multiple membership objects if repeated flags are implemented in this milestone.

Acceptance:

- `broccoli-comms agent-tracker list` shows swarm metadata for locally tracked agents.
- Existing tests still pass.

## Milestone 2: tracker swarm read API

Owner: `swarm-tracker-coder`

Goal: derive swarms from current agents and expose them to the TUI.

Scope:

- Add `list_swarms` RPC derived from agent metadata.
- Add warning behavior:
  - no main
  - duplicate main
- Add `get_swarm_timeline` as a wrapper over existing group timeline storage.
- Add `watch_swarm` as a small wrapper over existing group-watch behavior.
- Use local group id convention: `swarm:local:<swarm-name>`.

Tests:

- `list_swarms` groups main/subagents correctly.
- Agent in multiple swarms appears in each swarm.
- Unregister removes agent from all derived swarms.
- Missing main and duplicate main warnings are returned.
- `watch_swarm` records observed traffic among members using existing group timeline primitives.

Acceptance:

- TUI can call `list_swarms` and render local swarm membership.
- Removing/unregistering an agent removes it from derived swarms without separate cleanup code.

## Milestone 3: TUI Swarm Mode shell

Owner: `tabs-coder`

Goal: replace user-visible Advanced Chat tab with Swarm Mode and show swarm membership.

Dependencies:

- Can begin with a stub/fake client shape from Milestone 0.
- Full integration depends on Milestone 2.

Scope:

- Replace `Advanced Chat` tab label with `Swarm Mode`.
- Add TUI swarm state:
  - `swarms []swarmRow`
  - `selectedSwarm int`
  - `swarmMessages []...`
- Add tracker client methods for `list_swarms`, `get_swarm_timeline`, and optionally `watch_swarm`.
- In Swarm Mode, `Ctrl-N` / `Ctrl-P` switches swarms.
- Render selected swarm, main agent, subagents, and warnings.
- Empty state includes setup examples.

Tests:

- Bottom tab renders `Swarm Mode`.
- `Ctrl-N` / `Ctrl-P` changes selected swarm in swarm mode.
- Missing main warning renders.
- Empty state renders setup guidance.

Acceptance:

- TUI can display local swarm rows when backend API is available.
- If API is missing or returns no swarms, UI degrades clearly.

## Milestone 4: TUI send-to-main and timeline

Owner: `tabs-coder`

Goal: make Swarm Mode useful for user interaction and observation.

Scope:

- Implement `currentSendTarget()`:
  - Simple Chat → selected agent
  - Swarm Mode → selected swarm main
  - Saved Messages → no target
- Composer placeholder: `message main agent in <swarm>`.
- Disable composer if selected swarm has no main.
- Render swarm timeline as `sender → recipient` messages.
- Hook refresh/events to reload selected swarm timeline.

Tests:

- Enter in Swarm Mode sends to main agent only.
- Missing main returns no send command and preserves draft.
- Timeline renders sender → recipient labels.
- Switching swarms reloads/changes displayed timeline.

Acceptance:

- User can talk to main agent from Swarm Mode.
- User can observe messages among swarm members.

## Milestone 5: registry/remote swarm metadata

Owner: `swarm-tracker-coder`

Goal: make swarm membership visible across registry-connected machines.

Scope:

- Include agent `swarms` in registry heartbeat payloads.
- Store `swarms` in registry state.
- Include `swarms` in `/agents` responses.
- Ensure remote agent rows preserve `swarms`.

Tests:

- Heartbeat with swarm metadata persists in registry.
- `/agents` includes swarm metadata.
- Tracker remote list preserves remote swarm membership.

Acceptance:

- Remote swarm members are discoverable through registry.

## Milestone 6: remote delegated swarm timelines

Owner: `swarm-tracker-coder`, with TUI follow-up by `tabs-coder` if needed.

Goal: observe cross-machine swarm traffic.

Scope:

- Resolve remote members by `registry:host/agent`, `host/agent`, or stable agent id.
- Reuse delegated group-watch events:
  - `watch_group_request`
  - `group_message_observed`
- Append observed remote traffic to local swarm timeline.

Tests:

- Delegated watch request is published for remote members.
- Remote observed message is appended to swarm timeline.
- TUI can render remote sender/recipient labels.

Acceptance:

- Cross-machine swarms can be observed in Swarm Mode.

## Auto-advance workflow

After a milestone is implemented:

1. The owner reports files changed, tests run, and open issues.
2. Reviewer validates the milestone.
3. If validation passes, the owner may immediately move to the next milestone they own.
4. If validation fails, the owner fixes only review-blocking issues before advancing.

Current ownership chain:

- `swarm-tracker-coder`: Milestone 1 → Milestone 2 → Milestone 5 → Milestone 6 backend portions.
- `tabs-coder`: Milestone 3 → Milestone 4 → Milestone 6 TUI portions if needed.

Local build/runtime validation:

- When a milestone is ready, run package-level tests first.
- Then run a local Broccoli build/test using the existing Broccoli socket/runtime where practical.
- Do not restart or replace the user's active runtime unless explicitly approved; prefer commands that point at the existing `AGENT_TRACKER_SOCKET`.

Suggested local validation commands:

```sh
python3 -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-registry/*.py
cd agent-communicator-tui && nix develop . -c go test ./...
nix build .#broccoli-comms
AGENT_TRACKER_SOCKET=${AGENT_TRACKER_SOCKET:-} ./result/bin/broccoli-comms status --json
```

## Suggested start now

Start Milestone 1 and Milestone 3 in parallel:

- `swarm-tracker-coder`: implement Milestone 1.
- `tabs-coder`: implement Milestone 3 against the contract in Milestone 0, using stubs/fakes where backend is not ready.

After Milestone 1 is validated, `swarm-tracker-coder` should auto-advance to Milestone 2. After Milestone 3 is validated and Milestone 2 API is stable enough, `tabs-coder` should auto-advance to Milestone 4.
