local M = {}
local Adapter = {}
Adapter.__index = Adapter

function M.new(opts)
  opts = opts or {}
  return setmetatable({
    path = opts.path,
    adapter = opts.adapter,
  }, Adapter)
end

function Adapter:exec(sql, params)
  if type(self.adapter) ~= "table" or type(self.adapter.exec) ~= "function" then
    return nil, { kind = "config", message = "sqlite adapter with exec(sql, params) is required" }
  end
  return self.adapter.exec(sql, params or {})
end

function Adapter:query(sql, params)
  if type(self.adapter) ~= "table" or type(self.adapter.query) ~= "function" then
    return nil, { kind = "config", message = "sqlite adapter with query(sql, params) is required" }
  end
  return self.adapter.query(sql, params or {})
end

return M
