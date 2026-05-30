#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_name="broccoli-comms"
session_name="broccoli-comms-agents"
sentinel_window="preexisting-sentinel"

tmpdir="$(mktemp -d)"
export HOME="$tmpdir/home"
export BROCCOLI_COMMS_RUNTIME_DIR="$tmpdir/runtime"
export BROCCOLI_COMMS_CACHE_DIR="$tmpdir/cache"
export BROCCOLI_COMMS_CONFIG_DIR="$tmpdir/config"
export AGENT_TRACKER_SOCKET="$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock"
export XDG_CACHE_HOME="$BROCCOLI_COMMS_CACHE_DIR"
export AGENT_TRACKER_HTTP_PORT="0"
unset BROCCOLI_COMMS_TMUX_MODE BROCCOLI_COMMS_TMUX_SOCKET AGENT_TRACKER_TMUX_SOCKET AGENT_REGISTRIES_JSON AGENT_REGISTRY_TOKEN AGENT_TRACKER_DAEMON TMUX TMUX_PANE

nix_cmd=(nix --extra-experimental-features "nix-command flakes")

broccoli() {
  if [[ -n "${BROCCOLI_COMMS_BIN:-}" ]]; then
    "$BROCCOLI_COMMS_BIN" "$@"
  else
    "${nix_cmd[@]}" run "$repo_root#$app_name" -- "$@"
  fi
}

broccoli_timeout() {
  local seconds="$1"
  shift
  if [[ -n "${BROCCOLI_COMMS_BIN:-}" ]]; then
    timeout "$seconds" "$BROCCOLI_COMMS_BIN" "$@"
  else
    timeout "$seconds" "${nix_cmd[@]}" run "$repo_root#$app_name" -- "$@"
  fi
}

tmux_default() {
  env -u TMUX -u TMUX_PANE tmux "$@"
}

can_connect_unix() {
  python3 - "$1" <<'PY'
import socket, sys
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sock.connect(sys.argv[1])
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY
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

cleanup() {
  set +e
  broccoli stop >/dev/null 2>&1
  if tmux_default has-session -t "$session_name" >/dev/null 2>&1; then
    tmux_default kill-session -t "$session_name" >/dev/null 2>&1
  fi
  rm -rf "$tmpdir"
}
trap cleanup EXIT

if tmux_default has-session -t "$session_name" >/dev/null 2>&1; then
  echo "default tmux session $session_name already exists; refusing to run destructive smoke" >&2
  exit 2
fi

mkdir -p "$HOME" "$BROCCOLI_COMMS_RUNTIME_DIR" "$BROCCOLI_COMMS_CACHE_DIR" "$BROCCOLI_COMMS_CONFIG_DIR"

printf 'Using temp runtime: %s\n' "$tmpdir"

# Pre-create the target session with an unrelated sentinel window. Broccoli
# should reuse this session, add only its own windows, and leave the sentinel
# alive on stop.
tmux_default new-session -d -s "$session_name" -n "$sentinel_window" 'sleep 600'

broccoli start
tmux_default has-session -t "$session_name"
if ! tmux_default list-windows -t "$session_name" -F '#{window_name}' | grep -Fx "$sentinel_window" >/dev/null; then
  echo "pre-existing sentinel window was removed during start" >&2
  exit 1
fi

status_json="$(broccoli status --json)"
STATUS_JSON="$status_json" python3 <<'PY'
import json, os, sys
status = json.loads(os.environ["STATUS_JSON"])
if status.get("tmux", {}).get("mode") != "default":
    raise SystemExit("status did not report default tmux mode")
if status.get("tmux", {}).get("session") != "broccoli-comms-agents":
    raise SystemExit("status did not report new session name")
if status.get("tmux", {}).get("socket") is not None:
    raise SystemExit("default tmux mode unexpectedly reported a private socket")
if not status.get("tracker", {}).get("up") or not status.get("tmux", {}).get("up"):
    print(json.dumps(status, indent=2), file=sys.stderr)
    raise SystemExit("status did not report tracker/tmux up")
PY

# ui/open attach in the foreground; timeout is expected in non-interactive smoke
# runs. The important behavior here is that each command creates/reuses a single
# Broccoli-owned UI window in the existing session before attaching.
broccoli_timeout 4 ui || true
ui_count="$(tmux_default list-windows -t "$session_name" -F '#{@broccoli_ui_window}' | grep -Fx '1' | wc -l | tr -d ' ')"
if [[ "$ui_count" != "1" ]]; then
  echo "expected exactly one Broccoli UI window after ui, found $ui_count" >&2
  tmux_default list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_ui_window}' >&2
  exit 1
