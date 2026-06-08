#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_name="broccoli-comms"
session_name="broccoli-comms-agents"
agent_name="sleeper"
manual_agent="manual"
wrapped_agent="wrapped-pi"

tmpdir="$(mktemp -d)"
export HOME="$tmpdir/home"
export BROCCOLI_COMMS_RUNTIME_DIR="$tmpdir/runtime"
export BROCCOLI_COMMS_CACHE_DIR="$tmpdir/cache"
export BROCCOLI_COMMS_CONFIG_DIR="$tmpdir/config"
export AGENT_TRACKER_SOCKET="$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock"
export XDG_CACHE_HOME="$BROCCOLI_COMMS_CACHE_DIR"
export AGENT_TRACKER_HTTP_PORT="0"
export BROCCOLI_COMMS_TMUX_MODE="private"
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

broccoli run "$manual_agent" --cwd "$tmpdir/project" -- sleep 60
broccoli agent edit "$manual_agent" --cwd "$tmpdir/project" --command "sleep 60" --no-autostart
list_json="$(broccoli agent list --json)"
LIST_JSON="$list_json" python3 - "$manual_agent" <<'PY'
import json, os, sys
payload = json.loads(os.environ["LIST_JSON"])
agent = payload["agents"].get(sys.argv[1])
if not agent or agent.get("autostart") is not False:
    raise SystemExit("manual agent should default to autostart=false")
PY

# Keep a managed config entry but ensure the scratch process is not running before
# validating autostart-only startup behavior.
manual_window="$(managed_window_id "$manual_agent")"
if [[ -n "$manual_window" ]]; then
  tmux_private kill-window -t "$manual_window"
  for _ in {1..20}; do
    if [[ "$(managed_count "$manual_agent")" == "0" ]]; then
      break
    fi
    sleep 0.1
  done
fi

broccoli start
if [[ "$(managed_count "$manual_agent")" != "0" ]]; then
  echo "manual/non-autostart agent launched during start" >&2
  exit 1
fi
status_json="$(broccoli status --json)"
STATUS_JSON="$status_json" python3 <<'PY'
import json, os
status = json.loads(os.environ["STATUS_JSON"])
if status.get("agents", {}).get("configured_count") != 1:
    raise SystemExit("manual configured_count mismatch")
if status.get("agents", {}).get("autostart_count") != 0:
    raise SystemExit("manual autostart_count mismatch")
if status.get("agents", {}).get("managed_running_count") != 0:
    raise SystemExit("manual managed_running_count mismatch")
PY
broccoli agent restart "$manual_agent"
if [[ "$(managed_count "$manual_agent")" != "1" ]]; then
  echo "manual agent restart did not launch exactly one window" >&2
  exit 1
fi
wait_for_agent "$manual_agent"
broccoli agent remove "$manual_agent"
if [[ "$(managed_count "$manual_agent")" != "0" ]]; then
  echo "manual agent window still exists after remove" >&2
  exit 1
fi

broccoli run "$agent_name" --cwd "$tmpdir/project" -- sleep 60
broccoli agent edit "$agent_name" --cwd "$tmpdir/project" --command "sleep 60" --autostart

doctor_json="$(broccoli doctor --json)"
DOCTOR_JSON="$doctor_json" python3 - "$agent_name" <<'PY'
import json, os, sys
name = sys.argv[1]
payload = json.loads(os.environ["DOCTOR_JSON"])
if not payload.get("ok"):
    print(json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit("doctor --json reported not ok with configured sleep agent")
checks = {check.get("name"): check for check in payload.get("checks", [])}
check = checks.get(f"agent command:{name}")
if not check or check.get("status") != "ok" or check.get("executable") != "sleep":
    print(json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit("doctor did not validate configured sleep agent command")
PY

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
first_window="$(managed_window_id "$agent_name")"

focus_json="$(broccoli agent focus "$agent_name")"
FOCUS_JSON="$focus_json" python3 - "$agent_name" "$first_window" <<'PY'
import json, os, sys
name, window_id = sys.argv[1:]
payload = json.loads(os.environ["FOCUS_JSON"])
if payload.get("focused") != name:
    raise SystemExit("focus payload name mismatch")
if payload.get("window", {}).get("window_id") != window_id:
    raise SystemExit("focus payload window_id mismatch")
PY

status_json="$(broccoli status --json)"
STATUS_JSON="$status_json" python3 <<'PY'
import json, os
status = json.loads(os.environ["STATUS_JSON"])
if status.get("agents", {}).get("configured_count") != 1:
    raise SystemExit("status configured_count mismatch")
if status.get("agents", {}).get("managed_running_count") != 1:
    raise SystemExit("status managed_running_count mismatch")
if not status.get("tracker", {}).get("up") or not status.get("tmux", {}).get("up"):
    raise SystemExit("status did not report tracker/tmux up")
PY

list_json="$(broccoli agent list --json)"
LIST_JSON="$list_json" python3 - "$agent_name" <<'PY'
import json, os, sys
name = sys.argv[1]
payload = json.loads(os.environ["LIST_JSON"])
agent = payload.get("agents", {}).get(name)
if not agent:
    raise SystemExit("agent missing from list payload")
if not agent.get("running"):
    raise SystemExit("agent list did not report running=true")
windows = agent.get("managed_windows") or []
if len(windows) != 1 or not windows[0].get("window_id") or not windows[0].get("pane_id"):
    raise SystemExit("agent list missing managed window metadata")
if not agent.get("tracker") or not agent["tracker"].get("agent_id"):
    raise SystemExit("agent list missing tracker registration info")
PY

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

fake_bin="$tmpdir/fake-bin"
mkdir -p "$fake_bin" "$tmpdir/wrapped-project"
cat > "$fake_bin/pi" <<'SH'
#!/usr/bin/env bash
exec sleep "$@"
SH
chmod +x "$fake_bin/pi"
export PATH="$fake_bin:$PATH"

# Start an agent command that routes through an installed executable name,
# then persist it as a managed agent.
broccoli run "$wrapped_agent" --cwd "$tmpdir/wrapped-project" -- pi 60
broccoli agent edit "$wrapped_agent" --cwd "$tmpdir/wrapped-project" --command "pi 60" --autostart
broccoli start
if [[ "$(managed_count "$wrapped_agent")" != "1" ]]; then
  echo "expected wrapped command to keep managed agent name" >&2
  tmux_private list-windows -t "$session_name" -F $'#{window_id}\t#{window_name}\t#{@broccoli_managed_agent}\t#{pane_id}' >&2
  exit 1
fi
wait_for_agent "$wrapped_agent"
list_json="$(broccoli agent-tracker list)"
LIST_JSON="$list_json" python3 - "$wrapped_agent" <<'PY'
import json, os, sys
payload = json.loads(os.environ["LIST_JSON"])
name = sys.argv[1]
if name not in payload:
    raise SystemExit("wrapped managed agent missing from tracker list")
PY
broccoli agent remove "$wrapped_agent"
if [[ "$(managed_count "$wrapped_agent")" != "0" ]]; then
  echo "wrapped managed agent window still exists after remove" >&2
  exit 1
fi

collision_agent="bash"
mkdir -p "$tmpdir/collision-project"
broccoli run "$collision_agent" --cwd "$tmpdir/collision-project" -- sleep 60
broccoli agent edit "$collision_agent" --cwd "$tmpdir/collision-project" --command "sleep 60" --autostart
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
