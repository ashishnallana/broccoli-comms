# Reproducible Learning Agents Design

## Goal

Build a Broccoli Comms workflow where agents are reproducible, cwd-agnostic, task-driven, and learn only from validated outcomes.

Agents should be disposable processes that start in ephemeral `/tmp` workspaces. Durable state lives in Broccoli Comms and is accessed through `broccoli-comms` CLI/RPC. Agents do not rely on terminal scrollback, local cwd files, or previous process state for memory.

## Core Principles

1. **Agent processes are ephemeral**
   - Each agent instance starts in `/tmp/broccoli-agents/<profile>/<session-id>/` or equivalent.
   - Anything in the ephemeral workspace is disposable unless explicitly saved through Broccoli Comms.

2. **Agent profiles are durable**
   - A profile is the stable identity: `tui-coder`, `reviewer`, `pi-swarm-main`.
   - An instance is a running process: `tui-coder@session-abc123`.
   - Task assignment is primarily to profiles, not processes.

3. **All durable coordination happens through Broccoli Comms**
   - Tasks, working state, user profile, append-only events, later artifacts/memory/capabilities.
   - Agents use CLI/RPC commands rather than writing durable memory themselves.

4. **Append-only log records facts, not conclusions**
   - Each task/state/result transition appends structured events.
   - Later auditor jobs derive episodes, habits, expertise, capability evidence, and one-shot reliability from validated logs.

5. **Learning requires validation**
   - Agent chat or self-report can create candidate evidence only.
   - Capability/expertise memory is updated only after the user marks a task result as `good`, `bad`, or `need_improvements`.

6. **User profile is shared context**
   - User preferences/habits/policies are available to all agents.
   - Example: concise updates, run relevant tests, review-before-push, avoid raw output leakage.
   - User profile is read-only to agents in Phase 1.

## Phase 1 Scope

Implement a local-only durable task/checkpoint kernel:

- Task management
- WorkingState management
- read-only UserProfile display/bootstrap
- append-only event log for task/state/result/user validation events
- generated `AGENTS.md` in each ephemeral agent workspace

Out of scope for Phase 1:

- artifact content store
- capability scoring
- memory proposal/review UI
- validated episode search
- remote registry sync
- delegation protocol
- rich scheduler
- automatic memory mutation

## Data Model

### AgentProfile

Stable named identity used for task assignment and bootstrap.

Fields:

- `agent_name`
- `persona_summary`
- `default_command`
- `default_tools` optional
- `default_scope` optional
- `created_at`, `updated_at`

Phase 1 may reuse existing configured agent records rather than adding a full profile table.

### AgentInstance

Running process identity.

Fields:

- `instance_id`
- `agent_name`
- `session_id`
- `ephemeral_cwd`
- `tmux_pane` optional
- `pid` optional
- `status`: `starting|idle|working|stale|stopped`
- `started_at`, `last_seen_at`, `stopped_at`

### Task

A durable unit of work.

Fields:

- `task_id`: generated stable ID
- `title`
- `description` / `objective`
- `status`: `queued|ready|working|blocked|review|done|validated|archived`
- `assigned_agent`: optional agent profile name
- `scope`: optional opaque string, e.g. `repo:broccoli-comms`, `project:<id>`, `swarm:<name>`
- `depends_on`: list of task IDs
- `priority`: optional, default `normal`
- `next_step`: coordinator/task-level next action
- `acceptance_criteria`: list of strings
- `context_refs`: optional list of strings for message IDs, URLs, repo refs, future artifact IDs
- `result_summary`: optional
- `result_status`: optional user validation result: `good|bad|need_improvements`
- `result_notes`: optional user validation notes
- `blocked_reason`: optional/recommended when status is `blocked`
- `created_by`, `updated_by`
- `created_at`, `updated_at`
- `version`

Status semantics:

