#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_name="broccoli-comms"
session_name="broccoli-comms"
agent_name="sleeper"

tmpdir="$(mktemp -d)"
export HOME="$tmpdir/home"
export BROCCOLI_COMMS_RUNTIME_DIR="$tmpdir/runtime"
export BROCCOLI_COMMS_CACHE_DIR="$tmpdir/cache"
export BROCCOLI_COMMS_CONFIG_DIR="$tmpdir/config"
export AGENT_TRACKER_SOCKET="$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock"
export XDG_CACHE_HOME="$BROCCOLI_COMMS_CACHE_DIR"
export AGENT_TRACKER_HTTP_PORT="0"
unset AGENT_REGISTRIES_JSON AGENT_REGISTRY_TOKEN AGENT_TRACKER_DAEMON TMUX TMUX_PANE

nix_cmd=(nix --extra-experimental-features "nix-command flakes")

broccoli() {
  if [[ -n "${BROCCOLI_COMMS_BIN:-}" ]]; then
    "$BROCCOLI_COMMS_BIN" "$@"
  else
    "${nix_cmd[@]}" run "$repo_root#$app_name" -- "$@"
  fi
}

tmux_private() {
  env -u TMUX -u TMUX_PANE tmux -S "$BROCCOLI_COMMS_RUNTIME_DIR/tmux.sock" "$@"
}

tracker_rpc() {
  python3 - "$1" "${2:-{}}" <<'PY'
import json, os, socket, sys
method = sys.argv[1]
params = json.loads(sys.argv[2])
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(os.environ["AGENT_TRACKER_SOCKET"])
s.sendall(json.dumps({"jsonrpc":"2.0","method":method,"params":params,"id":1}).encode())
s.shutdown(socket.SHUT_WR)
chunks = []
while True:
    chunk = s.recv(4096)
    if not chunk:
        break
    chunks.append(chunk)
resp = json.loads(b"".join(chunks).decode())
if "error" in resp:
    raise SystemExit(resp["error"].get("message", "tracker RPC error"))
print(json.dumps(resp.get("result")))
PY
}

wait_for_agent() {
  local name="$1"
  for _ in {1..50}; do
    if AGENTS_JSON="$(tracker_rpc list 2>/dev/null || true)" python3 - "$name" <<'PY'
import json, os, sys
name = sys.argv[1]
try:
    agents = json.loads(os.environ.get("AGENTS_JSON") or "{}")
except json.JSONDecodeError:
    raise SystemExit(1)
raise SystemExit(0 if name in agents else 1)
PY
    then
      return 0
    fi
    sleep 0.1
  done
  echo "agent $name did not register" >&2
  tracker_rpc list >&2 || true
  return 1
}

managed_windows_for() {
  local name="$1"
  tmux_private list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_managed_agent}\t#{pane_id}' \
    | awk -F '\t' -v name="$name" '$3 == name { print }'
}

managed_count() {
  managed_windows_for "$1" | wc -l | tr -d ' '
}

managed_window_id() {
  managed_windows_for "$1" | awk -F '\t' 'NR == 1 { print $1 }'
}

managed_pane_id() {
  managed_windows_for "$1" | awk -F '\t' 'NR == 1 { print $4 }'
}

cleanup() {
  set +e
  broccoli stop >/dev/null 2>&1
  rm -rf "$tmpdir"
}
trap cleanup EXIT

mkdir -p "$HOME" "$BROCCOLI_COMMS_RUNTIME_DIR" "$BROCCOLI_COMMS_CACHE_DIR" "$BROCCOLI_COMMS_CONFIG_DIR" "$tmpdir/project"

printf 'Using temp runtime: %s\n' "$tmpdir"

broccoli agent add "$agent_name" --cwd "$tmpdir/project" --command "sleep 60"

