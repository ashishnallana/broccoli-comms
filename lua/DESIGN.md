# Lua Plugin System Design

## Scope

This document defines a future Broccoli Comms Lua client and plugin system. It is design-only for Phase 0; no runtime implementation is included here.

Goals:
- Provide an embeddable Lua tracker client that accepts an explicit `agent-tracker` Unix socket path.
- Support initial tracker APIs: `list`, `send_message`, and `read_inbox`.
- Support a Neovim-like `init.lua` configuration model.
- Support multiple Lua plugins with isolated lifecycle, options, permissions, state, and errors.
- Support plugin-owned agent metadata, exposed through agent query/list APIs.
- Prefer SQLite for persistent local plugin state and metadata.
- Enable demo-only Python and Go host embedding in later phases without integrating into agent-tracker or the TUI initially.

Non-goals for the initial implementation:
- No tracker RPC schema changes.
- No TUI or secondary frontend rendering integration.
- No registry-wide metadata sync.
- No direct plugin access to raw sockets or SQLite handles by default.

## Pre-implementation analysis: agent-tracker changes

Phase 1 tracker-client core should require no `agent-tracker` changes.

Current tracker capabilities are sufficient:
- `agent-tracker/rpc_handler.py` already dispatches `list`, `send_message`, and `get_inbox` over JSON-RPC on the Unix socket.
- `list` already supports `include_remote` through existing RPC params.
- `send_message` supports local delivery and remote routing via `target_address`.
- `get_inbox` supports explicit `agent_name`, `last_n`, `mark_read`, `clear`, and sender filters.

Caveats:
- Plugin metadata is initially host/Lua-layer only and is merged into Lua-facing agent query results by the plugin host.
- No tracker RPC schema change is required for initial metadata support.
- If backend metadata support is desired later, it must be additive and capability-negotiated, preserving current `list` behavior when `include_metadata` is absent or false.

## Modular layout requirement

Avoid monolithic files. The Lua system should be organized as small focused modules so each implementation slice is independently reviewable.

Suggested future layout:

```text
lua/
  DESIGN.md
  IMPLEMENTATION_PLAN.md
  broccoli/
    init.lua                 # public broccoli API facade
    tracker.lua              # tracker client facade
    tracker_rpc.lua          # JSON-RPC request/response mapping
    transport.lua            # transport adapter interface/default wiring
    config_loader.lua        # init.lua path resolution and loading
    plugins/
      registry.lua           # plugins.use, ordering, enable/disable
      lifecycle.lua          # setup/run/teardown orchestration
      sandbox.lua            # restricted environments
      capabilities.lua       # permission checks and scoped APIs
    agents/
      init.lua               # agents.get/list and metadata API facade
      metadata.lua           # set/get/clear/list metadata
      query.lua              # tracker result + metadata merge
    storage/
      init.lua               # storage adapter interface
      sqlite.lua             # host SQLite adapter wrapper
      migrations.lua         # schema migrations
    commands.lua             # command registry
    events.lua               # event registry and dispatch
    diagnostics.lua          # structured plugin/runtime errors
  examples/
    python_embed.py          # demo-only host adapter
    go_embed/                # demo-only host adapter
```

The exact layout can evolve, but each file should have a narrow responsibility. Avoid placing the whole tracker client, plugin registry, sandbox, storage, metadata, and event system into one giant Lua file or one giant host adapter.

## Public Lua API

The user-facing module is `broccoli`:

```lua
local broccoli = require("broccoli")

broccoli.setup({
  tracker = {
    socket_path = "/path/to/agent-tracker.sock",
    timeout_ms = 5000,
    include_remote = true,
  },
})
```

Initial tracker APIs:

```lua
local agents, err = broccoli.tracker.list({ include_remote = true })

local ok, err = broccoli.tracker.send_message({
  target = "review-agent",          -- local name/id or remote host/name
  message = "hello",
  sender_name = "optional",
  sender_id = "optional",
  message_id = "optional",
  attachments = nil,
})

local inbox, err = broccoli.tracker.read_inbox({
  agent_name = "agent-communicator",
  last = 10,
  clear = false,
  mark_read = true,
  sender_name = nil,
  sender_agent_id = nil,
  sender_tracker_id = nil,
})
```