- `queued`: exists but not yet eligible for `task next`
- `ready`: eligible when dependencies are satisfied
- `working`: assigned/in progress
- `blocked`: needs external action; not eligible until manually updated
- `review`: implementation/result ready for review
- `done`: agent/coordinator says complete; dependencies may be satisfied in Phase 1
- `validated`: user/reviewer accepted result; dependencies satisfied
- `archived`: hidden from normal list/next

Dependency rule for Phase 1:

- A dependency is satisfied if its status is `done` or `validated`.
- No rich DAG scheduling, conditional branches, or resource allocation yet.

### WorkingState

Live checkpoint for a specific agent on a task.

Fields:

- `state_id` or composite key `(task_id, agent)`
- `task_id`
- `agent`
- `instance_id` optional
- `status`: `working|blocked|waiting|review|done`
- `current_activity`: short description; avoids duplicating task title
- `next_step`: agent-specific next action
- `blockers`: list of strings
- `notes` / `checkpoint_summary`: bounded text
- `last_checkpoint_at` / `updated_at`
- `stale_after_seconds` optional
- `version`

`Task.next_step` is coordinator/user-level. `WorkingState.next_step` is agent-local execution state.

### UserProfile

Shared user preferences and policies.

Fields:

- `profile_id`: usually `default`
- `format`: `markdown|json`
- `body` or structured preferences
- `source`: local user-authored config path or DB record
- `updated_at`
- `version`

Rules:

- Read-only to agents in Phase 1.
- Private local by default.
- Must not contain secrets/tokens.

### AppendOnlyEvent

Durable historical facts used for audit and future memory extraction.

Fields:

- `event_id`
- `event_type`
- `timestamp`
- `actor_type`: `user|agent|system|reviewer|auditor`
- `actor_id`
- `agent_instance_id` optional
- `subject_type`: `task|working_state|agent_profile|agent_instance|user_profile`
- `subject_id`
- `task_id` optional
- `scope` optional
- `payload`: structured JSON, safe metadata only
- `refs`: optional structured refs: message IDs, task IDs, future artifact IDs
- `visibility`: default `private`
- `schema_version`

Phase 1 event types:

- `task_created`
- `task_updated`
- `task_status_changed`
- `task_assigned`
- `task_result_marked`
- `working_state_set`
- `working_state_cleared`
- `working_state_stale_detected`
- `agent_instance_started`
- `agent_instance_stopped`
- `agent_instance_stale`
- `bootstrap_generated`
- `user_profile_shown` optional/debug only

Do not log raw terminal output, full transcripts, secrets, or arbitrary file contents by default.

## Storage

Phase 1 should use local private SQLite under the Broccoli Comms state directory.

Requirements:

- SQLite database with `schema_version`
- WAL enabled if practical
- atomic updates: materialized row update + append log event in same transaction
- all mutating commands append events automatically
- `version` or `updated_at` support for optimistic concurrency/lost-update prevention

Avoid ad-hoc JSON files for task/state/event storage because multiple agents, TUI, and CLI may write concurrently.

## Generated `AGENTS.md`

Every launched ephemeral agent workspace gets an auto-generated `AGENTS.md` containing its operating contract.

Example:

```md
# Agent Operating Contract

You are: tui-coder
Agent profile: tui-coder
Instance: tui-coder@session-abc123
Ephemeral cwd: /tmp/broccoli-agents/tui-coder/session-abc123

Durable state lives in Broccoli Comms. Do not rely on this cwd for memory.

## Required startup
1. Run `broccoli-comms task next --agent tui-coder --include-profile`.
2. If a task is returned, run `broccoli-comms state show --task <task_id> --agent tui-coder`.
3. If no task is ready, stand by and do not invent work.

## Work rules
- Update WorkingState when starting, blocking, requesting review, or finishing.
- Ask user/coordinator for context if confidence is low.
- Explicit user instructions override task/profile/habits.
- Save durable outputs only through Broccoli Comms commands.
- Do not store secrets or raw terminal output in memory/state.
```

The file is a bootstrap contract, not durable memory.

## Agent Startup Flow

