# Send-keys / send-text implementation plan

## Source context

This plan mirrors the `home-manager-core` direct pane input work while preserving Broccoli Comms runtime boundaries.

Stable upstream references in `/home/tanmay/projects/nix/home-manager-core`:

- branch: `feature/agent-tracker-direct-pane-input`
- track log: `docs/agent-tracker-direct-pane-input-track-log.md`
- committed chunks:
  - `661b962 agent-tracker: add local direct pane input RPC`
  - `982a68f agent-tracker: add direct input CLI commands`
  - `98498c4 docs: add communicator direct input scope`

The Broccoli Comms port is now implemented through the planned local, registry, and TUI chunks. Upstream references remain useful background, but the Broccoli implementation intentionally differs where needed for app-private tmux sockets and default-disabled remote pane control.

Broccoli implementation status:

- Local tracker RPC/tmux primitives, CLI `send-text`/`send-key`, stable communicator identity, local TUI direct-input actions, and optional remote-message focus are implemented and reviewer-approved.
- Registry-routed remote pane input is implemented and reviewer-approved behind explicit sender/registry/receiver gates.
- TUI remote direct input is implemented and reviewer-approved behind a runtime/env capability gate.
- Native frontend experiments are future work only and are not part of this tree's direct-input implementation.

## Goals

Add explicit direct pane input actions alongside existing inbox messaging:

- `send-message`: unchanged, inbox-based, default behavior.
- `send-text TARGET TEXT`: type literal text into the target pane and press Enter by default.
- `send-text --no-submit TARGET TEXT`: type literal text without pressing Enter.
- `send-key TARGET KEY [KEY...]`: send symbolic tmux key tokens such as `Escape`, `Enter`, or `C-c`.

Direct input intentionally bypasses inbox files and inbox notifications.

## Broccoli Comms constraints

- All local tmux operations must use the target agent's registered tmux socket; in app mode this is the Broccoli private tmux socket.
- Never fall back to the user's default tmux server for registered targets. If a target has no registered `tmux_socket` or that socket is unreachable, fail clearly instead of guessing.
- Existing `send-message` behavior and registry `/messages` behavior must remain unchanged.
- The runtime/API boundary should stay UI-agnostic so terminal TUI, future native UI, and CLI automation can share the same backend capability.
- Remote direct input is powerful and is disabled by default. It is available only when explicitly enabled on sender, registry, and receiver; request deduplication, redacted audit, payload limits, and TUI capability gating are required guardrails.

## API shape

### Tracker JSON-RPC

Add method: `send_input`.

Text params:

```json
{
  "agent_name": "alice",
  "input_type": "text",
  "text": "hello",
  "submit": true
}
```

Key params:

```json
{
  "target_address": "host-a/alice",
  "input_type": "keys",
  "keys": ["Escape", "C-c", "Enter"]
}
```

Target fields mirror `send_message`:

- bare names use `agent_name`
- bare UUIDs use `agent_id`
- `host/name`, `host/uuid`, and `registry:host/name` use `target_address`

Expected result examples:

```json
{"success": true, "target": "alice", "mode": "text", "submitted": true}
{"success": true, "target": "host-a/alice", "mode": "keys", "remote": true}
```

### CLI

Add:

```sh
agent-tracker-ctl send-text TARGET TEXT
agent-tracker-ctl send-text --no-submit TARGET TEXT
agent-tracker-ctl send-key TARGET KEY [KEY...]
```

Keep bare targets local-only. Remote targets require host-qualified syntax, matching `send-message`.

Examples:

```sh
# Local direct text, submitted with Enter
agent-tracker-ctl send-text alice "hello"

# Local direct text without Enter
agent-tracker-ctl send-text --no-submit alice "draft prompt"

# Local symbolic keys
agent-tracker-ctl send-key alice C-c Enter

# Remote direct text, only if sender + registry + receiver gates are enabled
agent-tracker-ctl send-text host-a/alice "hello from the other machine"
agent-tracker-ctl send-key registry-a:host-a/alice C-c Enter
```

