local tracker_module = require("broccoli.tracker")
local config_loader = require("broccoli.config_loader")
local plugin_registry = require("broccoli.plugins.registry")
local storage = require("broccoli.storage")
local agents_module = require("broccoli.agents")

local M = {}

M.tracker = {}
M.config_loader = config_loader
M.storage_module = storage
M._generation = 0
M._config = { tracker = {} }
M.storage = nil
M._agents = agents_module.new(M, { trusted = true })
M.agents = {
  set_metadata = function(...) return M._agents:set_metadata(...) end,
  get_metadata = function(...) return M._agents:get_metadata(...) end,
  clear_metadata = function(...) return M._agents:clear_metadata(...) end,
  list_metadata = function(...) return M._agents:list_metadata(...) end,
  agent_key = function(...) return M._agents:agent_key(...) end,
  reset_memory = function() M._agents.memory = {} end,
}
M.plugins = plugin_registry.new(M)

local function merge(base, override)
  local out = {}
  for key, value in pairs(base or {}) do
    out[key] = value
  end
  for key, value in pairs(override or {}) do
    out[key] = value
  end
  return out
end

function M.setup(opts)
  opts = opts or {}
  M._config = {
    tracker = merge({}, opts.tracker or {}),
    storage = merge({}, opts.storage or {}),
  }
  M.storage = opts.storage and storage.new(opts.storage) or nil
  M._generation = M._generation + 1
  return true
end

function M.config()
  return M._config
end

function M.generation()
  return M._generation
end

function M.new_tracker(opts)
  return tracker_module.new(merge(M._config.tracker, opts or {}))
end

function M.new(opts)
  return M.new_tracker(opts)
end

function M.tracker.new(opts)
  return M.new_tracker(opts)
end

function M.tracker.list(opts)
  return M.new_tracker():list(opts)
end

function M.tracker.send_message(opts)
  return M.new_tracker():send_message(opts)
end

function M.tracker.read_inbox(opts)
  return M.new_tracker():read_inbox(opts)
end

function M.reset_plugins()
  M.plugins = plugin_registry.new(M)
  return M.plugins
end

function M.load_init(opts)
  opts = opts or {}
  local before = M._generation
  local ok, err = M.config_loader.load(opts.path, M, opts)
  if ok and M._generation == before then
    M._generation = M._generation + 1
  end
  return ok, err
end

return M
