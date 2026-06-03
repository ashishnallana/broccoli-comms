local M = {}

M.tracker = require("broccoli.tracker")

function M.new_tracker(opts)
  return M.tracker.new(opts)
end

function M.new(opts)
  return M.new_tracker(opts)
end

return M
