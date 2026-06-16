# Delivery Routing Diagnostics

## Scope

This document describes the current phase-4 diagnostic surface for multi-instance `agent-communicator` routing. It is intentionally compatible with existing local-only bare-name behavior.

## Shared-service discovery

List all registry-visible shared-service communicator instances:

```sh
broccoli-comms registry agents \
  --logical-identity agent-communicator \
  --service-kind shared_service \
  --json
```

Expected fields for each communicator service:

- `hostname`
- `name` (normally `agent-communicator`)
- `agent_id`
- `status`
- `logical_identity: agent-communicator`
- `service_kind: shared_service`
- `capabilities.mailbox: true`
- `capabilities.direct_input: false`

Only active/idle/working remote shared-service rows are used for task-update fanout planning. Stale/gone rows and unrelated logical identities are excluded.

## Delivery IDs

Task-update shared-service fanout uses:

- one logical `message_id` for the overall fanout message;
- one per-recipient `delivery_id` derived from logical message, target, and delivery scope.

The local and remote inbox payloads carry both IDs. Local inbox dedupe uses `delivery_id` when present, falling back to `message_id` for legacy messages. Registry queues are keyed by `delivery_id` when present and still accept message-id acks for compatibility.

## Inspecting delivery status

Current diagnostics are event and inbox based:

1. Use registry service discovery to confirm planned remote communicator targets:
   ```sh
   broccoli-comms registry agents --logical-identity agent-communicator --service-kind shared_service --json
   ```
2. Inspect local task/update events from the task kernel:
   ```sh
   broccoli-comms events list --task TASK_ID --json
   ```
3. Inspect local or remote communicator inboxes:
   ```sh
   broccoli-comms agent-tracker read-inbox --name agent-communicator --last 20
   ```
4. For remote delivery, inspect the remote host's `agent-communicator` inbox and registry/tracker logs for the same `message_id` and its per-recipient `delivery_id`.

## User-facing send compatibility

Bare sends remain local-only:

```sh
broccoli-comms agent-tracker send-message agent-communicator "hello local UI"
```

Host-qualified sends target exactly one remote communicator:

```sh
broccoli-comms agent-tracker send-message HOST/agent-communicator "hello remote UI"
```

Task-update system notifications are the fanout path. They use registry-discovered shared-service instances and preserve typed task-update metadata.

## Limitations

- There is not yet a single persistent `delivery show DELIVERY_ID` command; diagnostics currently combine registry discovery, task events, inbox entries, and tracker/registry logs.
- Full two-host validation requires a second running Broccoli Comms host or VM with registry connectivity. When unavailable, validate with unit/integration tests plus the documented E2E matrix.
