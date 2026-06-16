# Lua Plugin System Implementation Plan

## Review protocol

All phases are intentionally small. Do not commit or push a phase until it has been reviewed and approved.

Preferred approval path:
- This assistant reviews the phase.
- An independent Jetski/remote reviewer also reviews the phase.

Fallback:
- If the Jetski/remote reviewer is unavailable or unregistered at review time, this assistant's review is sufficient to unblock the phase.

## Global guardrails

- Keep early phases isolated under `lua/**` and demo-only paths unless a later phase explicitly expands scope.
- Do not modify `agent-tracker` for Phase 1 tracker-client core; current RPCs are sufficient.
- Do not modify the TUI or add a secondary app until an explicit UI integration phase is approved.
- Do not change tracker RPC schemas for metadata in initial phases.
- Prefer host adapters for socket, JSON, and SQLite operations.
- Keep demo Python/Go scripts demo-only and non-integrated.
- Avoid monolithic files. Split implementation into small focused modules for tracker JSON-RPC, transport, public API facade, config loader, plugin registry/lifecycle, sandbox/capability policy, events/commands, storage/migrations, metadata, query merge, diagnostics, and demo host scripts.

## Modular implementation layout

Suggested future layout:

```text
lua/
  broccoli/
    init.lua                 # public broccoli API facade
    tracker.lua              # tracker client facade
    tracker_rpc.lua          # JSON-RPC request/response mapping
    transport.lua            # transport adapter interface/default wiring
    config_loader.lua        # init.lua path resolution and loading
    plugins/
      registry.lua           # plugins.use, deterministic ordering
      lifecycle.lua          # setup/run/teardown orchestration
      sandbox.lua            # restricted environments
      capabilities.lua       # permission checks and scoped APIs
    agents/
      init.lua               # agents.get/list and metadata facade
      metadata.lua           # metadata set/get/clear/list
      query.lua              # tracker result + metadata merge
    storage/
      init.lua               # storage adapter interface
      sqlite.lua             # host SQLite adapter wrapper
      migrations.lua         # schema migrations
    commands.lua             # command registry
    events.lua               # event registry and dispatch
    diagnostics.lua          # structured plugin/runtime errors
  examples/
    python_embed.py          # demo-only Python host adapter
    go_embed/                # demo-only Go host adapter
```

Each phase should introduce only the modules needed for that phase. Do not dump the whole library into a single Lua file or a giant Python/Go host adapter.

## Phase 0: design and plan docs only

Status: current phase.

Scope:
- Create `lua/DESIGN.md`.
- Create `lua/IMPLEMENTATION_PLAN.md`.
- No runtime code.
- No tests required beyond whitespace validation.
- No changes to `agent-tracker`, TUI, or app runtime.

Validation:
- `git diff --check` for tracked changes.
- Because Phase 0 creates untracked Markdown files, also run explicit whitespace validation on `lua/DESIGN.md` and `lua/IMPLEMENTATION_PLAN.md` or use `git add -N lua/DESIGN.md lua/IMPLEMENTATION_PLAN.md` before `git diff --check`.
- Report `git status --short` and changed files.

Review output:
- Summary of files created.
- Confirmation that Phase 0 is docs-only.

## Phase 1: Lua tracker client core

Scope:
- Create the focused Phase 1 modules from the start:
  - `lua/broccoli/init.lua`: public facade/constructor wiring only.
  - `lua/broccoli/tracker.lua`: user-facing tracker client facade.
  - `lua/broccoli/tracker_rpc.lua`: method/param/error mapping for JSON-RPC.
  - `lua/broccoli/transport.lua`: transport adapter interface and default wiring.
- Implement adapter-driven JSON-RPC client logic for:
  - `list(opts)`.
  - `send_message(opts)`.
  - `read_inbox(opts)`.
- Accept explicit `agent-tracker` socket path through constructor/setup options.
- Use fake transport and JSON adapters in unit tests.
- Keep `tracker_rpc.lua` independent from socket/transport concerns so mapping can be tested without I/O.
- Do not add plugin registry, `init.lua` loader, SQLite, or metadata yet.

API sketch:

```lua
local tracker = require("broccoli.tracker")
local client = tracker.new({
  socket_path = "/path/to/agent-tracker.sock",
  timeout_ms = 5000,
  transport = transport_adapter,
  json = json_adapter,
})

client:list({ include_remote = true })
client:send_message({ target = "agent", message = "hello" })
client:read_inbox({ agent_name = "agent-communicator", last = 10 })
```