### Runtime/front-end contract

Broccoli Comms exposes the capability through tracker CLI/RPC and the communicator TUI. UI layers treat direct input as an explicit action mode (`/text`, `/key`), not as a replacement for `send-message` or plain Enter. The TUI hides/rejects remote direct input unless its runtime capability gate is enabled.

## Registry protocol

Add a separate endpoint from `/messages`:

```http
POST /pane-inputs
```

Payload:

```json
{
  "sender_agent_name": "operator",
  "sender_agent_id": "...",
  "sender_tracker_id": "...",
  "target_hostname": "host-a",
  "target_agent_name": "alice",
  "pane_input_id": "source-generated-id",
  "request_id": "source-generated-id",
  "input_type": "text",
  "text": "hello",
  "submit": true
}
```

For keys:

```json
{
  "sender_agent_name": "operator",
  "sender_agent_id": "...",
  "sender_tracker_id": "...",
  "target_agent_id": "...",
  "pane_input_id": "source-generated-id",
  "request_id": "source-generated-id",
  "input_type": "keys",
  "keys": ["C-c"]
}
```

Registry behavior:

- Remote direct input is disabled by default; reject `/pane-inputs` unless explicitly enabled in registry/tracker config.
- Validate payload before queueing.
- Enforce payload limits before queueing: non-empty text, maximum text length, non-empty key list, maximum key count.
- Require a source-generated `pane_input_id` / `request_id`; preserve it in the queued delivery.
- Resolve targets like `/messages`.
- Reject same-tracker remote calls; local callers should use local RPC.
- Reject stale/offline target trackers.
- Queue delivery as `delivery_type: "pane_input"`.
- Ack only after destination tracker successfully injects local pane input or recognizes the request id as already successfully applied.
- Destination trackers must dedupe `pane_input_id` / `request_id` so registry retries do not duplicate keystrokes.
- Sender identity should be derived from or checked against the authenticated tracker where possible. If bearer auth cannot distinguish trackers, document that limitation and keep remote direct input disabled by default.
- Do not modify `/messages` semantics.

## Safety rules

Tmux input helpers must be strict:

- literal text uses `tmux send-keys -l -- TEXT`
- text beginning with `-` must be treated as text, not a tmux option
- text `C-c` must type the characters `C-c`, not Ctrl-C
- symbolic keys use `tmux send-keys` only after token normalization/validation
- key validation should be whitelist-based: normalize aliases, then allow only known tmux key names and approved modifier forms
- accept aliases such as `ESC`, `Escape`, `ENTER`, `Return`, `C-C`, `Ctrl-C`
- reject whitespace, shell-looking strings, arbitrary unknown key names, and trailing modifiers such as `C-`
- prefer existing tmux reliability helpers for pane existence/copy-mode handling where available

Payload and audit policy:

- reject empty text and empty key lists
- define conservative limits before remote enablement, e.g. maximum text bytes/chars and maximum key count per request
- generate and propagate a `pane_input_id` / `request_id` for every remote request
- audit source tracker/agent, target, mode, request id, timestamp, result, and error class
- avoid logging full text payloads; store only redacted/truncated previews or length/hash metadata

Remote guardrails for the safety chunk:

- remote direct input must default to disabled globally
- require explicit enablement before `/pane-inputs` accepts requests or remote routing sends them
- consider per-agent opt-out metadata, e.g. `no_remote_pane_input`
- expose remote direct-input TUI affordances only when the runtime/env capability gate indicates the backend guardrails are enabled

## Implementation chunks

### Chunk A: local tmux primitives and tracker RPC — implemented

Files likely touched:

- `agent-tracker/tmux_util.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/test_tmux_util.py`
- `agent-tracker/test_rpc_handler.py`

Tasks:

- Add `send_literal_text(pane_id, text, submit=True, socket_path=None)`.
- Add key token normalization and `send_symbolic_keys(pane_id, keys, socket_path=None)`.
- Add `handle_send_input()` and JSON-RPC dispatcher wiring.
- Reuse target resolution from `send_message` where practical.
- Ensure local `target_address` for `local/<agent>` and local hostname resolves locally.
- Keep this chunk strictly local: remote `target_address` should return a clear not-yet-supported/disabled error until remote guardrails land.

