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
  broccoli.reset_plugins()
  broccoli.setup({})
end

local function temp_file(contents)
  local path = os.tmpname() .. ".lua"
  local file = assert(io.open(path, "w"))
  file:write(contents)
  file:close()
  return path
end

add("plugins load in dependency order with setup opts", function()
  reset()
  local order = {}
  package.preload["phase4.dep"] = function()
    return { setup = function(ctx) order[#order + 1] = ctx.plugin.name end }
  end
  package.preload["phase4.main"] = function()
    return {
      defaults = { greeting = "hello" },
      setup = function(ctx, opts)
        order[#order + 1] = ctx.plugin.name .. ":" .. opts.greeting
      end,
    }
  end

  broccoli.plugins:use("phase4.main", { name = "main", requires = { "dep" }, opts = { greeting = "hi" } })
  broccoli.plugins:use("phase4.dep", { name = "dep" })
  broccoli.plugins:load_all()

  assert_equal(order, { "dep", "main:hi" })
  assert_equal(broccoli.plugins.instances.main.status, "loaded")
end)

add("disabled and broken plugins are isolated", function()
  reset()
  package.preload["phase4.disabled"] = function()
    return { setup = function() error("should not run") end }
  end
  package.preload["phase4.broken"] = function()
    return { setup = function() error("boom") end }
  end

  broccoli.plugins:use("phase4.disabled", { name = "disabled", enabled = false })
  broccoli.plugins:use("phase4.broken", { name = "broken" })
  local statuses = broccoli.plugins:load_all()

  assert_equal(statuses[1].status, "disabled")
  assert_equal(statuses[2].status, "error")
end)

add("missing required dependency fails only dependent plugin", function()
  reset()
  package.preload["phase4.lonely"] = function()
    return { setup = function() error("should not load") end }
  end

  broccoli.plugins:use("phase4.lonely", { name = "lonely", requires = { "missing" } })
  local statuses = broccoli.plugins:load_all()

  assert_equal(statuses[1].status, "error")
end)

add("tracker permissions are denied by default and allowed explicitly", function()
  reset()
  broccoli.setup({
    tracker = {
      request_transport = {
        request = function(_, request)
          return { jsonrpc = "2.0", id = request.id, result = { ok = true } }
        end,
      },
    },
  })

  package.preload["phase4.denied"] = function()
    return { setup = function(ctx)
      local _, err = ctx.broccoli.tracker.list({})
      ctx.state.err_kind = err and err.kind
    end }
  end
  package.preload["phase4.allowed"] = function()
    return { setup = function(ctx)
      local result, err = ctx.broccoli.tracker.list({})
      ctx.state.ok = result and result.ok
      ctx.state.err = err
    end }
  end

  broccoli.plugins:use("phase4.denied", { name = "denied" })
  broccoli.plugins:use("phase4.allowed", { name = "allowed", permissions = { tracker = { list = true } } })
  broccoli.plugins:load_all()

  assert_equal(broccoli.plugins.instances.denied.state.err_kind, "permission")
  assert_equal(broccoli.plugins.instances.allowed.state.ok, true)
  assert_equal(broccoli.plugins.instances.allowed.state.err, nil)
end)

add("path plugin top-level uses scoped tracker permissions", function()
  reset()
  broccoli.setup({
    tracker = {
      request_transport = {
        request = function(_, request)
          return { jsonrpc = "2.0", id = request.id, result = { ok = true } }
        end,
      },
    },
  })
  local path = temp_file([[
local result, err = broccoli.tracker.list({})
return {
  setup = function(ctx)
    ctx.state.ok = result and result.ok
    ctx.state.err_kind = err and err.kind
  end,
}
]])

  broccoli.plugins:use(path, { name = "path-denied" })
  broccoli.plugins:use(path, { name = "path-allowed", permissions = { tracker = { list = true } } })
  broccoli.plugins:load_all()
  os.remove(path)

  assert_equal(broccoli.plugins.instances["path-denied"].state.err_kind, "permission")
  assert_equal(broccoli.plugins.instances["path-denied"].state.ok, nil)
  assert_equal(broccoli.plugins.instances["path-allowed"].state.ok, true)
  assert_equal(broccoli.plugins.instances["path-allowed"].state.err_kind, nil)
end)

add("disable calls teardown and removes instance", function()
  reset()
  local torn_down = false
  package.preload["phase4.teardown"] = function()
    return { teardown = function() torn_down = true end }
  end

  broccoli.plugins:use("phase4.teardown", { name = "teardown" })
  broccoli.plugins:load_all()
  assert_equal(broccoli.plugins.instances.teardown.status, "loaded")
  broccoli.plugins:disable("teardown")

  assert_equal(torn_down, true)
  assert_equal(broccoli.plugins.instances.teardown, nil)
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