fi

broccoli_timeout 4 open || true
ui_count="$(tmux_default list-windows -t "$session_name" -F '#{@broccoli_ui_window}' | grep -Fx '1' | wc -l | tr -d ' ')"
if [[ "$ui_count" != "1" ]]; then
  echo "open created duplicate Broccoli UI windows; found $ui_count" >&2
  tmux_default list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_ui_window}' >&2
  exit 1
fi

for _ in {1..50}; do
  agents_json="$(tracker_rpc list)"
  if AGENTS_JSON="$agents_json" python3 <<'PY'
import json, os, sys
agents = json.loads(os.environ["AGENTS_JSON"] or "{}")
ui = agents.get("agent-communicator")
if not ui or not ui.get("tmux_pane"):
    raise SystemExit(1)
raise SystemExit(0)
PY
  then
    break
  fi
  sleep 0.1
done

AGENTS_JSON="$agents_json" python3 <<'PY'
import json, os, sys
agents = json.loads(os.environ["AGENTS_JSON"] or "{}")
ui = agents.get("agent-communicator")
if not ui:
    print(json.dumps(agents, indent=2), file=sys.stderr)
    raise SystemExit("agent-communicator mailbox/UI registration missing")
if ui.get("target_address") != "agent-communicator" or ui.get("name") != "agent-communicator":
    raise SystemExit(f"agent-communicator registration is not stable/shared: {ui}")
if not ui.get("tmux_pane"):
    raise SystemExit(f"agent-communicator registration does not point at the UI pane: {ui}")
local_duplicates = [name for name, info in agents.items() if name.startswith("agent-communicator-") and info.get("scope", "local") == "local"]
if local_duplicates:
    print(json.dumps(agents, indent=2), file=sys.stderr)
    raise SystemExit(f"communicator registered duplicate local names: {local_duplicates}")
PY

# attach is interactive; verify it targets the renamed session without requiring
# a real terminal by accepting either a timeout or tmux's no-terminal error.
broccoli_timeout 2 attach >/tmp/broccoli-attach.out 2>/tmp/broccoli-attach.err || true
if grep -q "broccoli-comms" /tmp/broccoli-attach.err && ! grep -q "$session_name" /tmp/broccoli-attach.err; then
  echo "attach error referenced old session name" >&2
  cat /tmp/broccoli-attach.err >&2
  exit 1
fi

broccoli stop
if ! can_connect_unix "$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock" >/dev/null 2>&1; then
  :
else
  echo "agent-tracker socket still accepts connections after stop" >&2
  exit 1
fi

if ! tmux_default has-session -t "$session_name" >/dev/null 2>&1; then
  echo "stop killed pre-existing $session_name session" >&2
  exit 1
fi
if ! tmux_default list-windows -t "$session_name" -F '#{window_name}' | grep -Fx "$sentinel_window" >/dev/null; then
  echo "stop killed pre-existing sentinel window" >&2
  exit 1
fi
if tmux_default list-windows -t "$session_name" -F '#{@broccoli_ui_window} #{@broccoli_managed_agent}' | grep -Eq '(^1| .+)'; then
  echo "stop left Broccoli-owned windows in pre-existing session" >&2
  tmux_default list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_ui_window}\t#{@broccoli_managed_agent}' >&2
  exit 1
fi

tmux_default kill-session -t "$session_name"
trap - EXIT
rm -rf "$tmpdir"

echo "default session reuse smoke test passed"