Return convention:
- Success returns `(result, nil)` or `(true, nil)`.
- Failure returns `(nil, err)` or `(false, err)`.
- Errors are structured:

```lua
{
  kind = "rpc", -- rpc | transport | timeout | decode | config | permission | plugin
  code = -32602,
  message = "Invalid params",
  data = {},
}
```

## Host API namespace

The host provides a scoped API table inspired by Neovim's `vim.*`:

```lua
broccoli = {
  setup = function(opts) end,
  tracker = {
    list = function(opts) end,
    send_message = function(opts) end,
    read_inbox = function(opts) end,
  },
  agents = {
    get = function(agent_ref, opts) end,
    list = function(opts) end,
    set_metadata = function(agent_ref, namespace, key, value, opts) end,
    get_metadata = function(agent_ref, namespace, key) end,
    clear_metadata = function(agent_ref, namespace, key) end,
    list_metadata = function(agent_ref, opts) end,
  },
  plugins = {
    use = function(name_or_path, spec) end,
    disable = function(name) end,
    reload = function(name) end,
    list = function() end,
  },
  commands = {
    create = function(name, spec) end,
    delete = function(name) end,
    list = function() end,
  },
  events = {
    on = function(event, handler, opts) end,
    off = function(handle) end,
    emit = function(event, payload) end,
  },
  log = { trace = fn, debug = fn, info = fn, warn = fn, error = fn },
  ui = { notify = fn, select = fn, input = fn }, -- future host-dependent APIs
}
```

`bc` may be offered as a short alias later, but `broccoli` is the canonical namespace.

## Tracker RPC transport

Current protocol assumptions:
- Unix stream socket.
- Single JSON-RPC 2.0 request object per connection.
- Client sends JSON bytes, shuts down writes, reads until EOF, and decodes one JSON response.

Method mapping:
- `broccoli.tracker.list({ include_remote = true })` -> RPC `list` params `{ include_remote = true }`.
- `broccoli.tracker.send_message({ target = "host/agent", message = "..." })` -> RPC `send_message` with `target_address` for host-qualified targets or `agent_name`/`agent_id` for local targets.
- `broccoli.tracker.read_inbox({ agent_name = "...", last = 10 })` -> RPC `get_inbox` with `last_n = 10`.

Timeout/cancellation:
- Default connect/write/read timeout: 5 seconds.
- Per-call override allowed.
- Host adapters should honor host cancellation where available, e.g. Go `context.Context` or Python cancellation/timeouts.

Dependency policy:
- Lua core should be adapter-first: request validation, mapping, and error handling in Lua; JSON/socket operations supplied by host adapters.
- Standalone Lua may use `luasocket` plus `cjson`/`dkjson` later, but host adapters are preferred for Python/Go embedding and Unix socket portability.

## Neovim-like `init.lua`

Config path resolution:
1. Explicit host option/env, e.g. `BROCCOLI_CONFIG=/path/init.lua`.
2. `$XDG_CONFIG_HOME/broccoli-comms/init.lua`.
3. `~/.config/broccoli-comms/init.lua`.
4. No-op if missing.

Example user config:

```lua
local broccoli = require("broccoli")

broccoli.setup({
  tracker = { socket_path = os.getenv("AGENT_TRACKER_SOCKET") },
  plugins = { defaults = { timeout_ms = 250, sandbox = true } },
})

broccoli.plugins.use("my-statusline", {
  event = "AgentListUpdated",
  opts = { show_remote = true },
  permissions = { tracker = { list = true } },
})

broccoli.plugins.use("auto-reply", {
  enabled = false,
  opts = { prefix = "ack:" },
  permissions = {
    tracker = { read_inbox = true, send_message = true },
  },
})
```

`init.lua` is trusted user config by default: it is intentionally powerful and can register plugins, commands, and events. Hosts may offer a strict mode that sandboxes even user config.

