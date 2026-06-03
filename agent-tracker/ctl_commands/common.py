import argparse
import fcntl
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

import config

CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "agent-tracker")
SOCKET_PATH = config.get("paths", "agent_tracker_socket", os.path.join(CACHE_DIR, "agent-tracker.sock"))
LOCK_PATH = os.path.join(CACHE_DIR, "agent-tracker.lock")
REGISTRY_STATUS_PATH = os.path.join(CACHE_DIR, "registry-status.json")
DEFAULT_STARTUP_TIMEOUT = 5.0
DEFAULT_CAPTURE_PANE_LINES = 20


def default_capture_pane_lines() -> int:
    raw = config.get("ui", "capture_pane_default_lines", str(DEFAULT_CAPTURE_PANE_LINES))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CAPTURE_PANE_LINES
    return value if value > 0 else DEFAULT_CAPTURE_PANE_LINES


def _can_connect() -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(SOCKET_PATH)
        s.close()
        return True
    except OSError:
        return False


def ensure_tracker_running(timeout: float = DEFAULT_STARTUP_TIMEOUT) -> bool:
    os.makedirs(CACHE_DIR, exist_ok=True)
    if _can_connect():
        return True

    daemon_cmd = config.get("executables", "agent_tracker")
    if not daemon_cmd:
        return False

    with open(LOCK_PATH, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        if _can_connect():
            return True

        if os.path.exists(SOCKET_PATH) and not _can_connect():
            try:
                os.remove(SOCKET_PATH)
            except FileNotFoundError:
                pass

        if not _can_connect():
            subprocess.Popen(
                shlex.split(daemon_cmd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=tmux_env(),
            )

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _can_connect():
            return True
        time.sleep(0.1)

    return _can_connect()


def spin_session_name(directory: str) -> str:
    import re
    leaf = os.path.basename(os.path.abspath(directory)) or "root"
    leaf = re.sub(r"[^A-Za-z0-9_-]", "_", leaf)
    leaf = re.sub(r"_+", "_", leaf).strip("_")
    return leaf or "root"


def call_rpc(method, params={}):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect(SOCKET_PATH)
        s.sendall(json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode())
        s.shutdown(socket.SHUT_WR)

        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        resp = b"".join(chunks)

        data = json.loads(resp.decode())
        if "error" in data:
            print(f"Error: {data['error']['message']}", file=sys.stderr)
            sys.exit(1)
        return data.get("result")
    except (socket.error, socket.timeout) as e:
        print(f"Socket communication failed: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Failed to decode response from tracker: {e}", file=sys.stderr)
        sys.exit(1)


def default_tmux_socket() -> str | None:
    """Returns the app-private tmux socket configured for this CLI, if any."""
    if config.get("core", "tmux_mode") == "private":
        return str(config.get("paths", "tmux_socket"))
    return None


def tmux_command(args: list[str], socket_path: str | None = None) -> list[str]:
    """Builds a tmux command, defaulting to the configured private socket."""
    args = list(args or [])
    if args and args[0] in ("-S", "-L"):
        return ["tmux"] + args
    socket_path = socket_path if socket_path is not None else default_tmux_socket()
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    return cmd + args


def tmux_env(strip_inherited: bool | None = None) -> dict[str, str]:
    """Returns an environment for tmux commands.

    When an explicit/private socket is configured, inherited TMUX/TMUX_PANE must
    not influence which server is contacted. Without a private socket, CLI tools
    still support the legacy/default tmux context.
    """
    if strip_inherited is None:
        strip_inherited = bool(default_tmux_socket())
    env = os.environ.copy()
    if strip_inherited:
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
    return env


def get_current_tmux_pane(fallback: str | None = None) -> str:
    if fallback is not None:
        return fallback
    try:
        return subprocess.check_output(
            tmux_command(["display-message", "-p", "#{pane_id}"]),
            env=tmux_env(),
        ).decode("utf-8").strip()
    except subprocess.CalledProcessError:
        return ""


def is_uuid(value: str | None) -> bool:
    try:
        uuid.UUID(value or "")
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def parse_target_params(target: str) -> dict:
    """Return RPC target params using the same CLI target rules as send-message."""
    if "/" in target:
        return {"target_address": target}
    if is_uuid(target):
        return {"agent_id": target}
    return {"agent_name": target}


def _read_token_config(config: dict) -> str:
    if config.get("token"):
        return str(config.get("token"))
    token_file = config.get("token-file") or config.get("tokenFile")
    if token_file:
        try:
            with open(token_file, "r") as f:
                return f.read().strip()
        except Exception:
            return ""
    return config.get("registry", "token", "")


def _normalize_registries_json(raw: str) -> str:
    raw = (raw or "").strip().replace('\\"', '"')
    for _ in range(2):
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            if raw[0] == '"':
                try:
                    decoded = json.loads(raw)
                    if isinstance(decoded, str):
                        raw = decoded.strip()
                        continue
                except json.JSONDecodeError:
                    pass
            raw = raw[1:-1].strip()
        break
    if "'" in raw and '"' not in raw:
        raw = raw.replace("'", '"')
    return raw


def registry_configs() -> list[dict]:
    raw = config.get("registry", "endpoints", [])
    if isinstance(raw, str):
        raw = _normalize_registries_json(raw)
    elif not isinstance(raw, list):
        raw = []
    if not raw:
        return []
    try:
        configs = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(configs, dict):
        configs = configs.get("registries") or []
    return [{**c, "token": _read_token_config(c)} for c in configs if isinstance(c, dict) and c.get("url")]


def fetch_registry_agents(timeout: float = 3.0) -> dict:
    """Best-effort fetch of remote agents from all configured registries."""
    remote_agents = {}
    for config in registry_configs():
        registry_url = str(config.get("url", "")).strip().rstrip("/")
        if not registry_url:
            continue
        token = str(config.get("token") or "")
        req = urllib.request.Request(
            f"{registry_url}/agents",
            headers={**({"Authorization": f"Bearer {token}"} if token else {})},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    continue
                payload = json.loads(resp.read().decode() or "{}")
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            continue
        registry_name = config.get("name") or "default"
        for agent in payload.get("agents") or []:
            hostname = agent.get("hostname")
            name = agent.get("name")
            if not hostname or not name:
                continue
            base_key = f"{hostname}/{name}"
            key = base_key
            if base_key in remote_agents and remote_agents[base_key].get("agent_id") != agent.get("agent_id"):
                existing = remote_agents.pop(base_key)
                existing_registry = existing.get("registry_name") or "default"
                existing_key = f"{existing_registry}:{base_key}"
                remote_agents[existing_key] = {**existing, "name": existing_key, "target_address": existing_key}
                key = f"{registry_name}:{base_key}"
            elif base_key not in remote_agents and any(k.endswith(f":{base_key}") for k in remote_agents):
                key = f"{registry_name}:{base_key}"
            remote_agents[key] = {**agent, "name": key, "scope": "remote", "target_address": key, "registry_name": registry_name}
    return remote_agents


def merge_registry_agents(local_agents: dict, remote_agents: dict) -> dict:
    merged = {name: {**info, "scope": info.get("scope", "local")} for name, info in (local_agents or {}).items()}
    local_agent_ids = {info.get("agent_id") for info in (local_agents or {}).values() if info.get("agent_id")}
    for name, info in (remote_agents or {}).items():
        if info.get("agent_id") in local_agent_ids:
            continue
        merged[name] = info
    return merged


def load_registry_status() -> dict:
    try:
        with open(REGISTRY_STATUS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _is_entry_fresh(entry: dict, now: float, max_age: int) -> bool:
    last_success = entry.get("last_success")
    return bool(entry.get("connected") and isinstance(last_success, (int, float)) and now - last_success <= max_age)


def registry_connection_states(status: dict | None = None, now: float | None = None) -> list[tuple[str, bool]]:
    configs = registry_configs()
    if not configs:
        return []
    status = load_registry_status() if status is None else status
    now = time.time() if now is None else now
    heartbeat_interval = config.get("registry", "heartbeat_seconds", 30)
    max_age = max(heartbeat_interval * 2 + 5, 15)
    entries = status.get("registries") or {}
    states = []
    for config in configs:
        name = config.get("name") or "default"
        entry = entries.get(name)
        if entry is None and name == "default":
            entry = status
        states.append((name, _is_entry_fresh(entry or {}, now, max_age)))
    return states


def is_registry_connected(now: float | None = None) -> bool:
    return any(connected for _, connected in registry_connection_states(now=now))


def format_registry_status(status: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    registries = status.get("registries") or {"default": status} if status else {}
    configured_names = {config.get("name") or "default" for config in registry_configs()}
    if configured_names:
        registries = {name: entry for name, entry in registries.items() if name in configured_names}
    if not registries:
        return "No registry status found."
    lines = []
    for name in sorted(registries):
        entry = registries[name]
        ok = "connected" if entry.get("connected") else "disconnected"
        last_success = entry.get("last_success")
        age = "never" if not isinstance(last_success, (int, float)) else f"{int(now - last_success)}s ago"
        detail = entry.get("last_error") or f"status={entry.get('status_code')}"
        lines.append(f"{name}: {ok}, last_success={age}, url={entry.get('registry_url')}, {detail}")
    return "\n".join(lines)


def format_registry_dots(states: list[tuple[str, bool]] | None, connected_fallback: bool, color_ok: str, color_bad: str) -> str:
    if not states:
        color = color_ok if connected_fallback else color_bad
        dots = f"#[fg={color},bold]●"
    else:
        dots = "".join(f"#[fg={color_ok if connected else color_bad},bold]●" for _, connected in states)
    return f"#[range=user|agent-registries]{dots}#[norange] "


def format_status_bar(agents: dict, current_pane: str, registry_connected: bool = False, registry_states: list[tuple[str, bool]] | None = None) -> str:
    if not agents:
        return ""

    color8 = config.get("ui", "palette_color8", "#414868")
    color1 = config.get("ui", "palette_color1", "#db4b4b")
    color3 = config.get("ui", "palette_color3", "#e0af68")
    color6 = config.get("ui", "palette_color6", "#7dcfff")
    color2 = config.get("ui", "palette_color2", "#9ece6a")
    color4 = config.get("ui", "palette_color4", "#2ac3de")

    formatted = []
    for name, info in agents.items():
        pane = info.get("tmux_pane")
        waiting_approval = info.get("waiting_approval", False)
        status = info.get("status", "")

        color = color8
        if waiting_approval:
            color = color1
        elif pane == current_pane:
            color = color3
        elif status == "working":
            color = color6
        elif status == "idle":
            color = color2

        range_arg = f"agent:{pane}"
        formatted.append(f"#[range=user|{range_arg}]#[fg={color},bold]{name}#[fg={color8},nobold]#[norange]")

    if not formatted:
        return ""

    indicator = format_registry_dots(registry_states, registry_connected, color2, color1).rstrip()
    prefix = f"#[fg={color4},bold]Active Agents: #[fg={color8},nobold]"
    return f"{prefix}{' · '.join(formatted)}#[align=right]{indicator}#[default]"
