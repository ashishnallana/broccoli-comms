#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: agent-wrapper <command> [args...]" >&2
  exit 2
fi

cmd="$1"
shift

obs_enabled=false
no_notify_with_send_keys=false
no_registry=false
args=()
for arg in "$@"; do
  case "$arg" in
    --obs) obs_enabled=true ;;
    --no-notify-with-send-keys) no_notify_with_send_keys=true ;;
    --no-registry) no_registry=true ;;
    *) args+=("$arg") ;;
  esac
done
set -- "${args[@]}"
# Keep --obs accepted for parity with the Home Manager wrapper. The standalone
# wrapper does not open observer panes yet.
if [[ "$obs_enabled" == "true" ]]; then
  :
fi

if [[ -z "${TMUX:-}" ]]; then
  exec "$cmd" "$@"
fi

pane_id="${TMUX_PANE:-}"
if [[ -z "$pane_id" ]]; then
  exec "$cmd" "$@"
fi

export AGENT_TRACKER_SOCKET="${AGENT_TRACKER_SOCKET:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/broccoli-comms/agent-tracker.sock}"
if command -v agent-tracker-ctl >/dev/null 2>&1; then
  agent-tracker-ctl ensure-running >/dev/null 2>&1 || true
fi

session_name=$(tmux display-message -p -t "$pane_id" '#S' 2>/dev/null || echo broccoli-comms)
tmux_socket="${TMUX%%,*}"
wrapper_pid="$$"
suggested_name="${SUGGESTED_AGENT_NAME:-}"
agent_type=$(basename "$cmd")
agent_cmd=$(basename "$cmd")
agent_id="${AGENT_ID:-$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}"
export AGENT_ID="$agent_id"
current_cwd=$(tmux display-message -p -t "$pane_id" '#{pane_current_path}' 2>/dev/null || pwd)

rpc_register() {
  python3 - "$session_name" "$pane_id" "$wrapper_pid" "$tmux_socket" "$suggested_name" "$agent_type" "$agent_cmd" "$agent_id" "$no_notify_with_send_keys" "$no_registry" "$current_cwd" <<'PY'
import json, os, socket, sys
session, pane, wrapper_pid, tmux_socket, name, agent_type, agent_cmd, agent_id, no_notify, no_registry, cwd = sys.argv[1:]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(3)
s.connect(os.environ["AGENT_TRACKER_SOCKET"])
req = {
  "jsonrpc": "2.0",
  "method": "register",
  "params": {
    "session": session,
    "tmux_pane": pane,
    "wrapper_pid": int(wrapper_pid),
    "tmux_socket": tmux_socket,
    "name": name,
    "agent_type": agent_type,
    "agent_cmd": agent_cmd,
    "agent_id": agent_id,
    "no_notify_with_send_keys": no_notify.lower() == "true",
    "no_registry": no_registry.lower() == "true",
    "cwd": cwd,
  },
  "id": 1,
}
s.sendall(json.dumps(req).encode())
s.shutdown(socket.SHUT_WR)
data = json.loads(s.recv(4096).decode())
if data.get("error"):
  raise SystemExit(data["error"].get("message", "register failed"))
print(data.get("result", ""))
PY
}

agent_name=""
if agent_name=$(rpc_register 2>/tmp/broccoli-comms-agent-wrapper.log); then
  :
else
  agent_name="${suggested_name:-$agent_cmd}"
fi

if [[ -n "$agent_name" ]]; then
  export AGENT_NAME="$agent_name"
  tmux set-option -p -t "$pane_id" @agent_name "$agent_name" 2>/dev/null || true
  tmux set-option -p -t "$pane_id" @agent_id "$agent_id" 2>/dev/null || true
  tmux set-option -p -t "$pane_id" @agent_uuid "$agent_id" 2>/dev/null || true
  tmux set-option -p -t "$pane_id" @agent_type "$agent_type" 2>/dev/null || true
  tmux set-option -p -t "$pane_id" @agent_cmd "$agent_cmd" 2>/dev/null || true
  tmux select-pane -t "$pane_id" -T "$agent_name" 2>/dev/null || true
fi

heartbeat() {
  while true; do
    current_cwd=$(tmux display-message -p -t "$pane_id" '#{pane_current_path}' 2>/dev/null || pwd)
    python3 - "$agent_id" "$wrapper_pid" "$current_cwd" <<'PY' >/dev/null 2>>/tmp/broccoli-comms-agent-wrapper.log || true
import json, os, socket, sys
agent_id, wrapper_pid, cwd = sys.argv[1:]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(os.environ["AGENT_TRACKER_SOCKET"])
s.sendall(json.dumps({"jsonrpc":"2.0","method":"heartbeat","params":{"agent_id":agent_id,"wrapper_pid":int(wrapper_pid),"cwd":cwd},"id":1}).encode())
s.shutdown(socket.SHUT_WR)
s.recv(1024)
PY
    sleep 5
  done
}
heartbeat &
heartbeat_pid=$!

cleanup() {
  kill "$heartbeat_pid" >/dev/null 2>&1 || true
  if command -v agent-tracker-ctl >/dev/null 2>&1; then
    agent-tracker-ctl unregister --pane "$pane_id" >/dev/null 2>&1 || true
  fi
  tmux set-option -p -u -t "$pane_id" @agent_name 2>/dev/null || true
  tmux set-option -p -u -t "$pane_id" @agent_id 2>/dev/null || true
  tmux select-pane -t "$pane_id" -T "" 2>/dev/null || true
}
trap cleanup EXIT

exec "$cmd" "$@"
