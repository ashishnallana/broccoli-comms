#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_name="broccoli-comms"
session_name="broccoli-comms-agents"

tmpdir="$(mktemp -d)"
export HOME="$tmpdir/home"
export BROCCOLI_COMMS_RUNTIME_DIR="$tmpdir/runtime"
export BROCCOLI_COMMS_CACHE_DIR="$tmpdir/cache"
export BROCCOLI_COMMS_CONFIG_DIR="$tmpdir/config"
export AGENT_TRACKER_SOCKET="$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock"
export BROCCOLI_COMMS_TMUX_MODE="private"
export XDG_CACHE_HOME="$BROCCOLI_COMMS_CACHE_DIR"
export AGENT_TRACKER_HTTP_PORT="0"
unset AGENT_REGISTRIES_JSON AGENT_REGISTRY_TOKEN AGENT_TRACKER_DAEMON

nix_cmd=(nix --extra-experimental-features "nix-command flakes")

broccoli() {
  if [[ -n "${BROCCOLI_COMMS_BIN:-}" ]]; then
    "$BROCCOLI_COMMS_BIN" "$@"
  else
    "${nix_cmd[@]}" run "$repo_root#$app_name" -- "$@"
  fi
}

tracker_ctl() {
  if [[ -n "${AGENT_TRACKER_CTL_BIN:-}" ]]; then
    "$AGENT_TRACKER_CTL_BIN" "$@"
  else
    "${nix_cmd[@]}" run "$repo_root#agent-tracker-ctl" -- "$@"
  fi
}

tmux_private() {
  env -u TMUX -u TMUX_PANE tmux -S "$BROCCOLI_COMMS_RUNTIME_DIR/tmux.sock" "$@"
}

if grep -R --exclude-dir='__pycache__' --exclude='*.pyc' "tmux-status-refresh" "$repo_root/agent-tracker" "$repo_root/app" "$repo_root/wrapper" >/dev/null 2>&1; then
  echo "unsafe tmux-status-refresh runtime call found" >&2
  exit 1
fi

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

cleanup() {
  set +e
  broccoli stop >/dev/null 2>&1
  env -u TMUX -u TMUX_PANE tmux -S "$tmpdir/inherited-default-tmux.sock" kill-server >/dev/null 2>&1
  rm -rf "$tmpdir"
}
trap cleanup EXIT

mkdir -p "$HOME" "$BROCCOLI_COMMS_RUNTIME_DIR" "$BROCCOLI_COMMS_CACHE_DIR" "$BROCCOLI_COMMS_CONFIG_DIR"

# Create an isolated sentinel tmux server and pretend the smoke test is being
# run from inside it. The private tracker must not recover this default/inherited
# tmux pane.
sentinel_socket="$tmpdir/inherited-default-tmux.sock"
sentinel_pane="$(env -u TMUX -u TMUX_PANE tmux -S "$sentinel_socket" new-session -d -P -F '#{pane_id}' -s inherited-default 'sleep 600')"
env -u TMUX -u TMUX_PANE tmux -S "$sentinel_socket" set-option -p -t "$sentinel_pane" @agent_name sentinel-default-tmux-agent
env -u TMUX -u TMUX_PANE tmux -S "$sentinel_socket" set-option -p -t "$sentinel_pane" @agent_id sentinel-default-tmux-agent-id
export TMUX="$sentinel_socket,999,0"
export TMUX_PANE="$sentinel_pane"

printf 'Using temp runtime: %s\n' "$tmpdir"

