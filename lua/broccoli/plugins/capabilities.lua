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
    agents = {},
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

  local metadata_permissions = permissions.metadata or permissions.agents or {}
  local plugin_namespace = "plugin." .. tostring(plugin_name)
  local function namespace_or_default(namespace)
    return namespace or plugin_namespace
  end
  local function require_own_namespace(namespace, action)
    if namespace ~= plugin_namespace then
      return nil, {
        kind = "permission",
        code = 0,
        message = "plugin is not permitted to call " .. action .. " outside namespace " .. plugin_namespace,
      }
    end
    return true, nil
  end
  scoped.agents.set_metadata = function(agent_ref, namespace, key, value, opts)
    if not allows(metadata_permissions, "write") then
      return denied("agents.set_metadata")
    end
    namespace = namespace_or_default(namespace)
    local ok, err = require_own_namespace(namespace, "agents.set_metadata")
    if not ok then
      return nil, err
    end
    opts = opts or {}
    opts.owner_plugin = plugin_name
    opts.trusted = false
    return base.agents.set_metadata(agent_ref, namespace, key, value, opts)
  end
  scoped.agents.get_metadata = function(agent_ref, namespace, key, opts)
    if not allows(metadata_permissions, "read") then
      return denied("agents.get_metadata")
    end
    namespace = namespace_or_default(namespace)
    local ok, err = require_own_namespace(namespace, "agents.get_metadata")
    if not ok then
      return nil, err
    end
    opts = opts or {}
    opts.trusted = false
    return base.agents.get_metadata(agent_ref, namespace, key, opts)
  end
  scoped.agents.clear_metadata = function(agent_ref, namespace, key, opts)
    if not allows(metadata_permissions, "write") then
      return denied("agents.clear_metadata")
    end
    namespace = namespace_or_default(namespace)
    local ok, err = require_own_namespace(namespace, "agents.clear_metadata")
    if not ok then
      return nil, err
    end
    opts = opts or {}
    opts.trusted = false
    return base.agents.clear_metadata(agent_ref, namespace, key, opts)
  end
  scoped.agents.list_metadata = function(agent_ref, opts)
    if not allows(metadata_permissions, "read") then
      return denied("agents.list_metadata")
    end
    opts = opts or {}
    opts.namespace = namespace_or_default(opts.namespace)
    local ok, err = require_own_namespace(opts.namespace, "agents.list_metadata")
    if not ok then
      return nil, err
    end
    opts.trusted = false
    return base.agents.list_metadata(agent_ref, opts)
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
