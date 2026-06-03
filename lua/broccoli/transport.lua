local M = {}

local function structured_error(kind, message, data)
  return {
    kind = kind,
    code = data and data.code or 0,
    message = message,
    data = data,
  }
end

local function normalize_error(default_kind, err)
  if type(err) == "table" then
    err.kind = err.kind or default_kind
    err.message = err.message or "transport error"
    err.code = err.code or 0
    return err
  end
  return structured_error(default_kind, tostring(err or "transport error"))
end

local Transport = {}
Transport.__index = Transport

function M.new(opts)
  opts = opts or {}
  return setmetatable({
    socket_path = opts.socket_path,
    timeout_ms = opts.timeout_ms or 5000,
    adapter = opts.transport,
    json = opts.json,
  }, Transport)
end

function Transport:request(request_table, opts)
  opts = opts or {}
  if not self.socket_path or self.socket_path == "" then
    return nil, structured_error("config", "socket_path is required")
  end
  if type(self.adapter) ~= "table" or type(self.adapter.request) ~= "function" then
    return nil, structured_error("config", "transport adapter with request(socket_path, payload, timeout_ms) is required")
  end
  if type(self.json) ~= "table" or type(self.json.encode) ~= "function" or type(self.json.decode) ~= "function" then
    return nil, structured_error("config", "json adapter with encode/decode is required")
  end

  local ok, payload = pcall(self.json.encode, request_table)
  if not ok then
    return nil, structured_error("decode", "failed to encode JSON-RPC request", { cause = payload })
  end

  local timeout_ms = opts.timeout_ms or self.timeout_ms
  local request_ok, response_payload, request_err = pcall(self.adapter.request, self.socket_path, payload, timeout_ms)
  if not request_ok then
    return nil, structured_error("transport", "transport adapter failed", { cause = response_payload })
  end
  if request_err ~= nil then
    return nil, normalize_error("transport", request_err)
  end
  if response_payload == nil then
    return nil, structured_error("transport", "transport adapter returned no response")
  end

  local decode_ok, response = pcall(self.json.decode, response_payload)
  if not decode_ok then
    return nil, structured_error("decode", "failed to decode JSON-RPC response", { cause = response })
  end
  if type(response) ~= "table" then
    return nil, structured_error("decode", "decoded JSON-RPC response must be a table")
  end

  return response, nil
end

M.structured_error = structured_error
M.normalize_error = normalize_error

return M
