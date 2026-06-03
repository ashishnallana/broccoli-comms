local rpc = require("broccoli.tracker_rpc")
local transport = require("broccoli.transport")

local M = {}
local Client = {}
Client.__index = Client

function M.new(opts)
  opts = opts or {}
  local request_transport = opts.request_transport or transport.new(opts)
  return setmetatable({
    transport = request_transport,
    next_id = opts.next_id or 1,
  }, Client)
end

function Client:call(spec, opts)
  local id = self.next_id
  self.next_id = self.next_id + 1
  local response, transport_err = self.transport:request(rpc.request(spec, id), opts)
  if transport_err then
    return nil, transport_err
  end
  return rpc.result(response)
end

function Client:list(opts)
  return self:call(rpc.list(opts), opts)
end

function Client:send_message(opts)
  return self:call(rpc.send_message(opts), opts)
end

function Client:read_inbox(opts)
  return self:call(rpc.read_inbox(opts), opts)
end

M.Client = Client

return M