## Plugin registration and lifecycle

Users register plugins from `init.lua`:

```lua
broccoli.plugins.use("statusline", {
  enabled = true,
  after = { "agent-cache" },
  requires = { "agent-cache" },
  opts = { format = "compact" },
  permissions = { tracker = { list = true }, ui = { notify = true } },
})
```

Plugin module shape:

```lua
local M = {}

M.meta = {
  name = "statusline",
  version = "0.1.0",
  broccoli_version = ">=0.1.0",
  capabilities = { tracker = { "list" }, events = { "AgentListUpdated" } },
}

M.defaults = { show_remote = true }

function M.setup(ctx, opts) end
function M.run(ctx) end
function M.commands(ctx) return {} end
function M.events(ctx) return {} end
function M.teardown(ctx) end

return M
```

Plugin context:

```lua
ctx = {
  plugin = { name = "statusline", version = "0.1.0", generation = 1 },
  opts = {},
  state = {},
  broccoli = scoped_broccoli_api,
  cancel = host_cancel_token,
}
```

Lifecycle:
1. Discover plugin from module name, explicit file path, config-relative `plugins/`, or packaged path.
2. Resolve enabled/disabled status and deterministic load order.
3. Check `requires` and `after` constraints.
4. Build per-plugin sandbox and scoped `broccoli` API.
5. Merge `M.defaults` with user `opts`.
6. Call `setup(ctx, opts)` once.
7. Register commands/events from returned specs or imperative API calls.
8. Invoke `run`, command handlers, event handlers, and `teardown` as needed.
9. On reload/disable, unregister commands/events and call `teardown` if present.

Broken plugins must not crash the whole host. Load/setup/runtime failures are isolated, logged with plugin name and phase, and recorded in plugin diagnostics.

## Trusted config vs sandboxed plugins

Trusted `init.lua` mode:
- User-owned and intentionally powerful.
- May use broader Lua features if the host allows them.
- Uses `broccoli.*` APIs rather than raw tracker sockets by default.

Sandboxed third-party plugin mode:
- No unrestricted `_G`, `io`, `os`, `debug`, arbitrary `package`, `require`, `loadfile`, or `dofile`.
- Controlled `require` only for plugin-local and allowlisted bundled modules.
- Plugin receives scoped `ctx.broccoli` or sandbox global `broccoli`.
- No raw socket path, transport, or SQLite handle by default.
- Per-plugin permissions gate tracker, metadata, state, events, commands, and UI APIs.

## Commands and events

Command registration:

```lua
broccoli.commands.create("PingAgent", {
  desc = "Send a ping to an agent",
  nargs = 1,
  permissions = { tracker = { send_message = true } },
  run = function(ctx, args)
    return ctx.broccoli.tracker.send_message({ target = args.target, message = args.message or "ping" })
  end,
})
```

Future events:
- `AgentListUpdated`
- `MessageReceived`
- `BeforeSendMessage`
- `AfterSendMessage`
- `InboxRead`
- `AgentMetadataChanged`

Observational hooks are async-by-default with short timeouts. Mutating hooks like `BeforeSendMessage` should be feature-flagged, synchronous, ordered, and policy-controlled.

## Agent metadata

Plugins can attach custom metadata to agents: labels, tags, scores, annotations, role hints, custom status text, display badges, or cached fields.

Metadata APIs:

```lua
broccoli.agents.set_metadata(agent_ref, namespace, key, value, opts)
broccoli.agents.get_metadata(agent_ref, namespace, key)
broccoli.agents.clear_metadata(agent_ref, namespace, key)
broccoli.agents.list_metadata(agent_ref, opts)
```

`agent_ref` supports local names, agent IDs, UUIDs, remote `host/agent` target addresses, and structured refs.

Namespacing:
- Plugin metadata defaults to `plugin.<plugin_name>`.
- Trusted `init.lua` may write `user` or `global` metadata.
- Reserved namespaces such as `core`, `tracker`, `ui`, and `system` are read-only to sandboxed plugins.

