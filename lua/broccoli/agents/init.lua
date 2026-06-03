local metadata = require("broccoli.agents.metadata")
local query = require("broccoli.agents.query")

local M = {}
local Agents = {}
Agents.__index = Agents

local function now_ms()
  return math.floor(os.time() * 1000)
end

local function iso_from_ms(ms)
  return os.date("!%Y-%m-%dT%H:%M:%SZ", math.floor(ms / 1000))
end

local function ensure_agent(memory, agent_key)
  memory[agent_key] = memory[agent_key] or {}
  return memory[agent_key]
end

local function ensure_namespace(memory, agent_key, namespace)
  local agent = ensure_agent(memory, agent_key)
  agent[namespace] = agent[namespace] or {}
  return agent[namespace]
end

local function is_expired(row, current_ms)
  return row and row.expires_at_ms and row.expires_at_ms <= current_ms
end

local function row_value(row)
  if not row then
    return nil
  end
  return row.value
end

local function include_row(row, opts, current_ms)
  opts = opts or {}
  if not row then
    return false
  end
  if is_expired(row, current_ms) and not opts.include_expired_metadata then
    return false
  end
  if opts.namespace and row.namespace ~= opts.namespace then
    return false
  end
  if opts.metadata_namespaces then
    local ok = false
    for _, namespace in ipairs(opts.metadata_namespaces) do
      if namespace == row.namespace then
        ok = true
        break
      end
    end
    if not ok then
      return false
    end
  end
  if opts.metadata_prefix and row.namespace:sub(1, #opts.metadata_prefix) ~= opts.metadata_prefix then
    return false
  end
  if opts.metadata_visibility and row.visibility ~= opts.metadata_visibility then
    return false
  end
  return true
end

function M.new(api, opts)
  opts = opts or {}
  return setmetatable({
    api = api,
    memory = {},
    trusted = opts.trusted == true,
    now_ms = opts.now_ms or now_ms,
  }, Agents)
end

function Agents:agent_key(agent_ref)
  return metadata.normalize_ref(agent_ref)
end

function Agents:set_metadata(agent_ref, namespace, key, value, opts)
  opts = opts or {}
  local agent_key, err = self:agent_key(agent_ref)
  if not agent_key then
    return nil, err
  end
  local ok
  ok, err = metadata.validate_namespace(namespace, { trusted = opts.trusted or self.trusted })
  if not ok then
    return nil, err
  end
  if type(key) ~= "string" or key == "" then
    return nil, { kind = "validation", message = "metadata key must be a non-empty string" }
  end
  ok, err = metadata.validate_value(value, opts.max_bytes)
  if not ok then
    return nil, err
  end

  if opts.merge then
    local existing = self:get_metadata(agent_ref, namespace, key, { include_expired_metadata = true })
    value = metadata.merge_values(existing, value)
  end

  local current_ms = self.now_ms()
  local expires_at_ms = opts.ttl_ms and (current_ms + opts.ttl_ms) or nil
  local row = {
    agent_key = agent_key,
    namespace = namespace,
    key = key,
    value = value,
    owner_plugin = opts.owner_plugin,
    persist = opts.persist ~= false,
    visibility = opts.visibility or "private",
    created_at_ms = current_ms,
    updated_at_ms = current_ms,
    expires_at_ms = expires_at_ms,
  }

  if self.api.storage and row.persist then
    return self.api.storage:set_agent_metadata(agent_key, namespace, key, value, {
      owner_plugin = row.owner_plugin,
      persist = true,
      visibility = row.visibility,
      expires_at = expires_at_ms and iso_from_ms(expires_at_ms) or nil,
    })
  end

  ensure_namespace(self.memory, agent_key, namespace)[key] = row
  return true, nil
end

function Agents:get_metadata(agent_ref, namespace, key, opts)
  opts = opts or {}
  local agent_key, err = self:agent_key(agent_ref)
  if not agent_key then
    return nil, err
  end
  if namespace ~= nil then
    local ok
    ok, err = metadata.validate_namespace(namespace, { trusted = opts.trusted or self.trusted })
    if not ok then
      return nil, err
    end
  end

  if self.api.storage and opts.persist ~= false then
    if key == nil then
      local rows
      rows, err = self.api.storage:list_agent_metadata(agent_key, { namespace = namespace, now = iso_from_ms(self.now_ms()), include_expired_metadata = opts.include_expired_metadata })
      if err then
        return nil, err
      end
      local values = {}
      for _, row in ipairs(rows or {}) do
        values[row.key] = row.value
      end
      return values, nil
    end
    return self.api.storage:get_agent_metadata(agent_key, namespace, key, { now = iso_from_ms(self.now_ms()), include_expired_metadata = opts.include_expired_metadata })
  end

  local current_ms = self.now_ms()
  local agent = self.memory[agent_key] or {}
  if key ~= nil then
    return row_value((include_row(agent[namespace] and agent[namespace][key], opts, current_ms) and agent[namespace][key]) or nil), nil
  end
  local values = {}
  local namespaces = namespace and { namespace } or nil
  for ns, rows in pairs(agent) do
    if not namespaces or ns == namespace then
      for row_key, row in pairs(rows) do
        if include_row(row, opts, current_ms) then
          values[row_key] = row.value
        end
      end
    end
  end
  return values, nil
end

function Agents:clear_metadata(agent_ref, namespace, key, opts)
  opts = opts or {}
  local agent_key, err = self:agent_key(agent_ref)
  if not agent_key then
    return nil, err
  end
  local ok
  ok, err = metadata.validate_namespace(namespace, { trusted = opts.trusted or self.trusted })
  if not ok then
    return nil, err
  end
  if self.api.storage and opts.persist ~= false then
    return self.api.storage:clear_agent_metadata(agent_key, namespace, key)
  end
  local agent = self.memory[agent_key]
  if not agent or not agent[namespace] then
    return true, nil
  end
  if key then
    agent[namespace][key] = nil
  else
    agent[namespace] = nil
  end
  return true, nil
end

function Agents:collect_metadata(agent_ref, opts)
  opts = opts or {}
  local agent_key, err = self:agent_key(agent_ref)
  if not agent_key then
    return nil, err
  end
  local current_ms = self.now_ms()
  local rows = {}

  if self.api.storage and opts.persist ~= false then
    local stored
    stored, err = self.api.storage:list_agent_metadata(agent_key, {
      namespace = opts.namespace,
      now = iso_from_ms(current_ms),
      include_expired_metadata = opts.include_expired_metadata,
    })
    if err then
      return nil, err
    end
    for _, row in ipairs(stored or {}) do
      if include_row(row, opts, current_ms) then
        rows[#rows + 1] = row
      end
    end
  end

  if opts.persist ~= true then
    for _, namespace_rows in pairs(self.memory[agent_key] or {}) do
      for _, row in pairs(namespace_rows) do
        if include_row(row, opts, current_ms) then
          rows[#rows + 1] = {
            agent_key = row.agent_key,
            namespace = row.namespace,
            key = row.key,
            value = row.value,
            owner_plugin = row.owner_plugin,
            persist = row.persist,
            visibility = row.visibility,
            expires_at_ms = row.expires_at_ms,
          }
        end
      end
    end
  end

  return rows, nil
end

function Agents:list_metadata(agent_ref, opts)
  return self:collect_metadata(agent_ref, opts)
end

function Agents:collect_metadata_for_refs(refs, opts)
  local out = {}
  local seen = {}
  local err
  for _, ref in ipairs(refs or {}) do
    local rows
    rows, err = self:collect_metadata(ref, opts)
    if err then
      return nil, err
    end
    for _, row in ipairs(rows or {}) do
      local key = tostring(row.agent_key) .. "\0" .. tostring(row.namespace) .. "\0" .. tostring(row.key)
      if not seen[key] then
        seen[key] = true
        out[#out + 1] = row
      end
    end
  end
  return out, nil
end

function Agents:list(opts)
  opts = opts or {}
  local rows, err = self.api.tracker.list(opts)
  if err then
    return nil, err
  end
  if not opts.include_metadata then
    return query.snapshot(rows), nil
  end

  local out = {}
  for name, row in pairs(rows or {}) do
    local metadata_rows
    metadata_rows, err = self:collect_metadata_for_refs(query.agent_refs(row, name), opts)
    if err then
      return nil, err
    end
    out[name] = query.with_metadata(row, metadata_rows)
  end
  return out, nil
end

function Agents:get(agent_ref, opts)
  opts = opts or {}
  local agent_key, err = self:agent_key(agent_ref)
  if not agent_key then
    return nil, err
  end
  local rows
  rows, err = self.api.tracker.list(opts)
  if err then
    return nil, err
  end
  for name, row in pairs(rows or {}) do
    if query.matches_ref(row, name, agent_key) then
      if not opts.include_metadata then
        return query.snapshot(row), nil
      end
      local metadata_rows
      metadata_rows, err = self:collect_metadata_for_refs(query.agent_refs(row, name), opts)
      if err then
        return nil, err
      end
      return query.with_metadata(row, metadata_rows), nil
    end
  end
  return nil, nil
end

M.metadata = metadata
M.query = query

return M
