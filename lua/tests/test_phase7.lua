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

local function tracker_rows()
  return {
    alpha = { name = "alpha", agent_id = "id-alpha", status = "online" },
    remote = { name = "remote", target_address = "host/remote", status = "idle" },
  }
end

local function reset(rows)
  rows = rows or tracker_rows()
  broccoli.setup({ tracker = { request_transport = { request = function(_, request)
    return { jsonrpc = "2.0", id = request.id, result = rows }
  end } } })
  broccoli.reset_plugins()
  broccoli.agents.reset_memory()
  broccoli._agents.now_ms = function() return 1000 end
  return rows
end

add("agent list without metadata matches tracker result snapshot", function()
  local rows = reset()
  local result, err = broccoli.agents.list({ include_remote = true })
  assert_equal(err, nil)
  assert_equal(result, rows)
  result.alpha.status = "mutated"

  local again = broccoli.agents.list({ include_remote = true })
  assert_equal(again.alpha.status, "online")
end)

add("agent list with metadata adds namespaced metadata maps", function()
  reset()
  broccoli.agents.set_metadata("id-alpha", "user", "label", "primary", { persist = false, visibility = "public" })
  broccoli.agents.set_metadata("id-alpha", "plugin.one", "flag", "yes", { persist = false })
  broccoli.agents.set_metadata("host/remote", "user", "label", "remote", { persist = false })

  local result, err = broccoli.agents.list({ include_metadata = true })
  assert_equal(err, nil)
  assert_equal(result.alpha.metadata.user.label, "primary")
  assert_equal(result.alpha.metadata["plugin.one"].flag, "yes")
  assert_equal(result.remote.metadata.user.label, "remote")
end)

add("agent get finds local and remote refs with metadata", function()
  reset()
  broccoli.agents.set_metadata("host/remote", "user", "label", "remote", { persist = false })

  local result, err = broccoli.agents.get("host/remote", { include_metadata = true })
  assert_equal(err, nil)
  assert_equal(result.name, "remote")
  assert_equal(result.metadata.user.label, "remote")

  result = broccoli.agents.get("id-alpha", {})
  assert_equal(result.name, "alpha")
end)

add("agent list merges metadata set by local name alias", function()
  reset()
  broccoli.agents.set_metadata("alpha", "user", "label", "by-name", { persist = false })

  local result, err = broccoli.agents.list({ include_metadata = true })
  assert_equal(err, nil)
  assert_equal(result.alpha.metadata.user.label, "by-name")
end)

add("agent get by ID includes metadata set by local name alias", function()
  reset()
  broccoli.agents.set_metadata("alpha", "user", "label", "by-name", { persist = false })

  local result, err = broccoli.agents.get("id-alpha", { include_metadata = true })
  assert_equal(err, nil)
  assert_equal(result.name, "alpha")
  assert_equal(result.metadata.user.label, "by-name")
end)

add("metadata filters apply to merged agent list", function()
  reset()
  broccoli.agents.set_metadata("id-alpha", "user", "label", "primary", { persist = false, visibility = "public" })
  broccoli.agents.set_metadata("id-alpha", "plugin.one", "flag", "one", { persist = false, visibility = "private" })
  broccoli.agents.set_metadata("id-alpha", "plugin.two", "flag", "two", { persist = false, visibility = "public" })

  local prefix = broccoli.agents.list({ include_metadata = true, metadata_prefix = "plugin." })
  assert_equal(prefix.alpha.metadata.user, nil)
  assert_equal(prefix.alpha.metadata["plugin.one"].flag, "one")
  assert_equal(prefix.alpha.metadata["plugin.two"].flag, "two")

  local namespaces = broccoli.agents.list({ include_metadata = true, metadata_namespaces = { "plugin.two" } })
  assert_equal(namespaces.alpha.metadata["plugin.one"], nil)
  assert_equal(namespaces.alpha.metadata["plugin.two"].flag, "two")

  local public = broccoli.agents.list({ include_metadata = true, metadata_visibility = "public" })
  assert_equal(public.alpha.metadata.user.label, "primary")
  assert_equal(public.alpha.metadata["plugin.one"], nil)
  assert_equal(public.alpha.metadata["plugin.two"].flag, "two")
end)

add("expired metadata is omitted from merged results", function()
  reset()
  local now = 1000
  broccoli._agents.now_ms = function() return now end
  broccoli.agents.set_metadata("id-alpha", "user", "temp", "hot", { persist = false, ttl_ms = 100 })
  now = 1200

  local result = broccoli.agents.list({ include_metadata = true })
  assert_equal(result.alpha.metadata.user, nil)

  result = broccoli.agents.list({ include_metadata = true, include_expired_metadata = true })
  assert_equal(result.alpha.metadata.user.temp, "hot")
end)

add("plugin merged metadata is permission scoped", function()
  reset()
  broccoli.agents.set_metadata("id-alpha", "user", "label", "primary", { persist = false })
  broccoli.agents.set_metadata("id-alpha", "plugin.reader", "flag", "allowed", { persist = false })

  package.preload["phase7.reader"] = function()
    return { setup = function(ctx)
      local result, err = ctx.broccoli.agents.list({ include_metadata = true })
      ctx.state.err = err
      ctx.state.result = result
    end }
  end
  package.preload["phase7.denied"] = function()
    return { setup = function(ctx)
      local result, err = ctx.broccoli.agents.list({ include_metadata = true })
      ctx.state.result = result
      ctx.state.err = err
    end }
  end

  broccoli.plugins:use("phase7.reader", { name = "reader", permissions = { metadata = { read = true } } })
  broccoli.plugins:use("phase7.denied", { name = "denied" })
  broccoli.plugins:load_all()

  local reader = broccoli.plugins.instances.reader
  assert_equal(reader.state.err, nil)
  assert_equal(reader.state.result.alpha.metadata.user, nil)
  assert_equal(reader.state.result.alpha.metadata["plugin.reader"].flag, "allowed")

  local denied = broccoli.plugins.instances.denied
  assert_equal(denied.state.result, nil)
  assert_equal(denied.state.err.kind, "permission")
end)

add("storage and memory metadata merge at query time", function()
  local stored = {
    { agent_key = "id-alpha", namespace = "plugin.store", key = "flag", value_json = "stored", persist = 1, visibility = "public" },
  }
  local adapter = {
    exec = function()
      return true, nil
    end,
    query = function()
      return stored, nil
    end,
  }
  reset()
  broccoli.setup({
    tracker = { request_transport = { request = function(_, request)
      return { jsonrpc = "2.0", id = request.id, result = tracker_rows() }
    end } },
    storage = { adapter = adapter },
  })
  broccoli._agents.now_ms = function() return 1000 end
  broccoli.agents.set_metadata("id-alpha", "plugin.mem", "flag", "memory", { persist = false })

  local result = broccoli.agents.list({ include_metadata = true, metadata_prefix = "plugin." })
  assert_equal(result.alpha.metadata["plugin.store"].flag, "stored")
  assert_equal(result.alpha.metadata["plugin.mem"].flag, "memory")
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
