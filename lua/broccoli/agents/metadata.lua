local M = {}

local RESERVED_NAMESPACES = { user = true, global = true, internal = true }

local function shallow_copy(value)
  local out = {}
  for key, item in pairs(value or {}) do
    out[key] = item
  end
  return out
end

local function validate_json_value(value, seen)
  local kind = type(value)
  if kind == "string" then
    return true, #value
  end
  if kind == "nil" or kind == "number" or kind == "boolean" then
    return true, #tostring(value)
  end
  if kind ~= "table" then
    return false, { kind = "validation", message = "metadata value must be JSON-serializable" }
  end
  seen = seen or {}
  if seen[value] then
    return false, { kind = "validation", message = "metadata value must not contain cycles" }
  end
  seen[value] = true
  local size = 2
  for key, item in pairs(value) do
    local key_type = type(key)
    if key_type ~= "string" and key_type ~= "number" then
      return false, { kind = "validation", message = "metadata table keys must be strings or numbers" }
    end
    local ok, nested = validate_json_value(item, seen)
    if not ok then
      return false, nested
    end
    size = size + #tostring(key) + nested
  end
  seen[value] = nil
  return true, size
end

function M.validate_value(value, max_bytes)
  local ok, size_or_err = validate_json_value(value)
  if not ok then
    return nil, size_or_err
  end
  if size_or_err > (max_bytes or 8192) then
    return nil, { kind = "validation", message = "metadata value is too large" }
  end
  return true, nil
end

function M.normalize_ref(agent_ref)
  local kind = type(agent_ref)
  if kind == "string" then
    if agent_ref == "" then
      return nil, { kind = "validation", message = "agent_ref must not be empty" }
    end
    return agent_ref, nil
  end
  if kind ~= "table" then
    return nil, { kind = "validation", message = "agent_ref must be a string or table" }
  end
  if agent_ref.target_address and agent_ref.target_address ~= "" then
    return agent_ref.target_address, nil
  end
  local local_part = agent_ref.agent_id or agent_ref.uuid or agent_ref.id or agent_ref.agent_name or agent_ref.name
  if agent_ref.host and local_part then
    return tostring(agent_ref.host) .. "/" .. tostring(local_part), nil
  end
  if local_part then
    return tostring(local_part), nil
  end
  return nil, { kind = "validation", message = "structured agent_ref needs target_address, id, uuid, agent_id, agent_name, or name" }
end

function M.validate_namespace(namespace, opts)
  opts = opts or {}
  if type(namespace) ~= "string" or namespace == "" then
    return nil, { kind = "validation", message = "metadata namespace must be a non-empty string" }
  end
  if RESERVED_NAMESPACES[namespace] and not opts.trusted then
    return nil, { kind = "permission", message = "metadata namespace is reserved: " .. namespace }
  end
  return true, nil
end

function M.default_plugin_namespace(plugin_name)
  return "plugin." .. tostring(plugin_name)
end

function M.merge_values(existing, value)
  if type(existing) ~= "table" or type(value) ~= "table" then
    return value
  end
  local out = shallow_copy(existing)
  for key, item in pairs(value) do
    out[key] = item
  end
  return out
end

return M
