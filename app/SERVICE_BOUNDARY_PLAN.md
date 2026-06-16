# MemoryService / TaskService boundary plan

Phase 0 mapping for splitting Broccoli Comms database access currently concentrated in `app/learning_kernel.py`.

## Current structure

`LearningKernel` currently owns all of these responsibilities in one module/class:

- SQLite connection/bootstrap/migration: `connect`, `_init`, `_migrate_working_states`, schema DDL.
- Shared infrastructure: text sanitization helpers, row mappers, event insertion, replay-safe payload cleaning, user profile bootstrap.
- Task domain: task CRUD, dependency gating, participant/default participant CRUD, next-task selection, working state CRUD, task result marking, completion approval workflow, approval listing/showing/reviewing, task-chain summaries.
- Memory domain: payload validation, proposal/idempotency, approval/edit/archive proposal handling, direct edit/rollback/reject/revoke transitions, active/pending limits, list/search/show/history/budget/bootstrap selection.
- CLI call sites in `app/broccoli-comms.py` call `learning_kernel().task_*`, `state_*`, approval methods, summary methods, and `memory_*` directly.

## Memory DB access map

Primary methods in `LearningKernel`:

- Validation/shared memory helpers: `_require_trusted_memory_actor`, `_clean_memory_payload`, `_memory_event_payload`, `_reject_forbidden_memory_metadata`, `_clean_expertise_metadata`, `_memory_idempotency_payload`, `_validation_event_for_task`, `_memory_snapshot_for_version`, `_active_limit_conflict`.
- Mutating APIs: `memory_propose`, `memory_approve`, `memory_propose_edit`, `memory_propose_archive`, `memory_edit`, `memory_rollback`, `memory_reject`, `memory_revoke`, `_approve_memory_edit_proposal`, `_approve_memory_archive_proposal`, `_memory_transition`.
- Read APIs: `memory_show`, `memory_history`, `memory_list`, `memory_search`, `memory_budget`, `memory_for_bootstrap`.
- Tables touched: `memory_records`, `events`, and source-validation reads from `tasks`/`events`.
- CLI wrappers: `memory_propose`, `memory_decide`, `memory_edit`, `memory_rollback`, `memory_reject`, `memory_revoke`, `memory_list`, `memory_approvals`, `memory_search`, `memory_show`, `memory_history`, `memory_budget`, bootstrap context generation.

## Task DB access map

Primary methods in `LearningKernel`:

- Task CRUD/gating: `task_create`, `task_show`, `task_list`, `task_next`, `task_ready_dependents`, `task_update`, `_validate_deps`, `_task_next_statuses`.
- Participant/default participant APIs: `task_chain_default_participant_set`, `task_chain_default_participant_list`, `_chain_default_participants_for_create`, `_upsert_task_participant_in_tx`, `_task_participants_for_task`, `task_participant_list`, `task_participant_add`, `task_participant_update`, `task_participant_remove`.
- Working state APIs: `state_set`, `state_show`, `state_list`, `state_clear`.
- Result/review/approval APIs: `mark_result`, `submit_completion`, `review_completion`, `list_approvals`, `show_approval`, `record_approval_notification`, `_mark_result_in_tx`, `_validated_result_fields`, `_assert_direct_completion_allowed`, `_assert_chain_completion_allowed`, `_tasks_for_completion_chain`.
- Chain summary APIs: `_chain_events`, `summarize_chain`, `latest_chain_summary`.
- Tables touched: `tasks`, `working_states`, `task_participants`, `task_chain_default_participants`, `task_approvals`, `task_chain_summaries`, `events`, plus `user_profiles` in bootstrap paths.
- CLI wrappers: task create/show/list/next/update/participant/defaults/submit/review/list approvals/summarize/bootstrap/state commands.

## Proposed service boundaries

### Shared kernel/database context

Keep in `LearningKernel` or a small shared base/context:

- `connect`, `_init`, schema migration/bootstrap, `event`, row mappers, shared sanitizers/constants.
- Dependency injection point for services: `self.tasks`, `self.memory`, or lazily constructed `TaskService(self)` / `MemoryService(self)`.
- Compatibility wrappers on `LearningKernel` during migration so existing CLI/tests can continue calling `learning_kernel().memory_*` and `task_*` until call sites are migrated.

### MemoryService

Own memory-record lifecycle and memory-specific validation:

