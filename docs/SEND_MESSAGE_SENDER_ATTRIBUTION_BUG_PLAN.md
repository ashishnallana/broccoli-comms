# Fix `send-message` sender attribution

## Initial bug report

Reported by `claude` on `nixos`, 2026-06-01.

### Summary

When an agent runs:

```bash
broccoli-comms agent-tracker send-message <target> <message>
```

the message stored in the target inbox can show the **target** as the sender instead of the actual sending agent.

Example observed by `claude`:

```text
[12:14:33] From agent-communicator: Acknowledged. Reading your message now.
[12:14:38] From agent-communicator: Test message — can you see this?
```

Those messages were sent by `claude`, but raw inbox JSON showed:

```json
{
  "sender": "agent-communicator",
  "sender_agent_id": "32910138-28fd-5de2-a350-2b5a5babad1d",
  "sender_agent_type": "agent-communicator-ui"
}
```

`32910138-...` is `agent-communicator`, not `claude` (`270b8556-...`).

### Validated root cause

Two bugs combine:

1. `app/broccoli-comms.py::base_env()` strips agent identity before execing `agent-tracker-ctl.py`:

   ```python
   for key in ("TMUX", "TMUX_PANE", "AGENT_ID", "AGENT_NAME", "AGENT_UUID", "SUGGESTED_AGENT_NAME"):
       env.pop(key, None)
   ```

   As a result, `agent-tracker/ctl_commands/send_message.py` often cannot include `sender_id` or `sender_name` in RPC params.

2. Plain-name local targets are encoded as `agent_name=<target>`:

   ```python
   params.update(parse_target_params(args.target))
   # "agent-communicator" -> {"agent_name": "agent-communicator"}
   ```

   Then `agent-tracker/rpc_handler.py::handle_send_message()` does this:

   ```python
   sender_name = params.get("sender_name") or _identify_agent(params, caller_pid) or "cli-user"
   ```

   `_identify_agent(params, ...)` treats `params["agent_name"]` as caller identity, but in this RPC it is actually the **target**. So the target is misattributed as the sender.

### Local validation

A focused harness reproduced the backend issue:

- `handle_send_message({"agent_name": "target", "message": "hello"})` stored `sender=target`, `sender_agent_id=target-id`.
- `handle_send_message({"agent_name": "target", "message": "hello", "sender_id": "sender-id"})` stored the correct sender.

## Implementation plan

### Goal

`send-message` should never infer sender identity from target parameters. When launched from an agent context through `broccoli-comms agent-tracker`, it should preserve explicit sender identity (`AGENT_ID` / `AGENT_NAME`) so receiver inboxes show the real sender.

### Phase 1 — Backend safety fix

File: `agent-tracker/rpc_handler.py`

1. Add a helper for sender-only identification params, e.g.:

   ```python
   def _sender_identification_params(params: dict) -> dict:
       result = {}
       if params.get("sender_id"):
           result["sender_id"] = params["sender_id"]
       return result
   ```

2. Change `handle_send_message()` from:

   ```python
   sender_name = params.get("sender_name") or _identify_agent(params, caller_pid) or "cli-user"
   ```

   to:

   ```python
   sender_name = (
       params.get("sender_name")
       or _identify_agent(_sender_identification_params(params), caller_pid)
       or "cli-user"
   )
   ```

3. Confirm all target fields remain target-only:
   - `agent_name`
   - `agent_id`
   - `target_address`

   These must not be passed into sender identity inference unless explicitly represented as `sender_id` / `sender_name`.

4. Apply the same sender-only pattern to any other send-message-like code path that currently calls `_identify_agent(params, caller_pid)` while `params` can contain target identifiers.

### Phase 2 — Preserve sender identity for CLI passthrough

File: `app/broccoli-comms.py`