Query/list access:

```lua
local agent = broccoli.agents.get("host/pi", { include_metadata = true })
local agents = broccoli.agents.list({ include_remote = true, include_metadata = true })
```

Returned agent objects include namespaced metadata when requested:

```lua
{
  name = "pi",
  target_address = "host/pi",
  scope = "remote",
  metadata = {
    ["plugin.statusline"] = { role = "reviewer", score = 0.92 },
    ["user"] = { pinned = true, label = "important" },
  },
}
```

Filtering:

```lua
broccoli.agents.list({
  include_remote = true,
  include_metadata = true,
  metadata_namespaces = { "plugin.statusline", "user" },
})

broccoli.agents.get("pi", {
  include_metadata = true,
  metadata_prefix = "plugin.",
})
```

Metadata returned from `agents.get/list` is a snapshot merged at query time. TTL-expired metadata is omitted by default unless a trusted/debug option requests it.

Initial implementation keeps metadata in the Lua/plugin host layer and merges it into Lua-facing query results. No tracker RPC schema change is required.

## SQLite persistent store

SQLite is the preferred persistent local store for plugin state, plugin diagnostics, and persistent agent metadata.

Path resolution:
1. Explicit host option/env, e.g. `BROCCOLI_PLUGIN_STATE_DB=/path/plugin-state.sqlite3`.
2. `$XDG_STATE_HOME/broccoli-comms/plugin-state.sqlite3`.
3. `~/.local/state/broccoli-comms/plugin-state.sqlite3`.

Recommended settings:
- `PRAGMA journal_mode=WAL`.
- `PRAGMA foreign_keys=ON`.
- `PRAGMA busy_timeout=2500`.

Initial tables:

```sql
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE agent_metadata (
  agent_key TEXT NOT NULL,
  namespace TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  owner_plugin TEXT,
  persist INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT,
  PRIMARY KEY(agent_key, namespace, key)
);

CREATE TABLE plugin_state (
  plugin_name TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(plugin_name, key)
);

CREATE TABLE plugin_errors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plugin_name TEXT NOT NULL,
  phase TEXT NOT NULL,
  message TEXT NOT NULL,
  details_json TEXT,
  created_at TEXT NOT NULL
);
```

Ephemeral metadata can remain in memory. Persistent metadata and plugin state use SQLite. Agent query/list APIs merge tracker results with non-expired in-memory and SQLite metadata at query time.

## Embedding model

Python host:
- Load Lua through `lupa` or another embeddable Lua runtime.
- Register Python JSON/socket/SQLite adapters.
- Load `broccoli` Lua module and user `init.lua`.

Go host:
- Load Lua through `gopher-lua` or another embedded runtime.
- Register Go JSON/socket/SQLite adapters.
- Load `broccoli` Lua module and user `init.lua`.

Minimum Lua target:
- Prefer Lua 5.4 semantics where available.
- Keep module style and syntax compatible with Lua 5.1/LuaJIT/gopher-lua where practical.

Demo-only embedding scripts should be created in later phases and must not integrate into `agent-tracker` or the TUI until separately approved.

## Testing strategy

Planned tests:
- Lua unit tests with fake transport adapters.
- Param mapping tests for `list`, `send_message`, and `read_inbox`.
- Structured error mapping tests.
- Fake Unix socket integration tests.
- Python embedding demo tests with host adapters.
- Go embedding demo tests with host adapters.
- Sandbox permission tests.
- SQLite migration and TTL cleanup tests.
- Metadata query merge tests.

Real tracker integration should be opt-in via environment, e.g. `BROCCOLI_LUA_INTEGRATION=1`.

## Rollout summary

1. Tracker client core.
2. Demo Python/Go host adapters.
3. `init.lua` loader and `broccoli.setup`.
4. Plugin registry and sandbox basics.
5. SQLite storage adapter and schema migrations.
6. Agent metadata APIs.
7. Metadata merge into `broccoli.agents.get/list`.
8. Commands/events and later host UI integration.
