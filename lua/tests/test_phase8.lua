package.path = "lua/?.lua;lua/?/init.lua;" .. package.path

local broccoli = require("broccoli")

local tests = {}

local function add(name, fn)
  tests[#tests + 1] = { name = name, fn = fn }
end

local function dump(value)
  if type(value) ~= "table" then
    return tostring(value)
  end
  local parts = {}
  for key, item in pairs(value) do
    parts[#parts + 1] = tostring(key) .. "=" .. dump(item)
  end
  return "{" .. table.concat(parts, ",") .. "}"
end

local function deep_equal(a, b)
  if type(a) ~= type(b) then
    return false
  end
  if type(a) ~= "table" then
    return a == b
  end
  for key, value in pairs(a) do
    if not deep_equal(value, b[key]) then
      return false
    end
  end
  for key, _ in pairs(b) do
    if a[key] == nil then
      return false
    end
  end
  return true
end

local function assert_equal(actual, expected, label)
  if not deep_equal(actual, expected) then
    error((label or "values differ") .. ": got " .. dump(actual) .. ", want " .. dump(expected), 2)
  end
end

local function reset()
  broccoli._commands = require("broccoli.commands").new()
  broccoli.commands.create = function(...) return broccoli._commands:create(...) end
  broccoli.commands.delete = function(...) return broccoli._commands:delete(...) end
  broccoli.commands.list = function(...) return broccoli._commands:list(...) end
  broccoli.commands.clear_owner = function(...) return broccoli._commands:clear_owner(...) end
  broccoli._events = require("broccoli.events").new({ now_ms = function() return 0 end })
  broccoli.events.on = function(...) return broccoli._events:on(...) end
  broccoli.events.off = function(...) return broccoli._events:off(...) end
  broccoli.events.emit = function(...) return broccoli._events:emit(...) end
  broccoli.events.list = function(...) return broccoli._events:list(...) end
  broccoli.events.clear_owner = function(...) return broccoli._events:clear_owner(...) end
  broccoli.reset_plugins()
end

add("commands create list and delete", function()
  reset()
  local command, err = broccoli.commands.create("hello", { description = "Say hello" })
  assert_equal(err, nil)
  assert_equal(command.name, "hello")

  local rows = broccoli.commands.list()
  assert_equal(#rows, 1)
  assert_equal(rows[1].description, "Say hello")

  broccoli.commands.delete("hello")
  rows = broccoli.commands.list()
  assert_equal(#rows, 0)
end)

add("command permissions are enforced for plugins", function()
  reset()
  package.preload["phase8.commands"] = function()
    return { setup = function(ctx)
      local denied_command, denied_err = ctx.broccoli.commands.create("denied", {})
      ctx.state.denied_command = denied_command
      ctx.state.denied_err = denied_err
    end }
  end
  package.preload["phase8.commands_ok"] = function()
    return { setup = function(ctx)
      local command, err = ctx.broccoli.commands.create("owned", { description = "owned" })
      ctx.state.command = command
      ctx.state.err = err
      ctx.state.rows = ctx.broccoli.commands.list()
    end }
  end

  broccoli.plugins:use("phase8.commands", { name = "commands" })
  broccoli.plugins:use("phase8.commands_ok", { name = "commands_ok", permissions = { commands = { read = true, write = true } } })
  broccoli.plugins:load_all()

  assert_equal(broccoli.plugins.instances.commands.state.denied_command, nil)
  assert_equal(broccoli.plugins.instances.commands.state.denied_err.kind, "permission")
  assert_equal(broccoli.plugins.instances.commands_ok.state.err, nil)
  assert_equal(broccoli.plugins.instances.commands_ok.state.command.owner_plugin, "commands_ok")
  assert_equal(#broccoli.plugins.instances.commands_ok.state.rows, 1)
end)

add("events subscribe emit off and isolate handler errors", function()
  reset()
  local seen = {}
  local first = broccoli.events.on("AgentListUpdated", function(payload)
    seen[#seen + 1] = payload.count
    return "ok"
  end)
  broccoli.events.on("AgentListUpdated", function()
    error("boom")
  end)

  local results = broccoli.events.emit("AgentListUpdated", { count = 2 })
  assert_equal(#results, 2)
  assert_equal(results[1].result, "ok")
  assert_equal(results[2].error.kind, "event")
  assert_equal(seen[1], 2)

  broccoli.events.off(first)
  results = broccoli.events.emit("AgentListUpdated", { count = 3 })
  assert_equal(#results, 1)
  assert_equal(seen[2], nil)
end)

add("event timeout is reported after slow handler returns", function()
  reset()
  local clock = 0
  broccoli._events.now_ms = function()
    clock = clock + 10
    return clock
  end
  broccoli.events.on("InboxRead", function()
    return true
  end)
  local results = broccoli.events.emit("InboxRead", {}, { timeout_ms = 5 })
  assert_equal(results[1].error.kind, "timeout")
end)

add("plugin events require permissions", function()
  reset()
  package.preload["phase8.events_denied"] = function()
    return { setup = function(ctx)
      local handle, err = ctx.broccoli.events.on("MessageReceived", function() end)
      ctx.state.handle = handle
      ctx.state.err = err
    end }
  end
  package.preload["phase8.events_ok"] = function()
    return { setup = function(ctx)
      local handle, err = ctx.broccoli.events.on("MessageReceived", function(payload) return payload.text end)
      ctx.state.handle = handle
      ctx.state.err = err
    end }
  end

  broccoli.plugins:use("phase8.events_denied", { name = "events_denied" })
  broccoli.plugins:use("phase8.events_ok", { name = "events_ok", permissions = { events = { read = true, subscribe = true } } })
  broccoli.plugins:load_all()

  assert_equal(broccoli.plugins.instances.events_denied.state.handle, nil)
  assert_equal(broccoli.plugins.instances.events_denied.state.err.kind, "permission")
  assert_equal(broccoli.plugins.instances.events_ok.state.err, nil)
  assert_equal(broccoli.plugins.instances.events_ok.state.handle.owner_plugin, "events_ok")
end)

add("event read permission can list but cannot subscribe", function()
  reset()
  package.preload["phase8.events_read_only"] = function()
    return { setup = function(ctx)
      local rows, list_err = ctx.broccoli.events.list()
      local handle, on_err = ctx.broccoli.events.on("MessageReceived", function() end)
      ctx.state.rows = rows
      ctx.state.list_err = list_err
      ctx.state.handle = handle
      ctx.state.on_err = on_err
    end }
  end

  broccoli.plugins:use("phase8.events_read_only", { name = "events_read_only", permissions = { events = { read = true } } })
  broccoli.plugins:load_all()

  local state = broccoli.plugins.instances.events_read_only.state
  assert_equal(type(state.rows), "table")
  assert_equal(state.list_err, nil)
  assert_equal(state.handle, nil)
  assert_equal(state.on_err.kind, "permission")
end)

add("plugin unload unregisters commands and events", function()
  reset()
  package.preload["phase8.cleanup"] = function()
    return { setup = function(ctx)
      ctx.broccoli.commands.create("cleanup.cmd", {})
      ctx.broccoli.events.on("AgentMetadataChanged", function() end)
    end }
  end

  broccoli.plugins:use("phase8.cleanup", { name = "cleanup", permissions = { commands = { read = true, write = true }, events = { read = true, subscribe = true } } })
  broccoli.plugins:load_all()
  assert_equal(#broccoli.commands.list(), 1)
  assert_equal(#broccoli.events.list(), 1)

  broccoli.plugins:disable("cleanup")
  assert_equal(#broccoli.commands.list(), 0)
  assert_equal(#broccoli.events.list(), 0)
end)

add("plugin emit requires explicit permission", function()
  reset()
  local seen = false
  broccoli.events.on("AgentMetadataChanged", function()
    seen = true
  end)
  package.preload["phase8.emit"] = function()
    return { setup = function(ctx)
      local denied, denied_err = ctx.broccoli.events.emit("AgentMetadataChanged", {})
      ctx.state.denied = denied
      ctx.state.denied_err = denied_err
    end }
  end
  package.preload["phase8.emit_ok"] = function()
    return { setup = function(ctx)
      ctx.state.results = ctx.broccoli.events.emit("AgentMetadataChanged", {})
    end }
  end

  broccoli.plugins:use("phase8.emit", { name = "emit", permissions = { events = { read = true } } })
  broccoli.plugins:use("phase8.emit_ok", { name = "emit_ok", permissions = { events = { emit = true } } })
  broccoli.plugins:load_all()

  assert_equal(broccoli.plugins.instances.emit.state.denied, nil)
  assert_equal(broccoli.plugins.instances.emit.state.denied_err.kind, "permission")
  assert_equal(#broccoli.plugins.instances.emit_ok.state.results, 1)
  assert_equal(seen, true)
end)

local failed = 0
for _, test in ipairs(tests) do
  local ok, err = pcall(test.fn)
  if ok then
    io.write("ok - ", test.name, "\n")
  else
    failed = failed + 1
    io.write("not ok - ", test.name, "\n", tostring(err), "\n")
  end
end

if failed > 0 then
  error(tostring(failed) .. " test(s) failed")
end

io.write("# ", tostring(#tests), " tests passed\n")