Acceptance:

- Local direct input resolves by name and UUID.
- Registered `tmux_socket` is required and used for tmux calls.
- Missing or unreachable registered `tmux_socket` fails clearly; no default tmux fallback is attempted.
- Direct input bypasses inbox files and message notifications.
- Invalid payloads return JSON-RPC parameter errors.

### Chunk B: CLI commands — implemented

Files likely touched:

- `agent-tracker/agent-tracker-ctl.py`
- `agent-tracker/ctl_commands/send_text.py`
- `agent-tracker/ctl_commands/send_key.py`
- `agent-tracker/test_agent_tracker_ctl.py`
- README/docs help examples

Tasks:

- Add `send-text` and `send-key` subcommands.
- Preserve send-message as the default communication path.
- Parse bare names/UUIDs as local targets and host-qualified addresses as `target_address`.

Acceptance:

- `send-text alice "hello"` calls `send_input` with `input_type=text`, `submit=true`.
- `send-text --no-submit alice "draft"` sends `submit=false`.
- `send-key alice ESC C-c Enter` calls `send_input` with normalized/requested keys.

### Chunk C: registry protocol and remote routing — implemented

Files likely touched:

- `agent-registry/server.py`
- `agent-registry/test_http_registry.py`
- `agent-tracker/registry_client.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/test_registry_client_routing.py`
- `agent-tracker/test_rpc_handler.py`

Tasks:

- Add `POST /pane-inputs`.
- Add remote direct-input config gates first, defaulting disabled.
- Add registry client helpers for default and explicit registry routing.
- Route remote `send_input` target addresses through registry only when explicitly enabled.
- Generate `pane_input_id` / `request_id` at the source and include it in the registry payload.
- Add payload limits and redacted audit metadata.
- Keep queued remote pane input distinct from inbox messages.

Acceptance:

- With remote direct input disabled, remote `send-text host/agent "hello"` is rejected clearly.
- With explicit enablement, remote `send-text host/agent "hello"` queues `delivery_type=pane_input` with request id.
- Target-not-found, missing hostname, same-tracker, stale tracker, invalid payloads, over-limit payloads, and untrusted/unchecked sender identity cases are rejected or documented according to the auth model.
- `/messages` tests continue passing unchanged.

### Chunk D: remote delivery loop dispatch — implemented

Files likely touched:

- `agent-tracker/registry_client.py` and/or delivery loop code
- `agent-tracker/rpc_handler.py`
- delivery-loop tests

Tasks:

- When polling registry deliveries, dispatch `delivery_type=pane_input` to local `handle_send_input()`.
- Dedupe by `pane_input_id` / `request_id`; if the same id was already successfully applied, ack without injecting again.
- Ack only after successful first local injection or successful dedupe recognition.
- Do not write inbox entries for pane input deliveries.
- Define policy for invalid queued deliveries: drop+ack with warning vs leave unacked for retry.

Acceptance:

- Remote pane input bypasses inbox and injects into local pane only when remote direct input is enabled.
- Transient tmux/local target failures are not acked.
- Retries with the same request id do not duplicate keystrokes.
- Successful injection acks exactly once.

### Chunk E: Broccoli Comms runtime/docs/safety polish — implemented

Files likely touched:

- `docs/SETUP_AND_MULTI_DEVICE.md`
- `docs/RUNTIME_API.md`
- `docs/MIGRATION_PLAN.md`
- `README.md`
- optional config/runtime docs

Tasks:

- Document local and remote CLI examples.
- Document private-tmux-socket guarantees for app mode.
- Add remote direct-input guardrails and config docs.
- Add `doctor` checks or warnings if remote direct input is enabled without registry auth or without tracker-distinguishable auth.

Implemented Broccoli Chunk 5 env gates:

- Sender tracker: `AGENT_TRACKER_REMOTE_PANE_INPUT_SEND_ENABLED=1`, `BROCCOLI_COMMS_REMOTE_PANE_INPUT_SEND_ENABLED=1`, or umbrella `BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED=1`.
- Receiver tracker: `AGENT_TRACKER_REMOTE_PANE_INPUT_RECEIVE_ENABLED=1`, `BROCCOLI_COMMS_REMOTE_PANE_INPUT_RECEIVE_ENABLED=1`, or umbrella `BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED=1`.
- Registry: `AGENT_REGISTRY_REMOTE_PANE_INPUT_ENABLED=1` or `BROCCOLI_COMMS_REMOTE_PANE_INPUT_REGISTRY_ENABLED=1`.
- Limits: `AGENT_REMOTE_PANE_INPUT_MAX_TEXT_BYTES` (default 4096) and `AGENT_REMOTE_PANE_INPUT_MAX_KEYS` (default 16).

The registry endpoint is `POST /pane-inputs`; it queues `delivery_type=pane_input` with string `pane_input_id`/`request_id` values. Destination trackers dedupe request IDs before injecting and ack only after successful injection or duplicate recognition. Pane input does not create inbox entries or normal message notifications, and audit logs include only metadata plus text length/hash.

`broccoli-comms doctor` warns when remote direct input is enabled without registry auth/token assumptions in the environment.

Acceptance:

- Docs clearly distinguish inbox messaging from direct pane control.
- Remote direct input defaults and guardrails are explicit.
- `nix flake check` covers local primitives, CLI parsing, and registry validation tests.

### Chunk F: communicator TUI explicit action modes — implemented

Files likely touched:

- `agent-communicator-tui/internal/tracker/client.go`
- `agent-communicator-tui/commands.go`
- `agent-communicator-tui/app.go`
- `agent-communicator-tui/view.go`
- Go tests

Tasks:

- Add tracker client methods for direct text and keys.
- Add explicit UI mode/action selection:
  - inbox message
  - direct text
  - direct key sequence
- Keep inbox send as default.
- Preserve target addresses for local and remote rows.
- Make dangerous remote direct-input action visually explicit.
- Expose remote direct input in the TUI only when remote direct input is explicitly enabled and backend guardrails are present.

Acceptance:

- Existing send-message UX remains unchanged by default.
- Direct text and key modes call backend `send_input`/CLI equivalent.
- Remote direct-input UI is hidden or disabled by default.
- TUI tests cover mode selection, dispatch payloads, and regression for normal send.

## Validation gate

Before each commit:

```sh
python3 -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-tracker/ctl_commands/*.py agent-registry/*.py
(cd agent-tracker && python3 -m unittest test_tmux_util.py test_rpc_handler.py test_agent_tracker_ctl.py test_registry_client_routing.py test_http_registry.py)
(cd agent-registry && python3 -m unittest test_managed_agent.py)
(cd agent-communicator-tui && go test ./...)
bash -n wrapper/agent-wrapper.sh
nix --extra-experimental-features 'nix-command flakes' flake check .
git diff --check
```

Additional required tests:

- text starting with `-` is sent literally
- text `C-c` is typed literally, while symbolic key `C-c` sends Ctrl-C
- missing registered `tmux_socket` fails without default tmux fallback
- local and remote direct input do not write inbox files or notifications
- remote disabled requests are rejected
- remote request id dedup prevents duplicate injection on retry
- payload limits reject oversized text/key lists
- audit records omit full text payloads

For remote chunks, add an end-to-end registry test using `~/projects/nix/test-vm` or an isolated local registry/tracker pair.

## Remaining follow-up decisions

1. Whether to add a top-level `broccoli-comms` convenience wrapper for direct input, or keep direct input behind `agent-tracker-ctl` and the TUI.
2. Whether to add per-agent remote direct-input allow/deny settings in addition to the current global/env gates.
3. Whether direct input actions should be recorded in a user-visible audit log in Broccoli Comms state.
4. How registry auth should evolve so sender tracker identity can be derived cryptographically instead of trusted from payload fields.