1. Broccoli starts agent profile `A`.
2. Creates fresh `/tmp/...` workspace.
3. Writes `AGENTS.md`.
4. Registers an `AgentInstance`.
5. Appends `agent_instance_started` and `bootstrap_generated` events.
6. Agent reads `AGENTS.md` automatically through its normal startup context.
7. Agent calls:
   - `broccoli-comms user-profile show`
   - `broccoli-comms task next --agent A --include-profile`
   - `broccoli-comms state show --task TASK --agent A`
8. If ready task exists, agent either starts or asks for context if confidence is low.

## Task Execution Flow

1. User/coordinator creates a task.
2. Agent calls `task next` and receives task fields, acceptance criteria, and user profile.
3. Agent evaluates readiness:
   - task clear?
   - acceptance criteria clear?
   - required tools available?
   - has sufficient expertise/prior examples? Later phase.
4. If not ready:
   - set WorkingState `blocked` or `waiting`
   - ask user/coordinator for context
5. If ready:
   - update task status `working`
   - set WorkingState with `current_activity` and `next_step`
6. During work:
   - periodically checkpoint WorkingState
7. On completion:
   - update task status `review` or `done`
   - include `result_summary` and `next_step`, e.g. `wait for user validation`
8. User marks result:
   - `good`: task may become `validated`
   - `bad`: task remains/reopens with next_step explaining remediation
   - `need_improvements`: task returns to `ready|working|blocked` depending on next action
9. Event log records all transitions.

## User Result Validation

Users should be able to mark each task result:

- `good`: result is correct/useful; eligible for later memory/capability promotion
- `bad`: result incorrect/not useful; creates negative evidence later
- `need_improvements`: partially useful but needs follow-up; creates partial evidence later

Phase 1 only records this on the Task and appends `task_result_marked`. It does not update capabilities yet.

Future memory auditor behavior:

- `good` may promote validated episode/evidence.
- `bad` may record validated failure/known limitation.
- `need_improvements` may record partial evidence and fix-cycle count.

## CLI Shape

Tasks:

```bash
broccoli-comms task create \
  --title "Implement swarm bubbles" \
  --description "Make swarm mode message bubbles match simple chat" \
  --agent tui-coder \
  --scope repo:broccoli-comms \
  --next-step "Inspect rendering" \
  --acceptance "go test ./... passes" \
  --json

broccoli-comms task show TASK [--json]
broccoli-comms task list [--agent A] [--status ready,working] [--include-archived] [--json]
broccoli-comms task next [--agent A] [--scope S] [--include-profile] [--json]
broccoli-comms task update TASK [--status STATUS] [--next-step S] [--blocked-reason S] [--result-summary S] [--assign-agent A] [--json]
broccoli-comms task mark-result TASK --result good|bad|need_improvements [--notes S] [--json]
```

Working state:

```bash
broccoli-comms state set \
  --task TASK \
  --agent tui-coder \
  --status working \
  --current-activity "fix receipt row" \
  --next-step "run go tests" \
  --notes "Changed bubbles.go and swarm_test.go" \
  --json

broccoli-comms state show --task TASK [--agent A] [--json]
broccoli-comms state list [--agent A] [--task TASK] [--stale-after 30m] [--json]
broccoli-comms state clear --task TASK [--agent A] [--json]
```

User profile:

```bash
broccoli-comms user-profile show [--format markdown|json] [--json]
```

Bootstrap convenience:

```bash
broccoli-comms task bootstrap --agent A --json
```

Returns user profile + next task + current state + AGENTS.md contract summary.

All commands should support `--json`. `--agent` should default to current registered agent where reliable.

## Edge Cases

### Task assigned to non-running agent

Allowed.

- Task remains `ready` or `queued`.
- UI/CLI shows `assigned_agent=tui-coder offline`.
- When agent starts, it calls `task next` and picks it up.

### Duplicate active agents with same profile

Default: not allowed to silently share the same profile/task queue.

Policy:

