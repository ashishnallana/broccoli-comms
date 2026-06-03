local M = {}

function M.env(api)
  return {
    broccoli = api,
    assert = assert,
    error = error,
    ipairs = ipairs,
    pairs = pairs,
    pcall = pcall,
    tonumber = tonumber,
    tostring = tostring,
    type = type,
    math = math,
    string = string,
    table = table,
  }
end

function M.loadfile(path, api)
  if _VERSION == "Lua 5.1" then
    local chunk, err = loadfile(path)
    if not chunk then
      return nil, err
    end
    if setfenv then
      setfenv(chunk, M.env(api))
    end
    return chunk, nil
  end
  return loadfile(path, "t", M.env(api))
end

return M
