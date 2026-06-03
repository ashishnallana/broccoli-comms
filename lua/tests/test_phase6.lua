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
  broccoli.setup({})
  broccoli.reset_plugins()
  broccoli.agents.reset_memory()
  broccoli._agents.now_ms = function() return 1000 end
end

add("trusted config can write user metadata", function()
  reset()
  local ok, err = broccoli.agents.set_metadata("agent-a", "user", "label", "primary", { persist = false })
  assert_equal(err, nil)
  assert_equal(ok, true)

  local value = broccoli.agents.get_metadata("agent-a", "user", "label", { persist = false })
  assert_equal(value, "primary")
end)

add("plugin writes own default namespace", function()
  reset()
  package.preload["phase6.writer"] = function()
    return { setup = function(ctx)
      local ok, err = ctx.broccoli.agents.set_metadata("agent-b", nil, "status", "ready", { persist = false })
      ctx.state.set_ok = ok
      ctx.state.set_err = err
      ctx.state.value = ctx.broccoli.agents.get_metadata("agent-b", nil, "status", { persist = false })
    end }
  end

  broccoli.plugins:use("phase6.writer", { name = "writer", permissions = { metadata = { read = true, write = true } } })
  broccoli.plugins:load_all()

  local instance = broccoli.plugins.instances.writer
  assert_equal(instance.state.set_err, nil)
  assert_equal(instance.state.set_ok, true)
  assert_equal(instance.state.value, "ready")
  assert_equal(broccoli.agents.get_metadata("agent-b", "plugin.writer", "status", { persist = false }), "ready")
end)

add("plugin cannot write reserved namespace", function()
  reset()
  package.preload["phase6.reserved"] = function()
    return { setup = function(ctx)
      local ok, err = ctx.broccoli.agents.set_metadata("agent-b", "user", "status", "bad", { persist = false })
      ctx.state.ok = ok
      ctx.state.err = err
    end }
  end

  broccoli.plugins:use("phase6.reserved", { name = "reserved", permissions = { metadata = { write = true } } })
  broccoli.plugins:load_all()

  local instance = broccoli.plugins.instances.reserved
  assert_equal(instance.state.ok, nil)
  assert_equal(instance.state.err.kind, "permission")
  assert_equal(broccoli.agents.get_metadata("agent-b", "user", "status", { persist = false }), nil)
end)

add("TTL expired values are omitted by default", function()
  reset()
  local now = 1000
  broccoli._agents.now_ms = function() return now end
  broccoli.agents.set_metadata("agent-c", "user", "temp", "hot", { ttl_ms = 100, persist = false })
  assert_equal(broccoli.agents.get_metadata("agent-c", "user", "temp", { persist = false }), "hot")
  now = 1200
  assert_equal(broccoli.agents.get_metadata("agent-c", "user", "temp", { persist = false }), nil)
  assert_equal(broccoli.agents.get_metadata("agent-c", "user", "temp", { persist = false, include_expired_metadata = true }), "hot")
end)

add("metadata values must be serializable and size-limited", function()
  reset()
  local ok, err = broccoli.agents.set_metadata("agent-d", "user", "bad", function() end, { persist = false })
  assert_equal(ok, nil)
  assert_equal(err.kind, "validation")

  local cycle = {}
  cycle.self = cycle
  ok, err = broccoli.agents.set_metadata("agent-d", "user", "cycle", cycle, { persist = false })
  assert_equal(ok, nil)
  assert_equal(err.kind, "validation")

  ok, err = broccoli.agents.set_metadata("agent-d", "user", "big", "too-large", { persist = false, max_bytes = 1 })
  assert_equal(ok, nil)
  assert_equal(err.kind, "validation")
end)

add("multiple plugins write separate namespaces", function()
  reset()
  package.preload["phase6.one"] = function()
    return { setup = function(ctx)
      ctx.broccoli.agents.set_metadata("agent-e", nil, "flag", "one", { persist = false })
    end }
  end
  package.preload["phase6.two"] = function()
    return { setup = function(ctx)
      ctx.broccoli.agents.set_metadata("agent-e", nil, "flag", "two", { persist = false })
    end }
  end

  broccoli.plugins:use("phase6.one", { name = "one", permissions = { metadata = { write = true } } })
  broccoli.plugins:use("phase6.two", { name = "two", permissions = { metadata = { write = true } } })
  broccoli.plugins:load_all()

  assert_equal(broccoli.agents.get_metadata("agent-e", "plugin.one", "flag", { persist = false }), "one")
  assert_equal(broccoli.agents.get_metadata("agent-e", "plugin.two", "flag", { persist = false }), "two")
end)