1. Refactor `base_env()` to optionally preserve agent identity:

   ```python
   def base_env(preserve_agent_identity: bool = False) -> dict[str, str]:
       env = os.environ.copy()
       strip = ["TMUX", "TMUX_PANE", "SUGGESTED_AGENT_NAME"]
       if not preserve_agent_identity:
           strip += ["AGENT_ID", "AGENT_NAME", "AGENT_UUID"]
       for key in strip:
           env.pop(key, None)
       ...
   ```

2. Keep existing safe default (`preserve_agent_identity=False`) for runtime/daemon/frontend launches:
   - `ensure_tracker()`
   - `tmux()` / app-managed tmux commands
   - `ui_launch_command()` where identity is assigned deliberately
   - `track()` before assigning a fresh tracked identity

3. Use identity-preserving env only for the passthrough CLI:

   ```python
   def agent_tracker(args):
       ...
       os.execvpe(sys.executable, [sys.executable, ctl, *tracker_args], base_env(preserve_agent_identity=True))
   ```

This lets `send_message.py` see `AGENT_ID` / `AGENT_NAME` when `broccoli-comms agent-tracker ...` is run from an agent shell, while keeping daemon startup protected from inherited identities.

### Phase 3 — Tests

Add or update tests in `agent-tracker/test_rpc_handler.py`:

1. Plain local target with no sender identity must not become target sender:

   ```python
   state.set_agent("target", {"agent_id": "target-id", ...})
   handle_send_message({"agent_name": "target", "message": "hello"})
   assert payload["sender"] == "cli-user"
   assert payload.get("sender_agent_id") is None
   ```

2. Explicit sender ID plus plain local target resolves correctly:

   ```python
   state.set_agent("sender", {"agent_id": "sender-id", ...})
   state.set_agent("target", {"agent_id": "target-id", ...})
   handle_send_message({"agent_name": "target", "message": "hello", "sender_id": "sender-id"})
   assert payload["sender"] == "sender"
   assert payload["sender_agent_id"] == "sender-id"
   ```

3. `--id` target must not be mistaken for sender:

   ```python
   handle_send_message({"agent_id": "target-id", "message": "hello"})
   assert payload["sender"] == "cli-user"
   ```

4. Remote target with explicit sender ID still propagates sender metadata to registry client:
   - mock `registry_client.send_remote_message`
   - target `host/agent`
   - assert sender name/id are sender, not target.

Add or update tests for `app/broccoli-comms.py` if an app test harness exists; otherwise add a small focused testable helper:

- `base_env(preserve_agent_identity=False)` strips `AGENT_ID` / `AGENT_NAME`.
- `base_env(preserve_agent_identity=True)` keeps them.
- `agent_tracker()` uses preserving mode.

### Phase 4 — Manual validation

Use two local agents or a small direct RPC harness.

1. From an agent shell with `AGENT_ID` set:

   ```bash
   broccoli-comms agent-tracker send-message agent-communicator 'sender attribution smoke'
   broccoli-comms agent-tracker read-inbox --name agent-communicator --last 3
   ```

   Expected: inbox shows the real sender agent, not `agent-communicator`.

2. From a non-agent shell:

   ```bash
   broccoli-comms agent-tracker send-message agent-communicator 'cli smoke'
   ```

   Expected: sender is `cli-user`, not `agent-communicator`.

3. Remote route:

   ```bash
   broccoli-comms agent-tracker send-message nixos/claude 'remote attribution smoke'
   ```

   Expected on receiver: sender is the local sender if run from an agent context, otherwise `cli-user`; never the target.

### Acceptance criteria

- No inbox message is attributed to the target solely because target was passed as `agent_name` or `agent_id`.
- Agent-context `broccoli-comms agent-tracker send-message ...` preserves real sender attribution through `AGENT_ID` / `AGENT_NAME`.
- Non-agent CLI sends fall back to `cli-user`.
- Existing runtime startup still strips inherited identity to avoid daemon/UI identity contamination.
- Unit tests cover local plain-name, local UUID, and remote host-qualified targets.