doctor_json="$(broccoli doctor --json)"
DOCTOR_JSON="$doctor_json" python3 <<'PY'
import json, os, sys
payload = json.loads(os.environ["DOCTOR_JSON"])
if not payload.get("ok"):
    print(json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit("doctor --json reported not ok before start")
checks = {check.get("name"): check for check in payload.get("checks", [])}
for required in ["tmux", "python", "tracker script", "agent-wrapper", "agent-communicator", "runtime dir", "cache dir", "config dir"]:
    if checks.get(required, {}).get("status") != "ok":
        raise SystemExit(f"doctor check {required!r} was not ok")
if payload.get("runtime", {}).get("tracker_up") or payload.get("runtime", {}).get("tmux_up"):
    raise SystemExit("doctor reported runtime up before start")
PY

broccoli start

[[ -S "$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock" ]]
can_connect_unix "$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock"

[[ -S "$BROCCOLI_COMMS_RUNTIME_DIR/tmux.sock" ]]
tmux_private has-session -t "$session_name"

doctor_json="$(broccoli doctor --json)"
DOCTOR_JSON="$doctor_json" python3 <<'PY'
import json, os, sys
payload = json.loads(os.environ["DOCTOR_JSON"])
if not payload.get("ok"):
    print(json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit("doctor --json reported not ok after start")
if not payload.get("runtime", {}).get("tracker_up") or not payload.get("runtime", {}).get("tmux_up"):
    print(json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit("doctor did not report runtime sockets up after start")
checks = {check.get("name"): check for check in payload.get("checks", [])}
if checks.get("tracker socket", {}).get("status") != "ok" or checks.get("tmux session", {}).get("status") != "ok":
    raise SystemExit("doctor runtime checks were not ok after start")
PY

status_json="$(broccoli status --json)"
STATUS_JSON="$status_json" python3 <<'PY'
import json, os, sys
status = json.loads(os.environ["STATUS_JSON"])
expected_runtime = os.environ["BROCCOLI_COMMS_RUNTIME_DIR"]
checks = {
    "app": status.get("app") == "broccoli-comms",
    "paths.runtime_dir": status.get("paths", {}).get("runtime_dir") == expected_runtime,
    "paths.cache_dir": status.get("paths", {}).get("cache_dir") == os.environ["BROCCOLI_COMMS_CACHE_DIR"],
    "paths.config_dir": status.get("paths", {}).get("config_dir") == os.environ["BROCCOLI_COMMS_CONFIG_DIR"],
    "tracker.up": status.get("tracker", {}).get("up") is True,
    "tmux.up": status.get("tmux", {}).get("up") is True,
    "tracker.socket": status.get("tracker", {}).get("socket") == f"{expected_runtime}/agent-tracker.sock",
    "tmux.mode": status.get("tmux", {}).get("mode") == "private",
    "tmux.socket": status.get("tmux", {}).get("socket") == f"{expected_runtime}/tmux.sock",
    "tmux.session": status.get("tmux", {}).get("session") == "broccoli-comms-agents",
    "agents.configured_count": status.get("agents", {}).get("configured_count") == 0,
    "agents.managed_running_count": status.get("agents", {}).get("managed_running_count") == 0,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    print(json.dumps(status, indent=2), file=sys.stderr)
    raise SystemExit(f"status check failed: {', '.join(failed)}")
PY

agents_json="$(tracker_ctl list)"
AGENTS_JSON="$agents_json" python3 <<'PY'
import json, os, sys
agents = json.loads(os.environ["AGENTS_JSON"] or "{}")
local_agents = {name: info for name, info in agents.items() if info.get("scope", "local") == "local"}
if local_agents:
    print(json.dumps(local_agents, indent=2), file=sys.stderr)
    raise SystemExit("private tracker recovered agents before any app agents were configured")
if "sentinel-default-tmux-agent" in agents:
    raise SystemExit("private tracker recovered the inherited/default tmux sentinel pane")
PY

broccoli stop

for _ in {1..50}; do
  if ! tmux_private has-session -t "$session_name" >/dev/null 2>&1 \
    && ! can_connect_unix "$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

if tmux_private has-session -t "$session_name" >/dev/null 2>&1; then
  echo "tmux session still exists after stop" >&2
  exit 1
fi

if can_connect_unix "$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock" >/dev/null 2>&1; then
  echo "agent-tracker socket still accepts connections after stop" >&2
  exit 1
fi

if [[ -e "$BROCCOLI_COMMS_RUNTIME_DIR/tmux.sock" || -e "$BROCCOLI_COMMS_RUNTIME_DIR/agent-tracker.sock" ]]; then
  echo "runtime sockets were not removed after stop" >&2
  ls -la "$BROCCOLI_COMMS_RUNTIME_DIR" >&2 || true
  exit 1
fi

env -u TMUX -u TMUX_PANE tmux -S "$sentinel_socket" kill-server >/dev/null 2>&1 || true
trap - EXIT
rm -rf "$tmpdir"

echo "private runtime smoke test passed"