Implementation details:
- Map `target = "host/agent"` to RPC `target_address`.
- Map bare local target to `agent_name` unless an explicit `agent_id` is provided.
- Map `last` to `last_n` for `get_inbox`.
- Preserve RPC errors as structured error tables.
- Add transport/decode/config timeout error kinds.

Tests:
- `tracker_rpc.lua` mapping tests independent from transport:
  - `list` maps to RPC `list` with `include_remote`.
  - `send_message` maps local target to `agent_name`.
  - `send_message` maps explicit `agent_id` without rewriting it.
  - `send_message` maps remote target to `target_address`.
  - `read_inbox` maps to `get_inbox` with explicit `agent_name`, `last_n`, `mark_read`, `clear`, filters.
  - RPC error objects map to structured Lua errors.
- `transport.lua` adapter tests cover injected fake request functions and timeout/decode/config errors.
- `tracker.lua` facade tests verify it composes `tracker_rpc.lua` and `transport.lua` without duplicating mapping logic.

Validation:
- Lua unit tests for the new module.
- `git diff --check`.

Expected tracker changes: none.

## Phase 2: demo Python and Go embedding scripts

Scope:
- Add demo-only Python script using a host transport adapter.
- Add demo-only Go script using a host transport adapter.
- Suggested paths:
  - `lua/examples/python_embed.py`.
  - `lua/examples/go_embed/`.
- Demonstrate `list`, `send_message`, and `read_inbox` through explicit socket path.
- Do not integrate demos into `agent-tracker`, TUI, or app startup.

Tests:
- Fake socket/fake transport demo tests if practical.
- Demo scripts should support `--socket` argument.
- Real tracker integration remains opt-in via environment.

Validation:
- Existing repo tests unaffected.
- Demo-specific smoke checks where practical.
- `git diff --check`.

## Phase 3: `init.lua` loader and `broccoli.setup`

Scope:
- Add `broccoli` top-level module skeleton.
- Add host loader abstraction for user config:
  - explicit path/env option.
  - `$XDG_CONFIG_HOME/broccoli-comms/init.lua`.
  - fallback `~/.config/broccoli-comms/init.lua`.
- Implement `broccoli.setup(opts)` for tracker config only.
- Load trusted `init.lua` in a controlled host context.
- Do not implement plugin execution beyond recording declared specs if needed.

Tests:
- Config path resolution.
- Missing config is no-op.
- `broccoli.setup({ tracker = { socket_path = ... } })` configures tracker client.
- Reload creates a new config generation.

Validation:
- Lua tests.
- `git diff --check`.

## Phase 4: plugin registry and sandbox basics

Scope:
- Implement `broccoli.plugins.use(name_or_path, spec)`.
- Support multiple plugin specs with deterministic order.
- Support `enabled=false`.
- Support `requires` and `after` validation.
- Load plugin modules by controlled module name or explicit path.
- Create per-plugin context:
  - `ctx.plugin`.
  - `ctx.opts`.
  - `ctx.state` ephemeral table.
  - scoped `ctx.broccoli`.
- Call `setup(ctx, opts)` if present.
- Support optional `teardown(ctx)` on reload/disable.
- Isolate plugin errors with protected calls.

Sandbox basics:
- No unrestricted raw socket or transport access.
- Scoped permissions for tracker methods.
- Restricted globals for third-party plugin mode.
- Trusted `init.lua` remains intentionally broader.

Tests:
- Multiple plugins load in declaration order.
- `enabled=false` plugin is skipped.
- Broken plugin does not crash host.
- Missing dependency fails only dependent plugin.
- Permission-denied tracker call returns structured error.

Validation:
- Lua tests.
- `git diff --check`.

## Phase 5: SQLite storage adapter abstraction and schema

Scope:
- Add host storage adapter interface for SQLite.
- Add schema migration definitions for:
  - `schema_migrations(version, applied_at)`.
  - `agent_metadata(agent_key, namespace, key, value_json, owner_plugin, persist, created_at, updated_at, expires_at, PRIMARY KEY(agent_key, namespace, key))`.
  - `plugin_state(plugin_name, key, value_json, updated_at, PRIMARY KEY(plugin_name, key))`.
  - `plugin_errors(id, plugin_name, phase, message, details_json, created_at)`.
