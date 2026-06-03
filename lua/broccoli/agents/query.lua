local M = {}

local function deep_copy(value, seen)
  if type(value) ~= "table" then
    return value
  end
  seen = seen or {}
  if seen[value] then
    return seen[value]
  end
  local out = {}
  seen[value] = out
  for key, item in pairs(value) do
    out[deep_copy(key, seen)] = deep_copy(item, seen)
  end
  return out
end

function M.agent_ref(row, fallback_name)
  if type(row) ~= "table" then
    return fallback_name
  end
  return row.target_address or row.agent_id or row.uuid or row.id or row.agent_name or row.name or fallback_name
end

function M.agent_refs(row, fallback_name)
  local refs = {}
  local seen = {}
  local function add(value)
    if value ~= nil and value ~= "" and not seen[value] then
      seen[value] = true
      refs[#refs + 1] = value
    end
  end

  add(fallback_name)
  if type(row) == "table" then
    add(row.name)
    add(row.agent_name)
    add(row.agent_id)
    add(row.uuid)
    add(row.id)
    add(row.target_address)
    if row.host and (row.name or row.agent_name) then
      add(tostring(row.host) .. "/" .. tostring(row.name or row.agent_name))
    end
  end
  return refs
end

function M.matches_ref(row, fallback_name, agent_key)
  if fallback_name == agent_key then
    return true
  end
  if type(row) ~= "table" then
    return false
  end
  for _, key in ipairs({ "target_address", "agent_id", "uuid", "id", "agent_name", "name" }) do
    if row[key] == agent_key then
      return true
    end
  end
  if row.host and (row.name or row.agent_name) then
    local name = row.name or row.agent_name
    if tostring(row.host) .. "/" .. tostring(name) == agent_key then
      return true
    end
  end
  return false
end

function M.metadata_map(rows)
  local out = {}
  for _, row in ipairs(rows or {}) do
    out[row.namespace] = out[row.namespace] or {}
    out[row.namespace][row.key] = deep_copy(row.value)
  end
  return out
end

function M.with_metadata(row, rows)
  local copy = deep_copy(row)
  copy.metadata = M.metadata_map(rows)
  return copy
end

function M.snapshot(value)
  return deep_copy(value)
end

return M
