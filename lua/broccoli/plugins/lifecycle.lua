local capabilities = require("broccoli.plugins.capabilities")
local sandbox = require("broccoli.plugins.sandbox")

local M = {}

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

local function is_path(name)
  return name:find("/", 1, true) or name:sub(-4) == ".lua"
end

function M.load_module(spec, scoped_api)
  if is_path(spec.source) then
    local chunk, err = sandbox.loadfile(spec.source, scoped_api)
    if not chunk then
      return nil, err
    end
    return chunk()
  end
  return require(spec.source)
end

function M.setup(spec, api)
  local scoped = capabilities.scoped_api(api, spec.name, spec.permissions)
  local module, load_err = M.load_module(spec, scoped)
  if type(module) ~= "table" then
    return nil, { kind = "plugin", message = "plugin did not return a table", data = { cause = load_err } }
  end
  local opts = merge(module.defaults, spec.opts)
  local instance = {
    name = spec.name,
    source = spec.source,
    module = module,
    opts = opts,
    state = {},
    status = "loaded",
  }
  local ctx = {
    plugin = { name = spec.name, version = module.meta and module.meta.version, generation = spec.generation or 1 },
    opts = opts,
    state = instance.state,
    broccoli = scoped,
  }
  instance.ctx = ctx
  if type(module.setup) == "function" then
    local ok, err = pcall(module.setup, ctx, opts)
    if not ok then
      return nil, { kind = "plugin", message = "plugin setup failed", data = { cause = err } }
    end
  end
  return instance, nil
end

function M.teardown(instance)
  if instance and instance.module and type(instance.module.teardown) == "function" then
    return pcall(instance.module.teardown, instance.ctx)
  end
  return true, nil
end

return M
