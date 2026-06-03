local M = {}
local Registry = {}
Registry.__index = Registry

local function copy_command(command)
  return {
    name = command.name,
    description = command.description,
    owner_plugin = command.owner_plugin,
  }
end

function M.new()
  return setmetatable({ commands = {}, order = {} }, Registry)
end

function Registry:create(name, spec)
  spec = spec or {}
  if type(name) ~= "string" or name == "" then
    return nil, { kind = "validation", message = "command name must be a non-empty string" }
  end
  if self.commands[name] then
    return nil, { kind = "validation", message = "command already exists: " .. name }
  end
  local command = {
    name = name,
    description = spec.description,
    handler = spec.handler,
    owner_plugin = spec.owner_plugin,
  }
  self.commands[name] = command
  self.order[#self.order + 1] = name
  return copy_command(command), nil
end

function Registry:delete(name)
  if not self.commands[name] then
    return true, nil
  end
  self.commands[name] = nil
  for index, value in ipairs(self.order) do
    if value == name then
      table.remove(self.order, index)
      break
    end
  end
  return true, nil
end

function Registry:list(opts)
  opts = opts or {}
  local rows = {}
  for _, name in ipairs(self.order) do
    local command = self.commands[name]
    if command and (not opts.owner_plugin or command.owner_plugin == opts.owner_plugin) then
      rows[#rows + 1] = copy_command(command)
    end
  end
  return rows, nil
end

function Registry:clear_owner(owner_plugin)
  if not owner_plugin then
    return true, nil
  end
  local names = {}
  for name, command in pairs(self.commands) do
    if command.owner_plugin == owner_plugin then
      names[#names + 1] = name
    end
  end
  for _, name in ipairs(names) do
    self:delete(name)
  end
  return true, nil
end

return M
