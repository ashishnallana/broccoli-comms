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
    message = "plugin is not permitted to call tracker." .. name,
  }
end

function M.scoped_api(base, plugin_name, permissions)
  permissions = permissions or {}
  local tracker_permissions = permissions.tracker or {}
  local scoped = {
    plugin_name = plugin_name,
    tracker = {},
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

  return scoped
end

return M
