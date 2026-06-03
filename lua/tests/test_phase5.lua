package.path = "lua/?.lua;lua/?/init.lua;" .. package.path

local broccoli = require("broccoli")
local storage = require("broccoli.storage")
local migrations = require("broccoli.storage.migrations")

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

local function fake_adapter()
  local adapter = { execs = {}, queries = {}, state = {}, errors = {} }
  function adapter.exec(sql, params)
    adapter.execs[#adapter.execs + 1] = { sql = sql, params = params }
    if sql:find("INSERT OR REPLACE INTO plugin_state", 1, true) then
      adapter.state[params[1] .. ":" .. params[2]] = params[3]
    elseif sql:find("DELETE FROM plugin_state", 1, true) then
      adapter.state[params[1] .. ":" .. params[2]] = nil
    elseif sql:find("INSERT INTO plugin_errors", 1, true) then
      adapter.errors[#adapter.errors + 1] = params
    end
    return true, nil
  end
  function adapter.query(sql, params)
    adapter.queries[#adapter.queries + 1] = { sql = sql, params = params }
    if sql:find("SELECT value_json FROM plugin_state", 1, true) then
      local value = adapter.state[params[1] .. ":" .. params[2]]
      if value == nil then
        return {}, nil
      end
      return { { value_json = value } }, nil
    end
    return {}, nil
  end
  return adapter
end

add("storage resolves explicit env XDG and HOME paths", function()
  assert_equal(storage.default_path({ path = "/explicit.sqlite3", env = { BROCCOLI_PLUGIN_STATE_DB = "/env.sqlite3", XDG_STATE_HOME = "/state", HOME = "/home/user" } }), "/explicit.sqlite3")
  assert_equal(storage.default_path({ env = { BROCCOLI_PLUGIN_STATE_DB = "/env.sqlite3", XDG_STATE_HOME = "/state", HOME = "/home/user" } }), "/env.sqlite3")
  assert_equal(storage.default_path({ env = { BROCCOLI_PLUGIN_STATE_DB = "", XDG_STATE_HOME = "/state", HOME = "/home/user" } }), "/state/broccoli-comms/plugin-state.sqlite3")
  assert_equal(storage.default_path({ env = { XDG_STATE_HOME = "", HOME = "/home/user" } }), "/home/user/.local/state/broccoli-comms/plugin-state.sqlite3")
end)

add("setup clears storage when storage config is absent", function()
  broccoli.setup({ storage = { adapter = fake_adapter() } })
  assert_equal(type(broccoli.storage), "table")
  broccoli.setup({})
  assert_equal(broccoli.storage, nil)
end)

add("migrations run through adapter", function()
  local adapter = fake_adapter()
  local store = storage.new({ adapter = adapter, now = function() return "now" end })
  local ok, err = store:migrate()
  assert_equal(err, nil)
  assert_equal(ok, true)
  assert_equal(#adapter.execs, #migrations.statements * 2)
end)

add("migrations return schema statement errors", function()
  local boom = { kind = "sqlite", message = "boom" }
  local adapter = {
    exec = function()
      return false, boom
    end,
    query = function()
      return {}, nil
    end,
  }
  local store = storage.new({ adapter = adapter })
  local ok, err = store:migrate()
  assert_equal(ok, nil)
  assert_equal(err, boom)
end)

add("migrations return version insert errors", function()
  local boom = { kind = "sqlite", message = "insert boom" }
  local calls = 0
  local adapter = {
    exec = function(sql)
      calls = calls + 1
      if sql:find("INSERT OR IGNORE INTO schema_migrations", 1, true) then
        return false, boom
      end
      return true, nil
    end,
    query = function()
      return {}, nil
    end,
  }
  local store = storage.new({ adapter = adapter })
  local ok, err = store:migrate()
  assert_equal(ok, nil)
  assert_equal(err, boom)
  assert_equal(calls, 2)
end)

add("plugin state works through scoped plugin API", function()
  local adapter = fake_adapter()
  broccoli.reset_plugins()
  broccoli.setup({ storage = { adapter = adapter, now = function() return "now" end } })

  package.preload["phase5.state"] = function()
    return { setup = function(ctx)
      ctx.broccoli.state.set("answer", "42")
      local value = ctx.broccoli.state.get("answer")
      ctx.state.value = value
      ctx.broccoli.state.clear("answer")
      local cleared = ctx.broccoli.state.get("answer")
      ctx.state.cleared = cleared
    end }
  end

  broccoli.plugins:use("phase5.state", { name = "state", permissions = { state = { read = true, write = true } } })
  broccoli.plugins:load_all()

  assert_equal(broccoli.plugins.instances.state.state.value, "42")
  assert_equal(broccoli.plugins.instances.state.state.cleared, nil)
end)

add("plugin errors are recorded through storage", function()
  local adapter = fake_adapter()
  broccoli.reset_plugins()
  broccoli.setup({ storage = { adapter = adapter, now = function() return "now" end } })

  package.preload["phase5.broken"] = function()
    return { setup = function() error("boom") end }
  end

  broccoli.plugins:use("phase5.broken", { name = "broken" })
  broccoli.plugins:load_all()

  assert_equal(#adapter.errors, 1)
  assert_equal(adapter.errors[1][1], "broken")
  assert_equal(adapter.errors[1][2], "load")
end)

add("expired metadata cleanup uses migration SQL", function()
  local adapter = fake_adapter()
  local store = storage.new({ adapter = adapter })
  store:cleanup_expired_metadata("2026-01-01T00:00:00Z")

  assert_equal(adapter.execs[1].sql, migrations.cleanup_expired_metadata_sql)
  assert_equal(adapter.execs[1].params, { "2026-01-01T00:00:00Z" })
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
