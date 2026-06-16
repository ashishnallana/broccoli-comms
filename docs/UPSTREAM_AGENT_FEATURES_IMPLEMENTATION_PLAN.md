# Upstream agent feature implementation plan

## Scope

This plan covers the `home-manager-core` agent-tracker / agent-registry / communicator features that are relevant to Broccoli Comms after the standalone runtime extraction.

Relevant upstream features:

1. `agent-tracker-ctl send-text` and `send-key` CLI commands.
2. Communicator TUI explicit direct-input actions.
3. Stable conversation identity in communicator state/outbox.
4. Remote registry-routed direct pane input, redesigned for Broccoli safety constraints.
5. Remote-message destination pane focus, only where it fits Broccoli private runtime behavior.

Out of scope / do not port directly:

- Home Manager module option plumbing as-is.
- NixOS/Home Manager registry deployment details unrelated to Broccoli packaging.
- Upstream remote direct-input defaults; Broccoli remote direct input must default disabled.
- Any behavior that falls back to the user's default tmux server from app-managed runtime.

## Implementation status

Chunks 1-6 are implemented and reviewer-approved in the working tree. Chunk 7 docs/runtime cleanup is in progress in this documentation pass. Remote pane input remains default-disabled and guarded; native frontend work remains future-only and should not be included with these chunks.

## Current Broccoli baseline

Already present:

- Local tracker JSON-RPC method `send_input`.
- Local tmux primitives for literal text and symbolic keys.
- Registered `tmux_socket` requirement for local direct input.
- Private Broccoli tmux/tracker socket handling in app runtime.
- Draft send-keys/send-text plan in `docs/SEND_KEYS_SEND_TEXT_PLAN.md`.

Missing:

- CLI affordances for `send_input`.
- TUI direct-input affordances.
- Stable ID-based conversation/outbox matching.
- Safe remote `/pane-inputs` protocol and delivery loop.
- Optional focus of destination pane on remote message delivery.

## Chunk 1: CLI direct input commands

Goal: expose existing local `send_input` backend through `agent-tracker-ctl`.

Files:

- `agent-tracker/agent-tracker-ctl.py`
- `agent-tracker/ctl_commands/send_text.py`
- `agent-tracker/ctl_commands/send_key.py`
- `agent-tracker/test_agent_tracker_ctl.py`
- README / runtime docs as needed

Tasks:

- Add `send-text TARGET TEXT`.
- Add `send-text --no-submit TARGET TEXT`.
- Add `send-key TARGET KEY [KEY...]`.
- Parse targets consistently with `send-message`:
  - bare name -> `agent_name`
  - UUID -> `agent_id`
  - `host/name`, `host/uuid`, `registry:host/name` -> `target_address`
- Keep remote target behavior delegated to backend; initially it should fail clearly while remote direct input is disabled.
- Update help text examples.

Acceptance:

- CLI calls JSON-RPC `send_input` with expected params.
- Local bare targets work.
- Remote targets produce a clear disabled/not-supported error until remote chunk lands.
- Existing `send-message` behavior is unchanged.

## Chunk 2: stable communicator conversation identity

Goal: prevent conversation split/mix after renames, aliases, or duplicate names across registries.

Files:

- `agent-communicator-tui/internal/tracker/types.go`
- `agent-communicator-tui/outbox.go`
- `agent-communicator-tui/commands.go`
- `agent-communicator-tui/app.go`
- Go tests, including a new stable-identity regression test

Tasks:

- Add message fields:
  - `sender_agent_id`
  - `sender_tracker_id`
- Add outbox fields:
  - `target_agent_id`
  - `target_tracker_id`
- Make `makeOutboxRecord` persist target IDs when available.
- Replace address/name-only conversation keys with stable keys:
  - local: `local:<agent_id>` when present
  - remote: `remote:<tracker_id>:<agent_id>` when present
  - fallback: current `rowTarget(row)`