- Public methods: `propose`, `approve`, `propose_edit`, `propose_archive`, `edit`, `rollback`, `reject`, `revoke`, `show`, `history`, `list`, `search`, `budget`, `for_bootstrap`.
- Private helpers: memory payload validation, idempotency payloads, active/pending limits, edit/archive proposal approval, memory status transitions, snapshot lookup, validation-event lookup.
- Uses shared context for connection/event/row mapping. It may read tasks/events for source validation but should not own task mutation.

### TaskService

Own task, participant, working-state, result/approval, and chain-summary workflows:

- Public task methods: `create`, `show`, `list`, `next`, `ready_dependents`, `update`.
- Public participant methods: `chain_default_participant_set/list`, `participant_list/add/update/remove`.
- Public state methods: `state_set/show/list/clear` (or nested `TaskStateService` only if this grows further).
- Public result/review methods: `mark_result`, `submit_completion`, `review_completion`, `list_approvals`, `show_approval`, `record_approval_notification`.
- Public chain-summary methods: `summarize_chain`, `latest_chain_summary`.
- Private helpers: dependency validation, participant upsert/compatibility rows, review-role checks, direct completion gating, chain completion gating, chain event collection.

## Migration order

1. **Characterization / guardrails**: keep existing `app/test_learning_kernel.py` as the main regression suite. Add focused tests only for service delegation/compatibility if not already covered in the implementation phase.
2. **Introduce MemoryService first**: move memory helpers and APIs with minimal edits. Add `LearningKernel.memory_service` property and compatibility wrappers (`memory_propose` -> `self.memory.propose(...)`). Run memory-focused tests plus full learning-kernel tests.
3. **Introduce TaskService next**: move task/state/participant/result/approval/summary helpers in slices. Keep wrappers (`task_create`, `state_set`, `mark_result`, etc.) until CLI migration is safe.
4. **Migrate CLI call sites**: update `app/broccoli-comms.py` wrappers from `learning_kernel().memory_*`/`task_*` to `learning_kernel().memory.*` and `learning_kernel().tasks.*` where practical. Preserve old LearningKernel methods for one compatibility window if useful.
5. **Cleanup**: remove or reduce compatibility wrappers only after tests and CLI call sites are migrated; split tests into service-focused sections if file size becomes unwieldy.

## Risks / constraints

- Preserve append-only event ordering and transaction boundaries; service methods that currently call helper methods inside a transaction must keep using the same connection.
- Avoid circular service dependencies. MemoryService may validate a source task through shared read helpers; TaskService should not depend on MemoryService.
- Keep trusted-memory actor checks and source-task validation unchanged.
- Keep reviewer/verifier completion gating and notification-facing result/status semantics unchanged.
- Do not combine CLI behavior changes with service extraction phases.

## Phase 0 recommendation

Proceed with implementation in scoped phases:

1. MemoryService extraction with compatibility wrappers.
2. TaskService extraction for task CRUD/participants/state.
3. TaskService extraction for approvals/results/chain summaries and CLI call-site migration/cleanup.

## Phase 3 cleanup notes

The public service boundary is now `learning_kernel().memory.*` for memory workflows and `learning_kernel().tasks.*` for task, working-state, result, approval, and chain-summary workflows. CLI call sites should use those service objects instead of legacy `learning_kernel().memory_*`, `task_*`, `state_*`, or result/approval methods.

Intentional deferred direct access:

- SQLite connection setup, schema DDL/migrations, row mappers, event insertion, payload sanitization, and profile bootstrap remain in `LearningKernel` as shared infrastructure used by both services.
- Memory and task SQL implementations currently remain as private `LearningKernel._memory_*`, `_task_*`, `_state_*`, and approval/summary helpers. `MemoryService` and `TaskService` delegate to these private implementations for this compatibility window so transaction boundaries, append-only event ordering, idempotency, notifications, and existing tests stay unchanged.
- Legacy compatibility wrappers are provided by `LearningKernel.__getattr__` and are intentionally retained until external callers and tests have completed at least one stable release cycle on the service APIs.
- Cross-domain reads are intentionally limited: memory source validation may read task/event data through shared kernel helpers, while `TaskService` does not depend on `MemoryService`, avoiding circular service coupling.

Future cleanup can move private SQL implementations from `LearningKernel` into the service classes once the service API is stable; do that in smaller behavior-preserving slices with focused regression tests around transaction/event ordering.
