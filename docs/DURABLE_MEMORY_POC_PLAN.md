# Durable Memory POC Plan

## Goal

Build the smallest persisted-memory layer that lets a fresh/restarted agent in an ephemeral `/tmp` workspace fetch approved memory at startup through Broccoli Comms.

Phase 1 already provides the foundation: Tasks, WorkingState, read-only UserProfile, append-only Events, validation (`good|bad|need_improvements`), task-chain/instance scoping, and generated `AGENTS.md` bootstrap instructions.

This POC adds a durable, user-approved memory view on top of validated events.

## Non-goals

- No capability/expertise scoring.
- No automatic promotion from chat/self-report.
- No vector DB or semantic embeddings.
- No remote sync/registry sharing.
- No artifact store or raw transcript storage.
- No complex skill execution engine.

## Memory types for POC

Implement these first:

1. `fact`
   - Example: “For GitHub CLI latest release, use `https://api.github.com/repos/cli/cli/releases/latest`.”
   - Example: “For revenue queries in project X, use database `analytics_prod`, table `daily_revenue`.”

2. `habit`
   - Example: “For this repo, run targeted unit tests before reporting done.”

3. `episode`
   - Compact validated task summary: goal, approach, result, important reusable discoveries, validation outcome.

4. `expertise`
   - A bounded, validated area-of-competence note for an agent/profile, derived from one or more validated-good tasks.
   - Example: `phase1-persistent-pi has validated experience using GitHub API release endpoints via Python urllib/json.`
   - Example: `repo-coder has validated experience locating Broccoli Comms launch/bootstrap paths.`

`expertise` in this POC is not a score, rank, or automatic delegation recommendation. It is a user-approved memory record with provenance. Later capability/scoring systems may materialize metrics from validated expertise records and episodes.

## Validation gate

Reusable active memory must be grounded in validation.

A memory record can become `active` only by one of these paths:

1. **Validated task source**
   - Proposal references a `source_task_id`.
   - Approval verifies that the source task has `result_status=good` and status `validated`, or that the append-only event log contains a trusted `task_result_marked` / approval decision with `result_status=good` for that task.
   - Approval stores `source_event_seq` for the validation event when available.

2. **Trusted-human manual memory path**
   - A trusted local user/coordinator explicitly creates or approves a memory without a source task using a flag such as `--trusted-manual`.
   - This path must record `created_by` / `validated_by` as a trusted actor and append a `memory_approved` event with `source="trusted_manual"`.

Agent self-report alone must never create active memory.

## Trusted actors and immutable/non-learning rules

- Normal learning-enabled agents may create bounded `pending` proposals only.
- Immutable/non-learning instances must not create `memory_proposed` or other learning-memory events.
- `approve`, `reject`, and `revoke` are restricted to trusted local user/coordinator/task-kernel/UI paths.
- The trust decision must come from local runtime/config/registration metadata, not self-declared message text.
- If a proposal comes from an untrusted or immutable instance, reject it before persistence or store it only as non-learning/transient diagnostics outside the memory event stream.

## Storage model

Add a `memory_records` table to the existing local SQLite DB.

Suggested fields:

```text
memory_id TEXT PRIMARY KEY
idempotency_key TEXT
proposed_by TEXT NOT NULL
proposed_by_instance TEXT
type TEXT NOT NULL                 -- fact|habit|episode|expertise
scope TEXT NOT NULL DEFAULT 'global'
subject_agent TEXT                 -- optional profile/name, e.g. coder-agent
title TEXT NOT NULL
body TEXT NOT NULL                 -- bounded/sanitized markdown/text
source_task_id TEXT                -- required unless trusted_manual=true
source_event_seq INTEGER           -- validation/provenance event when known
source_event_id TEXT
trusted_manual INTEGER NOT NULL DEFAULT 0
created_by TEXT NOT NULL
created_at TEXT NOT NULL
validated_by TEXT
validated_at TEXT
status TEXT NOT NULL DEFAULT 'pending' -- pending|active|rejected|revoked|superseded
status_event_seq INTEGER
updated_event_seq INTEGER
version INTEGER NOT NULL DEFAULT 1
tags TEXT NOT NULL DEFAULT '[]'
metadata TEXT NOT NULL DEFAULT '{}'
schema_version INTEGER NOT NULL DEFAULT 1
```

