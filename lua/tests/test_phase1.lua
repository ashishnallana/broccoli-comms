package.path = "lua/?.lua;lua/?/init.lua;" .. package.path

local rpc = require("broccoli.tracker_rpc")
local transport = require("broccoli.transport")
local tracker = require("broccoli.tracker")
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

add("tracker_rpc maps list include_remote", function()
  assert_equal(rpc.list({ include_remote = true }), {
    method = "list",
    params = { include_remote = true },
  })
end)

add("tracker_rpc maps local send target", function()
  assert_equal(rpc.send_message({ target = "agent", message = "hello" }), {
    method = "send_message",
    params = { agent_name = "agent", message = "hello" },
  })
end)

add("tracker_rpc maps remote send target", function()
  assert_equal(rpc.send_message({ target = "host/agent", message = "hello" }), {
    method = "send_message",
    params = { target_address = "host/agent", message = "hello" },
  })
end)

add("tracker_rpc preserves explicit agent_id and optional send params", function()
  local attachments = { { name = "note.txt", content_b64 = "aGk=" } }
  assert_equal(rpc.send_message({
    target = "ignored-name",
    agent_id = "agent-uuid",
    message = "hello",
    sender_name = "sender",
    sender_id = "sender-id",
    message_id = "mid",
    attachments = attachments,
    verify = true,
  }), {
    method = "send_message",
    params = {
      agent_id = "agent-uuid",
      message = "hello",
      sender_name = "sender",
      sender_id = "sender-id",
      message_id = "mid",
      attachments = attachments,
      verify = true,
    },
  })
end)

add("tracker_rpc maps read_inbox filters", function()
  assert_equal(rpc.read_inbox({
    agent_name = "agent-communicator",
    last = 10,
    clear = false,
    mark_read = true,
    sender_name = "review-agent",
    sender_agent_id = "sender-id",
    sender_tracker_id = "tracker-id",
  }), {
    method = "get_inbox",
    params = {
      agent_name = "agent-communicator",
      last_n = 10,
      clear = false,
      mark_read = true,
      sender_name = "review-agent",
      sender_agent_id = "sender-id",
      sender_tracker_id = "tracker-id",
    },
  })
end)

add("tracker_rpc maps RPC success and error responses", function()
  local result, err = rpc.result({ jsonrpc = "2.0", id = 1, result = { ok = true } })
  assert_equal(result, { ok = true })
  assert_equal(err, nil)

  result, err = rpc.result({ jsonrpc = "2.0", id = 1, error = { code = -32602, message = "Invalid params", data = { retryable = false } } })
  assert_equal(result, nil)
  assert_equal(err, { kind = "rpc", code = -32602, message = "Invalid params", data = { retryable = false } })
end)

local passthrough_json = {
  encode = function(value) return value end,
  decode = function(value) return value end,
}

add("transport fake adapter returns decoded response", function()
  local seen = {}
  local t = transport.new({
    socket_path = "/tmp/tracker.sock",
    timeout_ms = 123,
    json = passthrough_json,
    transport = {
      request = function(socket_path, payload, timeout_ms)
        seen = { socket_path = socket_path, payload = payload, timeout_ms = timeout_ms }
        return { jsonrpc = "2.0", id = payload.id, result = true }
      end,
    },
  })

  local response, err = t:request({ jsonrpc = "2.0", id = 7, method = "list", params = {} })
  assert_equal(err, nil)
  assert_equal(response, { jsonrpc = "2.0", id = 7, result = true })
  assert_equal(seen.socket_path, "/tmp/tracker.sock")
  assert_equal(seen.timeout_ms, 123)
  assert_equal(seen.payload.method, "list")
end)

add("transport maps config transport and decode errors", function()
  local response, err = transport.new({}):request({})
  assert_equal(response, nil)
  assert_equal(err.kind, "config")

  response, err = transport.new({ socket_path = "/tmp/socket", json = passthrough_json }):request({})
  assert_equal(response, nil)
  assert_equal(err.kind, "config")

  response, err = transport.new({
    socket_path = "/tmp/socket",
    json = passthrough_json,
    transport = { request = function() return nil, { kind = "timeout", message = "deadline" } end },
  }):request({})
  assert_equal(response, nil)
  assert_equal(err.kind, "timeout")

  response, err = transport.new({
    socket_path = "/tmp/socket",
    json = { encode = function(value) return value end, decode = function() error("bad json") end },
    transport = { request = function() return "not-json" end },
  }):request({})
  assert_equal(response, nil)
  assert_equal(err.kind, "decode")
end)

add("tracker facade composes rpc mapping and transport", function()
  local requests = {}
  local fake_transport = {
    request = function(_, request)
      requests[#requests + 1] = request
      return { jsonrpc = "2.0", id = request.id, result = { method = request.method, params = request.params } }
    end,
  }
  local client = tracker.new({ request_transport = fake_transport })

  local result, err = client:list({ include_remote = true })
  assert_equal(err, nil)
  assert_equal(result, { method = "list", params = { include_remote = true } })

  result, err = client:send_message({ target = "host/agent", message = "hello" })
  assert_equal(err, nil)
  assert_equal(result, { method = "send_message", params = { target_address = "host/agent", message = "hello" } })

  result, err = client:read_inbox({ agent_name = "agent-communicator", last = 3 })
  assert_equal(err, nil)
  assert_equal(result, { method = "get_inbox", params = { agent_name = "agent-communicator", last_n = 3 } })

  assert_equal(#requests, 3)
end)

add("public broccoli facade constructs tracker clients", function()
  local client = broccoli.new({ request_transport = { request = function(_, request) return { result = request.method } end } })
  local result, err = client:list({})
  assert_equal(err, nil)
  assert_equal(result, "list")
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
