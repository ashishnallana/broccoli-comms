local migrations = require("broccoli.storage.migrations")
local sqlite = require("broccoli.storage.sqlite")

local M = {}
local Store = {}
Store.__index = Store

local function getenv(env, name)
  if env and env[name] ~= nil then
    return env[name]
  end
  return os.getenv(name)
end

function M.default_path(opts)
  opts = opts or {}
  if opts.path and opts.path ~= "" then
    return opts.path
  end
  local explicit = getenv(opts.env, "BROCCOLI_PLUGIN_STATE_DB")
  if explicit and explicit ~= "" then
    return explicit
  end
  local state_home = getenv(opts.env, "XDG_STATE_HOME")
  if state_home and state_home ~= "" then
    return state_home .. "/broccoli-comms/plugin-state.sqlite3"
  end
  local home = getenv(opts.env, "HOME") or "~"
  return home .. "/.local/state/broccoli-comms/plugin-state.sqlite3"
end

function M.new(opts)
  opts = opts or {}
  local path = M.default_path(opts)
  return setmetatable({
    path = path,
    db = opts.db or sqlite.new({ path = path, adapter = opts.adapter }),
    json = opts.json,
    now = opts.now or function() return os.date("!%Y-%m-%dT%H:%M:%SZ") end,
  }, Store)
end

function Store:migrate()
  for version, sql in ipairs(migrations.statements) do
    local ok, err = self.db:exec(sql, {})
    if not ok then
      return nil, err
    end
    ok, err = self.db:exec("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)", { version, self.now() })
    if not ok then
      return nil, err
    end
  end
  return true, nil
end

function Store:encode(value)
  if self.json and self.json.encode then
    return self.json.encode(value)
  end
  if type(value) == "string" then
    return value
  end
  return tostring(value)
end

function Store:decode(value)
  if self.json and self.json.decode then
    return self.json.decode(value)
  end
  return value
end

function Store:set_plugin_state(plugin_name, key, value)
  return self.db:exec(
    "INSERT OR REPLACE INTO plugin_state(plugin_name, key, value_json, updated_at) VALUES (?, ?, ?, ?)",
    { plugin_name, key, self:encode(value), self.now() }
  )
end

function Store:get_plugin_state(plugin_name, key)
  local rows, err = self.db:query("SELECT value_json FROM plugin_state WHERE plugin_name = ? AND key = ?", { plugin_name, key })
  if err then
    return nil, err
  end
  if not rows or not rows[1] then
    return nil, nil
  end
  return self:decode(rows[1].value_json), nil
end

function Store:clear_plugin_state(plugin_name, key)
  return self.db:exec("DELETE FROM plugin_state WHERE plugin_name = ? AND key = ?", { plugin_name, key })
end

function Store:set_agent_metadata(agent_key, namespace, key, value, opts)
  opts = opts or {}
  local now = self.now()
  return self.db:exec(
    "INSERT OR REPLACE INTO agent_metadata(agent_key, namespace, key, value_json, owner_plugin, persist, visibility, created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM agent_metadata WHERE agent_key = ? AND namespace = ? AND key = ?), ?), ?, ?)",
    { agent_key, namespace, key, self:encode(value), opts.owner_plugin, opts.persist == false and 0 or 1, opts.visibility or "private", agent_key, namespace, key, now, now, opts.expires_at }
  )
end

function Store:get_agent_metadata(agent_key, namespace, key, opts)
  opts = opts or {}
  local sql = "SELECT value_json FROM agent_metadata WHERE agent_key = ? AND namespace = ? AND key = ?"
  local params = { agent_key, namespace, key }
  if not opts.include_expired_metadata then
    sql = sql .. " AND (expires_at IS NULL OR expires_at > ?)"
    params[#params + 1] = opts.now or self.now()
  end
  local rows, err = self.db:query(sql, params)
  if err then
    return nil, err
  end
  if not rows or not rows[1] then
    return nil, nil
  end
  return self:decode(rows[1].value_json), nil
end

function Store:list_agent_metadata(agent_key, opts)
  opts = opts or {}
  local sql = "SELECT agent_key, namespace, key, value_json, owner_plugin, persist, visibility, expires_at FROM agent_metadata WHERE agent_key = ?"
  local params = { agent_key }
  if opts.namespace then
    sql = sql .. " AND namespace = ?"
    params[#params + 1] = opts.namespace
  end
  if not opts.include_expired_metadata then
    sql = sql .. " AND (expires_at IS NULL OR expires_at > ?)"
    params[#params + 1] = opts.now or self.now()
  end
  local rows, err = self.db:query(sql, params)
  if err then
    return nil, err
  end
  local out = {}
  for _, row in ipairs(rows or {}) do
    out[#out + 1] = {
      agent_key = row.agent_key,
      namespace = row.namespace,
      key = row.key,
      value = self:decode(row.value_json),
      owner_plugin = row.owner_plugin,
      persist = row.persist ~= 0,
      visibility = row.visibility or "private",
      expires_at = row.expires_at,
    }
  end
  return out, nil
end

function Store:clear_agent_metadata(agent_key, namespace, key)
  if key then
    return self.db:exec("DELETE FROM agent_metadata WHERE agent_key = ? AND namespace = ? AND key = ?", { agent_key, namespace, key })
  end
  return self.db:exec("DELETE FROM agent_metadata WHERE agent_key = ? AND namespace = ?", { agent_key, namespace })
end

function Store:record_plugin_error(plugin_name, phase, message, details)
  return self.db:exec(
    "INSERT INTO plugin_errors(plugin_name, phase, message, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
    { plugin_name, phase, message, details and self:encode(details) or nil, self.now() }
  )
end

function Store:cleanup_expired_metadata(now)
  return self.db:exec(migrations.cleanup_expired_metadata_sql, { now or self.now() })
end

M.migrations = migrations

return M
