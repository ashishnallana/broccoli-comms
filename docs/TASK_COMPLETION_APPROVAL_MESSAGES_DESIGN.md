# Task Completion Approval Messages Design

## Goal

Allow agents to submit task completion results through Broccoli Comms and automatically surface them in `agent-communicator` as explicit approval messages/cards with distinct styling. The user can approve, reject, or request improvements from `agent-communicator`; the decision is written through the same task validation / `mark-result` path used by the Phase 1 task kernel and becomes the validation gate for future learning.

## Non-goals

- No automatic capability scoring in Phase 1.
- No raw transcript/query-log/file-content capture.
- No remote registry trust for approvals by default.
- No replacement for the existing `task mark-result` CLI; the UI approval flow calls the same underlying mutation path.
- No self-declared immutable/non-learning trust; mode must come from trusted local config/registration metadata.

## Core design: task DB is source of truth

The task database is the source of truth for approval state. Inbox/messages are notification and rendering paths only.

Approval requests must live durably in the task kernel as either:

1. a minimal `task_approvals` materialized table, or
2. a deterministic event-derived view backed by append-only events.

Phase 1 should prefer a small table plus append-only events for simple querying and offline UI recovery.

Minimal approval record fields:

```json
{
  "approval_id": "apr_...",
  "idempotency_key": "optional client/rpc retry key",
  "task_id": "task_...",
  "task_chain_id": "chain_...",
  "root_task_id": "task_...",
  "status": "pending|decided|superseded",
  "result": "good|bad|need_improvements|null",
  "created_event_seq": 123,
  "decided_event_seq": 128,
  "task_version_at_submission": 7,
  "event_seq_at_submission": 122,
  "submitter_profile": "coder-agent",
  "submitter_instance_id": "coder-agent@s1",
  "result_summary": "bounded summary",
  "acceptance_summary": "bounded checklist / claims",
  "reusable_discoveries": [
    {"label": "database", "value": "analytics_prod", "reason": "bounded reason"}
  ],
  "clarification_count": 1,
  "correction_count": 0,
  "need_improvements_count": 0,
  "first_pass_success": false,
  "created_at": "...",
  "decided_at": null
}
```

## Approval-request notification message

After the task DB transaction commits, the tracker sends `agent-communicator` a structured notification message. This message is not the source of truth.

Suggested message metadata/content:

```json
{
  "content_type": "application/vnd.broccoli.task-approval+json",
  "kind": "task_completion_approval_request",
  "approval_id": "apr_...",
  "event_seq": 123,
  "task_id": "task_...",
  "task_chain_id": "chain_...",
  "root_task_id": "task_...",
  "task_version_at_submission": 7,
  "agent_profile": "coder-agent",
  "agent_instance_id": "coder-agent@s1",
  "result_summary": "bounded summary",
  "acceptance_summary": "bounded checklist / claims",
  "reusable_discoveries": [
    {"label": "database", "value": "analytics_prod", "reason": "bounded reason"}
  ],
  "clarification_count": 1,
  "correction_count": 0,
  "need_improvements_count": 0,
  "first_pass_success": false,
  "created_at": "..."
}
```

The plain Markdown fallback must be generated only from sanitized structured fields. Old clients may display the fallback as non-actionable text.

## UI styling and actions

`agent-communicator` should render approval notifications as approval cards, not normal chat bubbles:

- distinct border/background/accent, e.g. "Approval required";
- task title/status, result summary, submitting agent profile/instance, task chain;
- reusable discoveries section, e.g. DB/table names;
- clarification/correction counters;
- stale-card warning if the approval or task changed since the card was loaded;
- action buttons/commands:
  - **Approve / Good**
  - **Needs improvements**
  - **Reject / Bad**
  - optional: **Open task events** / **Copy task id** / **Refresh approval**

Actions call the trusted local tracker/task kernel, not the agent directly.

## State machine and transaction ordering

1. Agent checkpoints work using `state set` throughout execution.
2. Agent submits completion proposal:
   - CLI/RPC candidate: `task submit-completion TASK --summary ... [--discovery key=value] [--idempotency-key KEY] [--json]`.
3. In one DB transaction, tracker/task kernel:
   - validates and sanitizes bounded fields;
   - verifies the submitter is a normal reproducible-learning instance, not immutable/non-learning;
   - enforces duplicate pending approval rules;
   - updates task status to `review`;
   - creates/records approval request;
   - appends `task_completion_submitted` and `task_approval_requested` in append order;
   - stores `task_version_at_submission` and `event_seq_at_submission`.
4. After commit:
   - attempt structured notification delivery to `agent-communicator`;
   - append `task_approval_notification_sent` or `task_approval_notification_failed` separately.
5. User chooses an action in `agent-communicator`:
   - `good` => task status `validated`, append `task_result_marked` with `result_status=good` and `approval_id`.
   - `need_improvements` => task status `ready|working|blocked`, require remediation `next_step`, append result event.
   - `bad` => task status `blocked|ready`, require remediation `next_step`, append result event.
6. Tracker sends an optional decision notification back to the submitting agent profile/instance.

Message delivery failure never rolls back the approval request. Offline `agent-communicator` can recover by calling approval list/show APIs.

## Idempotency and duplicate pending approvals

`task.submit_completion` must be safe across RPC retry after commit/before response.

Phase 1 rules:

- Accept an optional `idempotency_key` generated by the caller.
- If the same caller retries with the same key and identical payload, return the existing approval.
- Enforce at most one pending approval for `task_id + task_chain_id/root_task_id`.
- If a different/conflicting pending submission exists for the same task chain, reject with a duplicate-pending conflict.
- Repeated notification delivery attempts may append sent/failed notification events, but must not create duplicate approval requests.

