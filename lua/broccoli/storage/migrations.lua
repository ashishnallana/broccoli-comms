local M = {}

M.statements = {
  [[CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
)]],
  [[CREATE TABLE IF NOT EXISTS agent_metadata (
  agent_key TEXT NOT NULL,
  namespace TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  owner_plugin TEXT,
  persist INTEGER NOT NULL DEFAULT 1,
  visibility TEXT NOT NULL DEFAULT 'private',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT,
  PRIMARY KEY(agent_key, namespace, key)
)]],
  [[CREATE INDEX IF NOT EXISTS idx_agent_metadata_agent_key
  ON agent_metadata(agent_key)]],
  [[CREATE INDEX IF NOT EXISTS idx_agent_metadata_expires_at
  ON agent_metadata(expires_at)]],
  [[CREATE TABLE IF NOT EXISTS plugin_state (
  plugin_name TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(plugin_name, key)
)]],
  [[CREATE TABLE IF NOT EXISTS plugin_errors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plugin_name TEXT NOT NULL,
  phase TEXT NOT NULL,
  message TEXT NOT NULL,
  details_json TEXT,
  created_at TEXT NOT NULL
)]],
}

M.cleanup_expired_metadata_sql = "DELETE FROM agent_metadata WHERE expires_at IS NOT NULL AND expires_at <= ?"

return M
