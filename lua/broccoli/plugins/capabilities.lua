local M = {}

local function allows(group, name)
  if group == true then
    return true
  end
  if type(group) ~= "table" then
    return false
  end
  if group[name] == true then
    return true
  end
  for _, value in pairs(group) do
    if value == name then
      return true
    end
  end
  return false
end

local function denied(name)
  return nil, {
    kind = "permission",
    code = 0,
    message = "plugin is not permitted to call " .. name,
  }
end

function M.scoped_api(base, plugin_name, permissions)
  permissions = permissions or {}
  local tracker_permissions = permissions.tracker or {}
  local scoped = {
    plugin_name = plugin_name,
    tracker = {},
    state = {},
    log = base.log or {},
  }

  for _, name in ipairs({ "list", "send_message", "read_inbox" }) do
    scoped.tracker[name] = function(...)
      if not allows(tracker_permissions, name) then
        return denied(name)
      end
      return base.tracker[name](...)
    end
  end

  local state_permissions = permissions.state or {}
  scoped.state.get = function(key)
    if not allows(state_permissions, "read") then
      return denied("state.get")
    end
    if not base.storage then
      return nil, { kind = "config", message = "plugin storage is not configured" }
    end
    return base.storage:get_plugin_state(plugin_name, key)
  end
  scoped.state.set = function(key, value)
    if not allows(state_permissions, "write") then
      return denied("state.set")
    end
    if not base.storage then
      return nil, { kind = "config", message = "plugin storage is not configured" }
    end
    return base.storage:set_plugin_state(plugin_name, key, value)
  end
  scoped.state.clear = function(key)
    if not allows(state_permissions, "write") then
      return denied("state.clear")
    end
    if not base.storage then
      return nil, { kind = "config", message = "plugin storage is not configured" }
    end
    return base.storage:clear_plugin_state(plugin_name, key)
  end

  return scoped
end

return M
