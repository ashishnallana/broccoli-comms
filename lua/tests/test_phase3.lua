package.path = "lua/?.lua;lua/?/init.lua;" .. package.path

local broccoli = require("broccoli")
local config_loader = require("broccoli.config_loader")

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

local function temp_file(contents)
  local path = os.tmpname()
  local file = assert(io.open(path, "w"))
  file:write(contents)
  file:close()
  return path
end

add("config_loader resolves explicit env XDG and HOME paths", function()
  assert_equal(config_loader.default_path({ path = "/explicit/init.lua", env = { BROCCOLI_CONFIG = "/env/init.lua", XDG_CONFIG_HOME = "/cfg", HOME = "/home/user" } }), "/explicit/init.lua")
  assert_equal(config_loader.default_path({ env = { BROCCOLI_CONFIG = "/env/init.lua", XDG_CONFIG_HOME = "/cfg", HOME = "/home/user" } }), "/env/init.lua")
  assert_equal(config_loader.default_path({ env = { BROCCOLI_CONFIG = "", XDG_CONFIG_HOME = "/cfg", HOME = "/home/user" } }), "/cfg/broccoli-comms/init.lua")
  assert_equal(config_loader.default_path({ env = { XDG_CONFIG_HOME = "", HOME = "/home/user" } }), "/home/user/.config/broccoli-comms/init.lua")
end)

add("missing init.lua is a no-op unless required", function()
  local ok, err = config_loader.load("/definitely/missing/broccoli-init.lua", broccoli)
  assert_equal(ok, true)
  assert_equal(err, nil)

  ok, err = config_loader.load("/definitely/missing/broccoli-init.lua", broccoli, { required = true })
  assert_equal(ok, false)
  assert_equal(err.kind, "config")
end)

add("broccoli.setup configures tracker client defaults", function()
  local fake_transport = {
    request = function(_, request)
      return { jsonrpc = "2.0", id = request.id, result = { method = request.method, socket = request.params.socket_path } }
    end,
  }
  broccoli.setup({ tracker = { request_transport = fake_transport } })
  local client = broccoli.new_tracker()
  local result, err = client:list({})
  assert_equal(err, nil)
  assert_equal(result.method, "list")
end)

add("load_init runs trusted init.lua and advances generation", function()
  local path = temp_file([[broccoli.setup({ tracker = { socket_path = "/tmp/from-init.sock", timeout_ms = 42 } })]])
  local before = broccoli.generation()
  local ok, err = broccoli.load_init({ path = path })
  os.remove(path)

  assert_equal(ok, true)
  assert_equal(err, nil)
  assert_equal(broccoli.config().tracker.socket_path, "/tmp/from-init.sock")
  assert_equal(broccoli.config().tracker.timeout_ms, 42)
  assert_equal(broccoli.generation(), before + 1)
end)

add("load_init missing file still records a reload generation", function()
  local before = broccoli.generation()
  local ok, err = broccoli.load_init({ path = "/definitely/missing/broccoli-init.lua" })
  assert_equal(ok, true)
  assert_equal(err, nil)
  assert_equal(broccoli.generation(), before + 1)
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
