local lifecycle = require("broccoli.plugins.lifecycle")

local M = {}
local Registry = {}
Registry.__index = Registry

local function name_from_source(source)
  local name = tostring(source):gsub("%.lua$", "")
  name = name:match("([^/]+)$") or name
  return name
end

function M.new(api)
  return setmetatable({ api = api, specs = {}, instances = {}, statuses = {}, generation = 0 }, Registry)
end

function Registry:use(source, spec)
  spec = spec or {}
  local name = spec.name or name_from_source(source)
  local entry = {
    name = name,
    source = source,
    opts = spec.opts or {},
    enabled = spec.enabled ~= false,
    permissions = spec.permissions or {},
    requires = spec.requires or {},
    after = spec.after or {},
    order = #self.specs + 1,
  }
  self.specs[#self.specs + 1] = entry
  self.statuses[name] = { name = name, status = entry.enabled and "registered" or "disabled" }
  return entry
end

function Registry:find_spec(name)
  for _, spec in ipairs(self.specs) do
    if spec.name == name then
      return spec
    end
  end
  return nil
end

function Registry:mark_error(spec, message)
  self.statuses[spec.name] = { name = spec.name, status = "error", error = message }
end

function Registry:can_load(spec, pending)
  for _, dependency in ipairs(spec.requires or {}) do
    if not self.instances[dependency] then
      if not self:find_spec(dependency) then
        return false, "missing required plugin: " .. dependency
      end
      return false, nil
    end
  end
  for _, after in ipairs(spec.after or {}) do
    if pending[after] then
      return false, nil
    end
  end
  return true, nil
end

function Registry:load_one(spec)
  if not spec.enabled then
    self.statuses[spec.name] = { name = spec.name, status = "disabled" }
    return true
  end
  spec.generation = self.generation
  local ok, instance, err = pcall(lifecycle.setup, spec, self.api)
  if not ok then
    self:mark_error(spec, tostring(instance))
    return false
  end
  if not instance then
    self:mark_error(spec, err and err.message or "plugin failed to load")
    return false
  end
  self.instances[spec.name] = instance
  self.statuses[spec.name] = { name = spec.name, status = "loaded" }
  return true
end

function Registry:load_all()
  self.generation = self.generation + 1
  local pending = {}
  for _, spec in ipairs(self.specs) do
    if spec.enabled then
      pending[spec.name] = spec
    else
      self.statuses[spec.name] = { name = spec.name, status = "disabled" }
    end
  end

  while true do
    local progressed = false
    for _, spec in ipairs(self.specs) do
      if pending[spec.name] then
        local can_load, dependency_error = self:can_load(spec, pending)
        if dependency_error then
          self:mark_error(spec, dependency_error)
          pending[spec.name] = nil
          progressed = true
        elseif can_load then
          self:load_one(spec)
          pending[spec.name] = nil
          progressed = true
        end
      end
    end
    if not progressed then
      break
    end
  end

  for name, spec in pairs(pending) do
    self:mark_error(spec, "dependency cycle or ordering constraint could not be resolved")
    pending[name] = nil
  end

  return self:list()
end

function Registry:disable(name)
  local instance = self.instances[name]
  if instance then
    lifecycle.teardown(instance)
    self.instances[name] = nil
  end
  self.statuses[name] = { name = name, status = "disabled" }
  return true
end

function Registry:reload(name)
  self:disable(name)
  local spec = self:find_spec(name)
  if not spec then
    return false, { kind = "plugin", message = "plugin not found" }
  end
  spec.enabled = true
  self:load_one(spec)
  return true, nil
end

function Registry:list()
  local rows = {}
  for _, spec in ipairs(self.specs) do
    rows[#rows + 1] = self.statuses[spec.name] or { name = spec.name, status = "registered" }
  end
  return rows
end

return M