Recommended uniqueness:

- `UNIQUE(proposed_by, idempotency_key)` when `idempotency_key` is not empty.
- Optional duplicate guard for active memory by `(type, scope, subject_agent, normalized_title)` to avoid accidental duplicates; conflicting duplicates should return an explicit conflict, not silently overwrite.

Important:
- `active` memory requires user/reviewer approval through the validation gate above.
- Raw transcripts, secrets, full query logs, and large file contents are rejected/sanitized.
- Memory records must keep source task/event provenance or trusted-manual provenance.

## Event log integration and transactions

Every memory mutation appends to the append-only event log:

- `memory_proposed`
- `memory_approved`
- `memory_rejected`
- `memory_revoked`
- `memory_superseded` (optional later)

The memory table is the queryable materialized view; the event log is the audit trail/source of truth for mutation history.

Transaction rule:

- Table update and memory event append happen in one SQLite transaction.
- The event sequence from the appended event is stored back into `status_event_seq` / `updated_event_seq` where applicable.
- Failed event append rolls back the materialized row mutation.

## Idempotency and concurrency

### Propose

- `memory propose` accepts an optional `--idempotency-key`.
- Retrying with the same proposer + key + identical payload returns the existing memory record and appends no duplicate event.
- Retrying with the same proposer + key but conflicting payload returns an idempotency conflict.

### Approve/reject/revoke

- Transitions are version checked, e.g. `--expected-version` or `expected_version` in RPC.
- Repeating the same transition against an already transitioned record is idempotent only if the requested state and payload match; it appends no duplicate event.
- Conflicting transitions return an explicit conflict:
  - approving a rejected/revoked record conflicts;
  - rejecting an active/revoked record conflicts unless a future force/supersede flow exists;
  - revoking a pending record should require rejection, not revoke, for POC simplicity.
- Stale UI/CLI actions must fail if `version` or `status_event_seq` changed.


## Per-agent memory budgets and limit behavior

The POC should include hard limits so one agent/profile cannot accumulate unbounded memory or flood bootstrap context.

Recommended configurable limits, with conservative defaults:

```text
memory.max_active_per_agent = 200
memory.max_active_per_agent_fact = 100
memory.max_active_per_agent_habit = 50
memory.max_active_per_agent_episode = 50
memory.max_active_per_agent_expertise = 50
memory.max_active_per_scope = 200
memory.bootstrap_max_records = 20
memory.bootstrap_max_body_chars_per_record = 1000
memory.bootstrap_max_total_chars = 8000
```

Limits apply to `active` records by `subject_agent` and relevant scope. Pending proposals should have a separate smaller cap, e.g. `memory.max_pending_per_agent = 50`, to prevent proposal spam.

When an approval would exceed a limit, the system must not silently drop memory or auto-delete records. Phase-1 behavior should force stale-memory cleanup before new active memory is admitted:

1. Return a limit conflict from `memory approve`, including current count, limit, memory type, agent/scope, candidate memory id, and suggested stale candidates.
2. Require a trusted user/coordinator to revoke stale entries or supersede older memory first.
3. Append explicit `memory_revoked` or `memory_superseded` events for every removed/staled entry.
4. Then retry approval.

Staleness candidates should be deterministic and explainable. Suggested ordering:

1. `revoked/rejected/superseded` records are never counted as active and need no cleanup.
2. active records with `expires_at` or TTL already elapsed;
3. active records explicitly marked `stale_candidate=true`;
4. oldest validated/least recently used records in the same `(subject_agent, type, scope)` bucket;
5. records superseded by the new candidate's `supersedes_memory_id`.

For the POC, do not implement automatic LRU deletion. It is acceptable to return `limit_exceeded` plus stale candidates and require explicit `memory revoke` / `memory supersede` before approval succeeds.