`task.review_completion` idempotency:

- If approval is already decided with the same result/action, return the existing decision and append no duplicate `task_result_marked` event.
- If approval is already decided with a different result/action, return a conflict unless a future explicit force/reopen workflow exists.

## Stale-card and concurrency checks

Approval cards must include `approval_id`, approval status/version, `task_version_at_submission`, and/or `event_seq_at_submission`.

When the UI calls `task.review_completion`:

- verify approval is still `pending`;
- verify task still corresponds to the submitted version/status or is otherwise safe to review;
- if task status/version changed in a way that could make the card obsolete, return a refresh-required conflict;
- UI should then reload approval/task state and display a stale-card warning.

This prevents validating an obsolete proposal after another agent/user changed the task.

## RPC/API shape

Suggested local-only JSON-RPC methods:

- `task.submit_completion(params)`
  - input: `task_id`, `agent`, `agent_instance_id`, `task_chain_id`, `root_task_id`, `result_summary`, `acceptance_summary`, `reusable_discoveries`, optional counts, `idempotency_key`.
  - output: `approval_id`, approval record, task snapshot, created event seq.
- `task.review_completion(params)`
  - input: `approval_id`, `result: good|bad|need_improvements`, optional `next_step`, optional `notes`, loaded approval/task version for stale-card checks.
  - output: updated task, approval record, decision event seq.
- `task.list_approvals(params)` / `task.show_approval(params)` for UI refresh/offline recovery.

CLI equivalents:

- `broccoli-comms task submit-completion TASK --summary S --discovery database=analytics_prod --idempotency-key KEY --json`
- `broccoli-comms task approval list [--status pending] --json`
- `broccoli-comms task approval show APPROVAL --json`
- `broccoli-comms task approval review APPROVAL --result good --json`

## Approval notification delivery

Use existing local inbox/message delivery with structured content type:

- sender: `broccoli-comms` or `task-kernel`, not the worker agent, to show it is a system approval card;
- recipient: `agent-communicator` mailbox;
- content type: `application/vnd.broccoli.task-approval+json`;
- metadata includes `approval_id` and `event_seq` for idempotent UI routing.

If `agent-communicator` is offline, the approval remains durable in the task DB and is loaded by `task.list_approvals` when the UI reconnects.

## Event log requirements

Events must be append-ordered and sufficient to reconstruct the review timeline:

- `task_completion_submitted`
- `task_approval_requested`
- `task_approval_notification_sent` or `task_approval_notification_failed`
- `task_result_marked`
- optional `task_approval_superseded`

Every event should include bounded metadata only:

- `approval_id`, `task_id`, `task_chain_id`, `root_task_id`, `agent_profile`, `agent_instance_id`;
- result/discovery summaries;
- clarification/correction counters;
- actor/provenance (`created_by`, `reviewed_by`).

Do not store raw query logs, terminal transcripts, secrets, or large file contents.

## Payload bounds and redaction

Approval payloads must use the Phase 1 bounded text sanitizer or stricter limits:

- `result_summary`: bounded short text.
- `acceptance_summary`: bounded short text/list.
- reusable discovery `label`, `value`, `reason`: bounded strings; secret-like values rejected/redacted.
- review `notes` and remediation `next_step`: bounded strings.
- fallback Markdown: generated from sanitized structured fields only and bounded before delivery.

Approval submissions containing raw transcript-like content, query logs, secrets/tokens, or oversized text should be rejected or redacted before persistence.

## Immutable / non-learning instances

Immutable/non-learning status must come from trusted local configuration or registration metadata, not self-declared message content.

Rules:

- Tracker/task kernel rejects `task.submit_completion` learning approval submissions from immutable/non-learning instances.
- Immutable/non-learning messages may be rendered as transient/non-learning with approval/validation actions disabled.
- Immutable/non-learning instances must not claim validation-required task chains or write learning events.
- If a UI receives an approval-looking message from an immutable/non-learning instance, it should display it as non-actionable unless the durable task DB has a matching trusted approval record.

## Security / trust

- Only local tracker/task kernel can create actionable approval cards by default.
- Remote approval requests are ignored or displayed as untrusted/non-actionable until a later signed/registry design exists.
- UI approval actions require the local trusted tracker socket/bridge.
- Agent-sent text alone cannot mark a task validated.

## Acceptance tests

1. Submitting a completion appends `task_completion_submitted` and `task_approval_requested` in append order and creates one pending approval record.
2. RPC retry with same `idempotency_key` returns the existing approval without duplicate events.
3. Conflicting duplicate pending submission for the same task chain is rejected.
4. `agent-communicator` receives/loads a structured approval request with distinct type/metadata.
5. Approving from UI/RPC writes one `task_result_marked(result_status=good)` and task becomes `validated`.
6. Repeating the same review action is idempotent and appends no duplicate decision event.
7. `need_improvements` / `bad` require `next_step` and do not validate learning.
8. Offline `agent-communicator` does not lose approval requests; they are queryable from durable store.
9. Stale card/version mismatch returns refresh-required conflict.
10. Immutable/non-learning instance cannot create a learning approval request.
11. Oversized/raw/secret-like payloads are rejected or sanitized and fallback Markdown is generated only from sanitized fields.

## Future questions

- Should reviewer agents be allowed to approve? Phase 1 keeps user approval as the default trusted validator; reviewer approval can be separate metadata unless explicitly configured.
- Should the browser UI use a future HTTP bridge instead of local UNIX socket? Local socket is fine for trusted local Phase 1; HTTP bridge can come later for browser portability.
- Should superseded approvals be supported in Phase 1 or should duplicate pending approvals always be rejected? Recommended Phase 1: reject duplicates; add superseding later.
