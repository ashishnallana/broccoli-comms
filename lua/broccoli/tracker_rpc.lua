local M = {}

local function copy_selected(source, target, keys)
  for _, key in ipairs(keys) do
    if source[key] ~= nil then
      target[key] = source[key]
    end
  end
end

function M.error(kind, message, extra)
  local err = extra or {}
  err.kind = err.kind or kind
  err.message = err.message or message
  return err
end

function M.request(spec, id)
  return {
    jsonrpc = "2.0",
    id = id or 1,
    method = spec.method,
    params = spec.params or {},
  }
end

function M.result(response)
  if type(response) ~= "table" then
    return nil, M.error("decode", "response must be a table")
  end
  if response.error ~= nil then
    local rpc_error = response.error
    if type(rpc_error) ~= "table" then
      return nil, M.error("rpc", tostring(rpc_error), { code = 0 })
    end
    return nil, M.error("rpc", rpc_error.message or "RPC error", {
      code = rpc_error.code,
      data = rpc_error.data,
    })
  end
  return response.result, nil
end

function M.list(opts)
  opts = opts or {}
  local params = {}
  copy_selected(opts, params, { "include_remote" })
  return { method = "list", params = params }
end

function M.send_message(opts)
  opts = opts or {}
  local params = {}

  if opts.agent_id ~= nil then
    params.agent_id = opts.agent_id
  elseif opts.target_address ~= nil then
    params.target_address = opts.target_address
  elseif opts.agent_name ~= nil then
    params.agent_name = opts.agent_name
  elseif opts.target ~= nil then
    if type(opts.target) == "string" and opts.target:find("/", 1, true) then
      params.target_address = opts.target
    else
      params.agent_name = opts.target
    end
  end

  copy_selected(opts, params, {
    "message",
    "attachments",
    "sender_name",
    "sender_id",
    "message_id",
    "verify",
  })

  return { method = "send_message", params = params }
end

function M.read_inbox(opts)
  opts = opts or {}
  local params = {}

  copy_selected(opts, params, {
    "agent_name",
    "agent_id",
    "clear",
    "mark_read",
    "sender_name",
    "sender_agent_id",
    "sender_tracker_id",
  })

  if opts.last ~= nil then
    params.last_n = opts.last
  elseif opts.last_n ~= nil then
    params.last_n = opts.last_n
  end

  return { method = "get_inbox", params = params }
end

return M