Optional but useful POC command:

```bash
broccoli-comms memory budget --agent AGENT --scope S --json
```

It should show active/pending counts by type and remaining capacity.

Future behavior can add summarization or compression when limits are reached, but Phase 1 should prefer explicit user/coordinator action over automatic deletion.

Bootstrap retrieval must also respect retrieval budgets even if stored memory is below durable storage limits:

- return only active records;
- use deterministic ordering;
- cap returned record count;
- cap per-record body length;
- cap total memory text returned to the agent;
- include `truncated: true` / `omitted_count` metadata when retrieval limits hide records.

## Expertise POC semantics

Expertise records are allowed in the POC only as validated, bounded evidence summaries. They must not become free-form self-praise or an automatic score.

Rules:

- `type=expertise` requires `subject_agent` unless `scope` is explicitly a team/project expertise record.
- It must reference at least one validated-good source task or use a trusted-human manual path.
- The body should state the concrete task family/tool/domain and the evidence basis, not a numeric rating.
- Suggested metadata fields:

```json
{
  "task_family": "github-release-lookup",
  "tools": ["python", "urllib", "json", "github-api"],
  "evidence_task_ids": ["task-..."],
  "validation_count": 1,
  "last_validated_at": "...",
  "known_limits": "bounded optional text"
}
```

Bootstrap retrieval may include relevant active expertise records for the agent/profile, but agents must treat them as context, not authority. Explicit user/task instructions still override expertise memory.

For Phase 1, do not compute scores, confidence, levels, or recommendations. If a future UI wants to show expertise, it should display evidence count and source tasks rather than a ranking.

## CLI/API

Minimal CLI:

```bash
broccoli-comms memory propose \
  --type fact \
  --scope project:broccoli-comms \
  --title "GitHub CLI release lookup endpoint" \
  --body "Use https://api.github.com/repos/cli/cli/releases/latest" \
  --source-task task-... \
  --idempotency-key KEY \
  --tag github --tag cli \
  --json

broccoli-comms memory approve MEMORY_ID --expected-version N --json
broccoli-comms memory reject MEMORY_ID --reason "too broad" --expected-version N --json
broccoli-comms memory revoke MEMORY_ID --reason "obsolete" --expected-version N --json
broccoli-comms memory list [--scope S] [--type fact] [--status active|approved] [--agent A] --json
broccoli-comms memory approvals [--scope S] [--type fact] [--agent A] --json
broccoli-comms memory search --query "github cli release" [--scope S] --json
broccoli-comms memory show MEMORY_ID --json
broccoli-comms memory history MEMORY_ID --json
```

Trusted manual path:

```bash
broccoli-comms memory propose \
  --trusted-manual \
  --type habit \
  --scope project:broccoli-comms \
  --title "Run targeted tests" \
  --body "Run targeted tests before reporting implementation complete." \
  --json
```

Minimal RPC methods can mirror CLI functions:

- `memory.propose`
- `memory.approve`
- `memory.reject`
- `memory.revoke`
- `memory.list`
- `memory.search`
- `memory.show`

Search can be simple case-insensitive substring search over title/body/tags for the POC.

## Bootstrap retrieval

Update:

```bash
broccoli-comms task bootstrap --agent AGENT --json
```

to return relevant active memories:

```json
{
  "task": {...},
  "state": {...},
  "user_profile": {...},
  "memory": [
    {
      "memory_id": "mem_...",
      "type": "fact",
      "scope": "project:broccoli-comms",
      "title": "GitHub CLI release lookup endpoint",
      "body": "Use https://api.github.com/repos/cli/cli/releases/latest",
      "source_task_id": "task-...",
      "source_event_seq": 123,
      "tags": ["github", "cli"]
    }
  ]
}
```

### Scope semantics

- `task.scope` is the primary project/task scope for retrieval.
- For POC, scope is caller-supplied opaque text from task creation/update, e.g. `global`, `project:broccoli-comms`, `repo:<git-remote-or-path-id>`, `agent:<profile>`.
- Do not infer complex project identity automatically in the first POC; add automatic git remote/project derivation later.