list_json="$(broccoli agent list --json)"
LIST_JSON="$list_json" python3 - "$agent_name" "$tmpdir/project" <<'PY'
import json, os, sys
payload = json.loads(os.environ["LIST_JSON"])
name, cwd = sys.argv[1:]
agent = payload["agents"].get(name)
if not agent or agent.get("cwd") != cwd or agent.get("command") != "sleep 60":
    raise SystemExit("configured agent missing from agent list")
PY

broccoli start

tmux_private has-session -t "$session_name"
if [[ "$(managed_count "$agent_name")" != "1" ]]; then
  echo "expected one managed $agent_name window after start" >&2
  tmux_private list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_managed_agent}\t#{pane_id}' >&2
  exit 1
fi
wait_for_agent "$agent_name"
first_pane="$(managed_pane_id "$agent_name")"

broccoli start
window_count="$(managed_count "$agent_name")"
if [[ "$window_count" != "1" ]]; then
  echo "expected exactly one managed agent window after repeated start, found $window_count" >&2
  exit 1
fi

broccoli agent restart "$agent_name"
if [[ "$(managed_count "$agent_name")" != "1" ]]; then
  echo "expected one managed $agent_name window after restart" >&2
  exit 1
fi
wait_for_agent "$agent_name"
second_pane="$(managed_pane_id "$agent_name")"
if [[ "$first_pane" == "$second_pane" ]]; then
  echo "restart did not create a new pane" >&2
  exit 1
fi

broccoli agent remove "$agent_name"
if [[ "$(managed_count "$agent_name")" != "0" ]]; then
  echo "managed agent window still exists after remove" >&2
  exit 1
fi
list_json="$(broccoli agent list --json)"
LIST_JSON="$list_json" python3 - "$agent_name" <<'PY'
import json, os, sys
payload = json.loads(os.environ["LIST_JSON"])
if sys.argv[1] in payload.get("agents", {}):
    raise SystemExit("removed agent still present in config")
PY

collision_agent="bash"
mkdir -p "$tmpdir/collision-project"
broccoli agent add "$collision_agent" --cwd "$tmpdir/collision-project" --command "sleep 60"
broccoli start
if [[ "$(managed_count "$collision_agent")" != "1" ]]; then
  echo "expected one managed collision window" >&2
  tmux_private list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_managed_agent}\t#{pane_id}' >&2
  exit 1
fi
bash_window_count="$(tmux_private list-windows -t "$session_name" -F '#{window_name}' | grep -Fx "$collision_agent" | wc -l | tr -d ' ')"
if [[ "$bash_window_count" -lt 2 ]]; then
  echo "expected a bare-name collision with at least two bash windows, found $bash_window_count" >&2
  tmux_private list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_managed_agent}\t#{pane_id}' >&2
  exit 1
fi
wait_for_agent "$collision_agent"
first_collision_window="$(managed_window_id "$collision_agent")"

broccoli start
if [[ "$(managed_count "$collision_agent")" != "1" ]]; then
  echo "repeated start created duplicate managed collision windows" >&2
  exit 1
fi

broccoli agent restart "$collision_agent"
if [[ "$(managed_count "$collision_agent")" != "1" ]]; then
  echo "restart did not leave exactly one managed collision window" >&2
  exit 1
fi
second_collision_window="$(managed_window_id "$collision_agent")"
if [[ "$first_collision_window" == "$second_collision_window" ]]; then
  echo "collision restart did not create a new managed window" >&2
  exit 1
fi

broccoli agent remove "$collision_agent"
if [[ "$(managed_count "$collision_agent")" != "0" ]]; then
  echo "managed collision window still exists after remove" >&2
  exit 1
fi
bash_window_count="$(tmux_private list-windows -t "$session_name" -F '#{window_name}' | grep -Fx "$collision_agent" | wc -l | tr -d ' ')"
if [[ "$bash_window_count" -lt 1 ]]; then
  echo "remove killed the non-managed bash window" >&2
  exit 1
fi

broccoli stop

trap - EXIT
rm -rf "$tmpdir"

echo "managed agent smoke test passed"