- Match inbound messages to rows by sender agent/tracker IDs when available, falling back to legacy sender-name matching.
- Match outbox records to rows by target agent/tracker IDs when available, falling back to target address.

Acceptance:

- Renaming an agent does not lose previous sent/inbound history.
- Two remote agents with the same display name on different trackers do not share a conversation.
- Legacy outbox/messages without IDs still display using fallback behavior.

## Chunk 3: local communicator direct-input actions

Goal: expose direct pane control in the TUI as explicit action modes while keeping normal inbox messages as default.

Files:

- `agent-communicator-tui/internal/tracker/client.go`
- `agent-communicator-tui/commands.go`
- `agent-communicator-tui/app.go`
- `agent-communicator-tui/view.go`
- Go tests

Tasks:

- Add tracker client methods:
  - `SendText(ctx, target, text, submit)`
  - `SendKeys(ctx, target, keys)`
- Add composer command parsing:
  - plain text -> normal inbox `send-message`
  - `/msg TEXT` -> normal inbox `send-message`
  - `/text TEXT` -> direct text and submit
  - `/text --no-submit TEXT` -> direct text without submit
  - `/key KEY [KEY...]` -> direct symbolic keys
- Direct-input sends must not append normal outbox messages or add markdown reply suffixes.
- On direct-input failure, restore the original composer text.
- Show a short success/error status.
- Footer/help must clearly label direct input as pane control.
- Initially allow only local rows unless the remote guardrail chunk exposes an explicit capability flag.

Acceptance:

- Default Enter behavior remains normal inbox message.
- `/text` and `/key` call `send_input` through the tracker client.
- Direct-input commands do not create inbox history/outbox records.
- Remote direct-input UI is hidden/disabled until remote direct input is explicitly enabled.

## Chunk 4: optional remote message pane focus

Goal: when a remote inbox message is delivered into a local app-managed agent, optionally focus that agent pane.

Files:

- `agent-tracker/tmux_util.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/test_rpc_handler.py`
- `agent-tracker/test_tmux_util.py`
- possibly `app/broccoli-comms.py` config/docs

Tasks:

- Add best-effort `focus_pane(pane_id, session=None, socket_path=None)` using the registered/private socket only.
- On remote-origin message delivery, focus destination pane if enabled.
- Default should be conservative for Broccoli: either disabled by default or app-runtime-only with config documented.
- Never fail message delivery because focus failed.
- Never use the user's default tmux server from Broccoli runtime.

Acceptance:

- Remote message delivery remains successful if focus fails.
- Focus commands include the registered/private tmux socket.
- Local/inbox-only deliveries do not unexpectedly steal focus unless explicitly desired.

## Chunk 5: safe remote direct pane input protocol

Goal: implement registry-routed remote direct input for multi-device Broccoli deployments with stronger guardrails than upstream.

Files:

- `agent-registry/server.py`
- `agent-registry/test_http_registry.py`
- `agent-tracker/registry_client.py`
- `agent-tracker/rpc_handler.py`
- `agent-tracker/state.py` or a small persistent dedupe store
- `agent-tracker/test_registry_client_routing.py`
- `agent-tracker/test_rpc_handler.py`
- docs / doctor checks

Design requirements:

- Remote direct input defaults disabled everywhere.
- Enablement must be explicit in Broccoli config/env.
- Use a separate registry endpoint: `POST /pane-inputs`.
- Keep `/messages` semantics unchanged.
- Require source-generated `pane_input_id` / `request_id`.
- Queue as `delivery_type: pane_input`.
- Destination tracker must dedupe request IDs before injecting keystrokes.
- Ack only after successful injection or successful duplicate recognition.
- Do not write inbox entries or normal message notifications for pane input.
- Validate before queueing:
  - known input type: `text` or `keys`
  - non-empty text
  - max text length
  - non-empty keys
  - max key count
  - valid key tokens
  - target hostname required for name targets
  - reject same-tracker remote calls
  - reject stale/offline target tracker