### Retrieval rules

Bootstrap returns active memory only:

- include `scope=global`;
- include exact `scope == task.scope` when a task exists;
- include `scope == agent:<agent>` and/or `subject_agent == agent`;
- exclude `pending`, `rejected`, `revoked`, `superseded` by default;
- cap records, e.g. `limit=20`;
- cap body length in bootstrap response, e.g. truncate/summarize to configured safe limit;
- stable ordering:
  1. exact task scope matches,
  2. agent/profile matches,
  3. global memories,
  4. most recently validated,
  5. title / memory_id for deterministic tie-break.

Generated `AGENTS.md` should instruct agents:

- Always read `task bootstrap` at startup.
- Treat returned `memory` as durable approved guidance.
- Do not self-promote memory.
- Propose memory only after validated task outcomes.

## User validation flow

POC flow:

1. Agent completes task and user marks it `good`.
2. Coordinator/user proposes memory from the validated task:

```bash
broccoli-comms memory propose --from-task TASK --type fact ...
```

3. Approval verifies the source validation event and activates memory:

```bash
broccoli-comms memory approve MEM_ID --expected-version N
```

4. A future fresh `/tmp` agent runs `task bootstrap` and receives that approved memory.

Optional convenience for later:

```bash
broccoli-comms memory propose --from-task TASK --interactive
broccoli-comms task mark-result TASK --result good --propose-memory fact:"..."
```

Do not require convenience promotion in the first POC.

## Acceptance tests

1. Propose a `fact` memory from a validated-good task; it starts as `pending` and appends `memory_proposed`.
2. Approve the memory; approval verifies the task validation event, status becomes `active`, and `memory_approved` is appended in the same transaction as the row update.
3. Proposing from an unvalidated/non-good task cannot become active.
4. Trusted manual memory can be approved only by trusted actor path and records trusted-manual provenance.
5. Immutable/non-learning instance cannot propose learning memory.
6. `memory list/search/show --json` returns stable IDs, version, status event seq, provenance, and bounded fields.
7. `task bootstrap --agent A --json` includes matching active memory with deterministic ordering and limits.
8. Fresh agent in `/tmp` can fetch memory without relying on cwd files.
9. Pending/rejected/revoked/superseded memory is not returned by bootstrap by default.
10. Oversized/secret-like/raw transcript text is rejected or sanitized.
11. Propose idempotency key prevents duplicate proposal events on retry.
12. Approve/reject/revoke transitions are idempotent for exact retries and conflict on stale/conflicting transitions.
13. Memory source provenance includes `source_task_id` and validation `source_event_seq` when available.
14. `expertise` memory requires `subject_agent` or explicit team/project scope, validated provenance, and is returned in bootstrap only as bounded context.
15. Expertise POC does not expose score/rank/recommendation fields.

## Suggested implementation phases

### POC-A: Table + CLI + events

- Add `memory_records` schema.
- Add bounded sanitization.
- Add `memory propose/approve/reject/revoke/list/approvals/show/history/search`.
- Enforce validation gate and trusted actor/immutable rules.
- Append memory events atomically with table updates.
- Tests for memory lifecycle, idempotency, and stale conflicts.

### POC-B: Bootstrap retrieval

- Add active approved memory to `task bootstrap` response.
- Filter by global/scope/agent.
- Enforce deterministic limits/order.
- Update generated `AGENTS.md` instructions.
- Tests with fresh `/tmp` bootstrap.

### POC-C: E2E smoke

- Use the existing `phase1-persistent-pi` pattern:
  1. Create validated task discovering a reusable endpoint/database.
  2. Propose + approve memory.
  3. Start a fresh agent instance in `/tmp`.
  4. Confirm bootstrap returns memory and agent can use it without rediscovery.

## Open questions for later

- Should memory approval happen from agent-communicator approval cards?
- Should memory be scoped by git remote/project ID automatically?
- Should memory support content-addressed artifacts later?
- Should skill/playbook memory become executable and tested?
- How should memory be exported/imported or synced remotely?
