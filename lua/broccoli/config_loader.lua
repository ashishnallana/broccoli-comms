local M = {}

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
  local broccoli_config = getenv(opts.env, "BROCCOLI_CONFIG")
  if broccoli_config and broccoli_config ~= "" then
    return broccoli_config
  end
  local config_home = getenv(opts.env, "XDG_CONFIG_HOME")
  if config_home and config_home ~= "" then
    return config_home .. "/broccoli-comms/init.lua"
  end
  local home = getenv(opts.env, "HOME") or "~"
  return home .. "/.config/broccoli-comms/init.lua"
end

local function trusted_env(api)
  return {
    broccoli = api,
    require = require,
    os = os,
    assert = assert,
    error = error,
    ipairs = ipairs,
    pairs = pairs,
    pcall = pcall,
    print = print,
    tonumber = tonumber,
    tostring = tostring,
    type = type,
    math = math,
    string = string,
    table = table,
  }
end

local function loadfile_with_env(path, env, loadfile_fn)
  loadfile_fn = loadfile_fn or loadfile
  if _VERSION == "Lua 5.1" then
    local chunk, err = loadfile_fn(path)
    if not chunk then
      return nil, err
    end
    if setfenv then
      setfenv(chunk, env)
    end
    return chunk, nil
  end
  return loadfile_fn(path, "t", env)
end

function M.load(path, api, opts)
  opts = opts or {}
  path = path or M.default_path(opts)

  local open = opts.open or io.open
  local file, open_err = open(path, "r")
  if not file then
    if opts.required then
      return false, { kind = "config", message = "init.lua not found", data = { path = path, cause = open_err } }
    end
    return true, nil
  end
  file:close()

  local chunk, load_err = loadfile_with_env(path, trusted_env(api), opts.loadfile)
  if not chunk then
    return false, { kind = "config", message = "failed to load init.lua", data = { path = path, cause = load_err } }
  end

  local ok, run_err = pcall(chunk)
  if not ok then
    return false, { kind = "config", message = "init.lua failed", data = { path = path, cause = run_err } }
  end
  return true, nil
end

return M