- Audit without logging full text payloads; record source/target/mode/request id/result and text length or hash only.

Tasks:

- Add registry config gate for remote pane input.
- Add tracker config gate for sending/receiving remote pane input.
- Add registry payload validation and queueing.
- Add registry client helpers for default and explicit registry routing.
- Extend `handle_send_input` so remote `target_address` routes only when enabled.
- Extend delivery loop to dispatch `delivery_type=pane_input`.
- Add persistent or state-backed dedupe for applied request IDs.
- Add docs and `doctor` warnings when remote direct input is enabled without registry auth or equivalent trust assumptions.

Acceptance:

- Disabled remote direct input rejects clearly at sender and registry.
- Enabled remote direct text/key queues through registry and injects at the destination tracker.
- Registry retries do not duplicate keystrokes.
- Transient local tmux/target failures are not acked.
- Invalid, over-limit, same-tracker, stale-target, and target-not-found requests are rejected.
- `/messages` tests remain unchanged.

## Chunk 6: remote direct input in TUI, capability-gated

Goal: expose remote direct input in the communicator only after Chunk 5 guardrails are complete.

Files:

- `agent-communicator-tui` client/app/view files
- runtime config/status surfaces
- Go tests

Tasks:

- Add a backend capability indicator, e.g. `remote_direct_input_enabled`.
- Hide or reject `/text` and `/key` for remote rows unless capability is true.
- Make remote direct input visually explicit in status/help.
- Consider a confirmation step for remote direct pane control.

Acceptance:

- Local direct input still works.
- Remote direct input is impossible from the TUI while disabled.
- When enabled, remote direct input preserves exact `TargetAddress` and surfaces success/failure clearly.

## Chunk 7: docs, runtime API, and migration cleanup

Files:

- `docs/SEND_KEYS_SEND_TEXT_PLAN.md`
- `docs/RUNTIME_API.md`
- `docs/SETUP_AND_MULTI_DEVICE.md`
- `docs/MIGRATION_PLAN.md`
- `README.md`

Tasks:

- Update `SEND_KEYS_SEND_TEXT_PLAN.md` so it no longer says upstream remote chunks were uncommitted.
- Document CLI examples for local direct input.
- Document remote direct input as disabled by default and dangerous.
- Document config/env keys once chosen.
- Document stable conversation identity expectations.
- Update migration-plan checkboxes as chunks land.

## Suggested implementation order

1. Chunk 1: CLI direct input commands.
2. Chunk 2: stable communicator identity.
3. Chunk 3: local TUI direct input.
4. Chunk 4: optional remote message pane focus.
5. Chunk 5: safe remote registry direct input.
6. Chunk 6: remote TUI direct input.
7. Chunk 7: docs cleanup throughout, finalized at the end.

This order gets useful local Broccoli functionality quickly while avoiding premature exposure of remote pane control.

## Validation gate

Before each chunk commit:

```sh
python3 -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-tracker/ctl_commands/*.py agent-registry/*.py
(cd agent-tracker && python3 -m unittest test_tmux_util.py test_rpc_handler.py test_agent_tracker_ctl.py test_registry_client_routing.py test_http_registry.py)
(cd agent-registry && python3 -m unittest test_managed_agent.py test_http_registry.py 2>/dev/null || python3 -m unittest test_managed_agent.py)
(cd agent-communicator-tui && go test ./...)
bash -n wrapper/agent-wrapper.sh
nix --extra-experimental-features 'nix-command flakes' flake check .
git diff --check
```

Additional targeted checks:

- Text beginning with `-` is sent literally.
- Text `C-c` is typed literally; symbolic key `C-c` sends Ctrl-C.
- Missing registered `tmux_socket` never falls back to default tmux.
- Direct input does not create inbox/outbox messages.
- Remote disabled requests are rejected.
- Remote dedupe prevents duplicate injection.
- Audit logs do not contain full text payloads.