add("metadata prefix filters namespaces", function()
  reset()
  broccoli.agents.set_metadata("agent-prefix", "plugin.one", "flag", "one", { persist = false })
  broccoli.agents.set_metadata("agent-prefix", "user", "label", "primary", { persist = false })

  local rows = broccoli.agents.list_metadata("agent-prefix", { persist = false, metadata_prefix = "plugin." })
  assert_equal(#rows, 1)
  assert_equal(rows[1].namespace, "plugin.one")
  assert_equal(rows[1].key, "flag")
  assert_equal(rows[1].value, "one")
end)

add("storage-backed metadata filters namespaces", function()
  reset()
  local adapter = {
    exec = function()
      return true, nil
    end,
    query = function()
      return {
        { agent_key = "agent-store", namespace = "plugin.one", key = "flag", value_json = "one", persist = 1 },
        { agent_key = "agent-store", namespace = "user", key = "label", value_json = "primary", persist = 1 },
        { agent_key = "agent-store", namespace = "plugin.two", key = "flag", value_json = "two", persist = 1 },
      }, nil
    end,
  }
  broccoli.setup({ storage = { adapter = adapter } })
  broccoli._agents.now_ms = function() return 1000 end

  local prefix_rows = broccoli.agents.list_metadata("agent-store", { metadata_prefix = "plugin." })
  assert_equal(#prefix_rows, 2)
  local by_namespace = {}
  for _, row in ipairs(prefix_rows) do
    by_namespace[row.namespace] = row.value
  end
  assert_equal(by_namespace["plugin.one"], "one")
  assert_equal(by_namespace["plugin.two"], "two")
  assert_equal(by_namespace.user, nil)

  local namespace_rows = broccoli.agents.list_metadata("agent-store", { metadata_namespaces = { "plugin.two" } })
  assert_equal(#namespace_rows, 1)
  assert_equal(namespace_rows[1].namespace, "plugin.two")
  assert_equal(namespace_rows[1].value, "two")
end)

add("storage-backed metadata filters visibility", function()
  reset()
  local stored = {}
  local adapter = {
    exec = function(sql, params)
      if sql:find("INSERT OR REPLACE INTO agent_metadata", 1, true) then
        stored[#stored + 1] = {
          agent_key = params[1],
          namespace = params[2],
          key = params[3],
          value_json = params[4],
          owner_plugin = params[5],
          persist = params[6],
          visibility = params[7],
        }
      end
      return true, nil
    end,
    query = function()
      return stored, nil
    end,
  }
  broccoli.setup({ storage = { adapter = adapter } })
  broccoli._agents.now_ms = function() return 1000 end

  broccoli.agents.set_metadata("agent-visible", "plugin.one", "pub", "yes", { visibility = "public" })
  broccoli.agents.set_metadata("agent-visible", "plugin.one", "priv", "no", {})

  local rows = broccoli.agents.list_metadata("agent-visible", { metadata_visibility = "public" })
  assert_equal(#rows, 1)
  assert_equal(rows[1].key, "pub")
  assert_equal(rows[1].value, "yes")
  assert_equal(rows[1].visibility, "public")

  local private_rows = broccoli.agents.list_metadata("agent-visible", { metadata_visibility = "private" })
  assert_equal(#private_rows, 1)
  assert_equal(private_rows[1].key, "priv")
  assert_equal(private_rows[1].visibility, "private")
end)

add("agent refs accept names UUIDs remote targets and structured refs", function()
  reset()
  assert_equal(broccoli.agents.agent_key("host-a/agent"), "host-a/agent")
  assert_equal(broccoli.agents.agent_key({ target_address = "host-b/agent" }), "host-b/agent")
  assert_equal(broccoli.agents.agent_key({ host = "host-c", name = "agent" }), "host-c/agent")
  assert_equal(broccoli.agents.agent_key({ agent_id = "uuid-1" }), "uuid-1")
end)

add("clear metadata removes one key or namespace", function()
  reset()
  broccoli.agents.set_metadata("agent-f", "user", "a", "1", { persist = false })
  broccoli.agents.set_metadata("agent-f", "user", "b", "2", { persist = false })
  broccoli.agents.clear_metadata("agent-f", "user", "a", { persist = false })
  assert_equal(broccoli.agents.get_metadata("agent-f", "user", "a", { persist = false }), nil)
  assert_equal(broccoli.agents.get_metadata("agent-f", "user", "b", { persist = false }), "2")
  broccoli.agents.clear_metadata("agent-f", "user", nil, { persist = false })
  assert_equal(broccoli.agents.get_metadata("agent-f", "user", "b", { persist = false }), nil)
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