- Stable names identify profiles.
- Running processes are instances.
- Only one active instance should claim a profile/task at a time unless explicit parallelism is requested.

If duplicate active instances appear:

- mark profile conflict
- pause automatic task claiming for that profile
- coordinator resolves via stop/rename/takeover

Allowed duplicate cases:

1. Replacement: old instance stale/dead; new instance takes over.
2. Explicit parallelism: user creates distinct profiles/instances, e.g. `tui-coder-a`, `tui-coder-b`.
3. Swarm roles: multiple agents share template but have distinct profile names.

### Instance dies mid-task

- WorkingState becomes stale by `updated_at` / heartbeat timeout.
- Task remains assigned to profile.
- Claim expires or is manually released.
- New instance can recover via `task next` and `state show`.

### Stale working state

- `state list --stale-after 30m` identifies old checkpoints.
- Later system may append `working_state_stale_detected`.
- Stale state does not automatically mean task failed.

### Conflicting updates

- Use SQLite transactions and `version`.
- If command updates an old version, return conflict and ask caller to reload.
- At minimum, append events so lost updates can be audited.

### Dependencies

- Phase 1 readiness: all dependencies must be `done` or `validated`.
- Cycles should be rejected on task creation/update.
- Missing dependency IDs should be rejected.
- If dependency later becomes `bad` or reopened, dependent task should not auto-roll back in Phase 1; coordinator must update.

### Low-confidence agent

Agent should not guess.

It should:

- set WorkingState to `blocked` or `waiting`
- set `next_step` to ask for context or delegate
- send message to user/coordinator

### User marks result bad/need_improvements

- Append `task_result_marked`.
- `bad` should normally move task to `blocked` or `ready` with a remediation `next_step`.
- `need_improvements` should keep result summary and specify follow-up next_step.
- Future memory auditor records negative/partial evidence only after validation.

### User profile contains secrets

- User profile command should warn that profile must not contain secrets.
- Phase 1 should not sync profile remotely.
- Future phase can add redaction/secrets detection.

### AGENTS.md stale after task changes

`AGENTS.md` is a static operating contract, not live task state.

Agents must still call `task next` / `state show` to get current work.

### Agent not registered but CLI called with --agent

Allowed for planning commands.

- `task create --agent missing-agent` is valid.
- `state set --agent missing-agent` should probably warn or reject unless `--allow-offline` is supplied, because WorkingState is normally live agent state.

### Remote agents

Out of scope in Phase 1.

- Tasks/state are local-only/private.
- No registry sync.
- Later remote capability cards and delegation can be added explicitly.

## Acceptance Tests

1. Create a task assigned to an offline agent; task appears in list and is returned after the agent starts.
2. Fresh agent with empty cwd can run `task next --include-profile` and receive objective, acceptance criteria, next_step, and profile.
3. `state set`, process restart, `state show` returns checkpoint.
4. `task next` excludes tasks whose dependencies are not `done|validated`.
5. Mark dependency `done`; dependent task becomes selectable.
6. `state list --stale-after` identifies old checkpoints.
7. `task mark-result TASK --result good|bad|need_improvements` updates task and appends event.
8. `task list/show/next`, `state show/list`, and `user-profile show` all support `--json`.
9. Concurrent writes do not corrupt the store.
10. Duplicate active profile instances are detected or prevented.
11. Generated `AGENTS.md` exists in ephemeral workspace and contains profile, instance, cwd, and startup commands.
12. Event log can be queried/rebuilt to show the task/state/result timeline.

## Future Phases

Phase 2: artifact save/get and handoff snapshots.

Phase 3: memory proposal/review workflow for episodes, habits, skills, and evidence.

Phase 4: capability materialized views and recommendation engine using validated evidence only.

Phase 5: skill/playbook registry with dependency checks and dry-run support.

Phase 6: delegation and swarm task graph integration.

Phase 7: remote sync of signed, TTL-limited public capability/availability cards only.

Phase 8: privacy/security hardening: redaction, ACLs, encryption, retention, export/import, poison-memory recovery.