- Configure default DB path:
  - `$XDG_STATE_HOME/broccoli-comms/plugin-state.sqlite3`.
  - fallback `~/.local/state/broccoli-comms/plugin-state.sqlite3`.
- Recommend WAL, foreign keys, and busy timeout.
- Keep ephemeral metadata/state in memory.

Tests:
- Migration idempotence.
- DB path resolution.
- Plugin state get/set through scoped API.
- Plugin errors are recorded.
- TTL cleanup query behavior for metadata rows.

Validation:
- Lua/host adapter tests.
- `git diff --check`.

## Phase 6: agent metadata APIs

Scope:
- Implement metadata APIs:
  - `broccoli.agents.set_metadata(agent_ref, namespace, key, value, opts)`.
  - `broccoli.agents.get_metadata(agent_ref, namespace, key?)`.
  - `broccoli.agents.clear_metadata(agent_ref, namespace, key?)`.
  - `broccoli.agents.list_metadata(agent_ref, opts)`.
- Support agent refs:
  - local names.
  - agent IDs/UUIDs.
  - remote `host/agent` target addresses.
  - structured refs.
- Default sandbox plugin namespace to `plugin.<plugin_name>`.
- Support trusted `user`/`global` metadata from `init.lua`.
- Enforce permissions and value validation.
- Support `ttl_ms`, `persist`, `visibility`, and `merge` options.

Tests:
- Plugin writes own namespace.
- Plugin cannot write reserved namespace.
- Trusted config can write `user` metadata.
- TTL-expired values are omitted by default.
- Values must be JSON-serializable and size-limited.
- Multiple plugins can write separate namespaces to the same agent.

Validation:
- Lua/adapter tests.
- `git diff --check`.

## Phase 7: metadata merge into agent get/list

Scope:
- Implement `broccoli.agents.get(agent_ref, opts)`.
- Implement `broccoli.agents.list(opts)`.
- Add `include_metadata` support.
- Add metadata filters:
  - `metadata_namespaces`.
  - `metadata_prefix`.
  - `metadata_visibility`.
  - trusted/debug `include_expired_metadata`.
- Merge current tracker `list` results with in-memory and SQLite metadata at query time.
- Keep `broccoli.tracker.list` as a thin tracker call, or allow `include_metadata=true` to delegate to `broccoli.agents.list` in the Lua host layer.
- Do not change tracker RPC schemas.

Tests:
- Agent list without metadata matches tracker result.
- Agent list with metadata adds namespaced `metadata` maps.
- Namespace filters work.
- Plugin read permissions are enforced in merged results.
- TTL-expired metadata is omitted.
- Returned results are snapshots, not live mutable views.

Validation:
- Lua/adapter tests.
- `git diff --check`.

## Phase 8: commands and events

Scope:
- Implement host-neutral command registry:
  - `broccoli.commands.create`.
  - `broccoli.commands.delete`.
  - `broccoli.commands.list`.
- Implement event registry:
  - `broccoli.events.on`.
  - `broccoli.events.off`.
  - restricted `broccoli.events.emit`.
- Initial observational events only:
  - `AgentListUpdated`.
  - `MessageReceived` if host can safely produce it.
  - `InboxRead`.
  - `AgentMetadataChanged`.
- Mutating hooks like `BeforeSendMessage` remain feature-flagged future work.

Tests:
- Command registration/list/delete.
- Command permissions.
- Event subscription/unsubscribe.
- Handler timeout/error isolation.
- Plugin unload unregisters commands/events.

Validation:
- Lua/adapter tests.
- `git diff --check`.

## Phase 9 and later: optional host/UI integration

Potential future work, each requiring separate approval:
- TUI command palette integration.
- TUI/future UI display of selected public metadata badges/status text.
- Metadata-driven sort/filter/grouping.
- Real Python/Go host production integration.
- Registry-backed metadata sync.
- Additive tracker RPC metadata endpoints.

Guardrails:
- UI integration must be behind feature flags initially.
- Backend metadata support must be additive and capability-negotiated.
- Remote metadata sync requires a separate security/privacy design.

## Validation checklist per coding phase

At minimum:
- Relevant Lua/host tests.
- `git diff --check` for tracked changes.
- For new untracked Markdown or source files, either run explicit whitespace validation or use `git add -N <paths>` before `git diff --check`, because plain `git diff --check` does not inspect untracked files.
- `git status --short`.
- Changed file list.
- Review summary sent before commit/push.

If a phase touches existing Go/Python packages, also run the relevant existing test suite for that package.
