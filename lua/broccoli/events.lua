local M = {}
local Registry = {}
Registry.__index = Registry

local function now_ms()
  return math.floor(os.clock() * 1000)
end

local function copy_subscription(subscription)
  return {
    id = subscription.id,
    event = subscription.event,
    owner_plugin = subscription.owner_plugin,
  }
end

function M.new(opts)
  opts = opts or {}
  return setmetatable({ subscriptions = {}, order = {}, next_id = 1, now_ms = opts.now_ms or now_ms }, Registry)
end

function Registry:on(event, handler, opts)
  opts = opts or {}
  if type(event) ~= "string" or event == "" then
    return nil, { kind = "validation", message = "event name must be a non-empty string" }
  end
  if type(handler) ~= "function" then
    return nil, { kind = "validation", message = "event handler must be a function" }
  end
  local id = self.next_id
  self.next_id = self.next_id + 1
  local subscription = {
    id = id,
    event = event,
    handler = handler,
    owner_plugin = opts.owner_plugin,
  }
  self.subscriptions[id] = subscription
  self.order[#self.order + 1] = id
  return copy_subscription(subscription), nil
end

function Registry:off(handle)
  local id = type(handle) == "table" and handle.id or handle
  if not self.subscriptions[id] then
    return true, nil
  end
  self.subscriptions[id] = nil
  for index, value in ipairs(self.order) do
    if value == id then
      table.remove(self.order, index)
      break
    end
  end
  return true, nil
end

function Registry:list(opts)
  opts = opts or {}
  local rows = {}
  for _, id in ipairs(self.order) do
    local subscription = self.subscriptions[id]
    if subscription and (not opts.owner_plugin or subscription.owner_plugin == opts.owner_plugin) then
      rows[#rows + 1] = copy_subscription(subscription)
    end
  end
  return rows, nil
end

function Registry:emit(event, payload, opts)
  opts = opts or {}
  local results = {}
  for _, id in ipairs(self.order) do
    local subscription = self.subscriptions[id]
    if subscription and subscription.event == event then
      local start = self.now_ms()
      local ok, value = pcall(subscription.handler, payload, { event = event, id = id })
      local elapsed = self.now_ms() - start
      local result = { id = id, event = event, owner_plugin = subscription.owner_plugin, elapsed_ms = elapsed }
      if not ok then
        result.error = { kind = "event", message = tostring(value) }
      elseif opts.timeout_ms and elapsed > opts.timeout_ms then
        result.error = { kind = "timeout", message = "event handler exceeded timeout" }
      else
        result.result = value
      end
      results[#results + 1] = result
    end
  end
  return results, nil
end

function Registry:clear_owner(owner_plugin)
  if not owner_plugin then
    return true, nil
  end
  local ids = {}
  for id, subscription in pairs(self.subscriptions) do
    if subscription.owner_plugin == owner_plugin then
      ids[#ids + 1] = id
    end
  end
  for _, id in ipairs(ids) do
    self:off(id)
  end
  return true, nil
end

return M
