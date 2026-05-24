import threading
import time
import uuid
import logging
import subprocess
import os
import json
import tmux_util

CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "agent-tracker")
SOCKET_PATH = os.environ.get("AGENT_TRACKER_SOCKET", os.path.join(CACHE_DIR, "agent-tracker.sock"))
LOCK_PATH = os.path.join(CACHE_DIR, "agent-tracker.lock")
INBOX_DIR = os.path.join(CACHE_DIR, "inboxes")

state = {}  # keyed by stable agent_id
name_index = {}  # agent_name/alias -> agent_id
pane_index = {}  # tmux pane id -> agent_id
state_lock = threading.Lock()
event_lock = threading.Condition()
events = []
event_seq = 0
MAX_EVENTS = 200

TRANSIENT_COMMS = {
    "ps", "grep", "pgrep", "ls", "cat", "sleep", "which", "sh", "bash", "zsh",
    "fish", "tmux", "home-manager", "nix", "env"
}


def discover_agent_process(pane_id: str, agent_cmd: str | None = None) -> dict | None:
    """Best-effort discovery of the long-lived agent process attached to a pane."""
    info = tmux_util.get_pane_info(pane_id)
    if not info:
        return None

    tty = info["tty"]
    shell_pid = info["pid"]
    pts_name = tty.replace("/dev/", "")

    try:
        out = subprocess.check_output(
            ["ps", "-t", pts_name, "-o", "pid=,ppid=,comm=,args="],
            timeout=2,
        ).decode("utf-8").strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    proc_list = []
    for line in out.split("\n"):
        parts = line.strip().split(None, 3)
        if len(parts) < 3:
            continue
        pid = int(parts[0])
        ppid = int(parts[1])
        comm = parts[2]
        args = parts[3] if len(parts) > 3 else comm
        proc_list.append({"pid": pid, "ppid": ppid, "comm": comm, "args": args})

    candidates = [p for p in proc_list if p["pid"] != shell_pid and p["comm"] not in TRANSIENT_COMMS]
    if not candidates:
        return None

    expected_patterns = {
        "jetski": ["cli", "jetski"],
        "gemini": ["gemini"],
        "pi": ["pi", "pi-coding-agent", "@earendil-works/pi-coding-agent"],
    }.get(agent_cmd, [])

    if expected_patterns:
        for proc in reversed(candidates):
            haystack = f'{proc["comm"]} {proc["args"]}'.lower()
            if any(pattern in haystack for pattern in expected_patterns):
                return proc

    return candidates[-1]


def init_state() -> None:
    """Recovers existing agents by querying tmux panes."""
    logging.info("Initializing state from tmux panes...")
    panes = tmux_util.list_panes()
    if panes is None:
        logging.warning("Skipping state recovery because tmux panes could not be listed.")
        return
    for pane in panes:
        pane_id = pane["pane_id"]
        agent_name = pane["agent_name"]
        agent_id = pane.get("agent_id")
        agent_uuid = pane["agent_uuid"]
        agent_type = pane.get("agent_type", "unknown")
        agent_cmd = pane.get("agent_cmd")
        no_notify_with_send_keys = bool(pane.get("no_notify_with_send_keys", False))
        no_registry = bool(pane.get("no_registry", False))
        if agent_name:
            logging.info(f"Found recovered agent: {agent_name} of type {agent_type} in pane {pane_id}")
            try:
                info = tmux_util.get_pane_info(pane_id)
                proc = discover_agent_process(pane_id, agent_cmd)
                if info:
                    session = info["session"]
                    agent_pid = proc["pid"] if proc else None
                    discovered_cmd = proc["comm"] if proc else None
                    resolved_agent_id = agent_id or agent_uuid or str(uuid.uuid4())
                    set_agent(agent_name, {
                        "session": session,
                        "tmux_pane": pane_id,
                        "pid": agent_pid,
                        "tmux_socket": "", # Fallback to default
                        "wrapper_pid": None,
                        "status": "unknown",
                        "waiting_approval": False,
                        "agent_id": resolved_agent_id,
                        "uuid": resolved_agent_id,
                        "recovered_at": time.time(),
                        "agent_type": agent_type,
                        "agent_cmd": agent_cmd or discovered_cmd or "unknown",
                        "cwd": pane.get("cwd"),
                        "no_notify_with_send_keys": no_notify_with_send_keys,
                        "no_registry": no_registry,
                        "pending_notifications": []
                    })

                    # If we didn't have an agent_id in tmux, persist the recovered one.
                    if not agent_id:
                        logging.info(f"Generated/recovered agent ID {resolved_agent_id} for agent {agent_name}")
                        tmux_util.set_agent_id(pane_id, resolved_agent_id)
                        tmux_util.set_agent_uuid(pane_id, resolved_agent_id)

                    logging.info(f"Recovered agent {agent_name} with PID {agent_pid} and agent ID {resolved_agent_id}")
            except Exception as e:
                logging.error(f"Error recovering agent {agent_name}: {e}")

def _resolve_agent_id(name_or_id: str) -> str | None:
    if name_or_id in state:
        return name_or_id
    return name_index.get(name_or_id)


def _remove_indexes(agent_id: str, info: dict | None) -> None:
    if not info:
        return
    current_name = info.get("name")
    if current_name and name_index.get(current_name) == agent_id:
        name_index.pop(current_name, None)
    for alias in info.get("aliases", []):
        if name_index.get(alias) == agent_id:
            name_index.pop(alias, None)
    pane_id = info.get("tmux_pane")
    if pane_id and pane_index.get(pane_id) == agent_id:
        pane_index.pop(pane_id, None)


def _add_indexes(agent_id: str, info: dict) -> None:
    current_name = info.get("name")
    if current_name:
        name_index[current_name] = agent_id
    for alias in info.get("aliases", []):
        name_index[alias] = agent_id
    pane_id = info.get("tmux_pane")
    if pane_id:
        pane_index[pane_id] = agent_id


def get_all_agents() -> dict:
    """Returns a copy of all agents indexed by display name for compatibility."""
    with state_lock:
        return {
            info["name"]: {k: v for k, v in info.items() if k != "name"}
            for info in state.values()
        }


def get_agent(name_or_id: str) -> dict | None:
    """Returns the state of a specific agent by display name or agent_id."""
    with state_lock:
        agent_id = _resolve_agent_id(name_or_id)
        if not agent_id:
            return None
        info = state.get(agent_id)
        if not info:
            return None
        return {k: v for k, v in info.items() if k != "name"}


def get_agent_name_by_id(agent_id: str) -> str | None:
    """Returns the agent name for a given stable agent_id."""
    with state_lock:
        info = state.get(agent_id)
        return info.get("name") if info else None


def get_agent_id_by_name(name: str) -> str | None:
    """Returns the stable agent_id for a given display name."""
    with state_lock:
        return name_index.get(name)


def get_agent_name_by_pane(tmux_pane: str) -> str | None:
    """Returns the agent name for a given tmux pane."""
    with state_lock:
        agent_id = pane_index.get(tmux_pane)
        info = state.get(agent_id) if agent_id else None
        return info.get("name") if info else None


def set_agent(name: str, info: dict) -> None:
    """Sets or upserts an agent keyed by stable agent_id."""
    with state_lock:
        normalized = info.copy()
        agent_id = normalized.get("agent_id") or normalized.get("uuid") or str(uuid.uuid4())
        normalized["agent_id"] = agent_id
        normalized["uuid"] = agent_id
        normalized["name"] = name
        if "aliases" not in normalized:
            normalized["aliases"] = []

        existing = state.get(agent_id)
        if existing:
            normalized["aliases"] = existing.get("aliases", []).copy()
            if existing.get("name") and existing.get("name") != name:
                if existing["name"] not in normalized["aliases"]:
                    normalized["aliases"].append(existing["name"])

        existing_id_for_name = name_index.get(name)
        if existing_id_for_name and existing_id_for_name != agent_id:
            evicted = state.pop(existing_id_for_name, None)
            _remove_indexes(existing_id_for_name, evicted)

        _remove_indexes(agent_id, existing)
        state[agent_id] = normalized
        _add_indexes(agent_id, normalized)


def delete_agent(name_or_id: str) -> None:
    """Deletes an agent from state by display name or agent_id."""
    with state_lock:
        agent_id = _resolve_agent_id(name_or_id)
        if not agent_id:
            return
        info = state.pop(agent_id, None)
        _remove_indexes(agent_id, info)


def update_agent(name_or_id: str, **kwargs) -> bool:
    """Updates specific fields of an agent's state."""
    with state_lock:
        agent_id = _resolve_agent_id(name_or_id)
        if not agent_id or agent_id not in state:
            return False

        info = state[agent_id]
        old_pane = info.get("tmux_pane")
        for k, v in kwargs.items():
            info[k] = v
        new_pane = info.get("tmux_pane")
        if old_pane != new_pane:
            if old_pane and pane_index.get(old_pane) == agent_id:
                pane_index.pop(old_pane, None)
            if new_pane:
                pane_index[new_pane] = agent_id
        return True


def rename_agent(old_name: str, new_name: str) -> bool:
    """Renames an agent in state without changing its stable agent_id."""
    with state_lock:
        if old_name == new_name:
            return True
        agent_id = name_index.get(old_name)
        if not agent_id or new_name in name_index:
            return False
        name_index[new_name] = agent_id
        state[agent_id]["name"] = new_name
        if "aliases" not in state[agent_id]:
            state[agent_id]["aliases"] = []
        if old_name not in state[agent_id]["aliases"]:
            state[agent_id]["aliases"].append(old_name)
        return True


def get_agents_for_registry() -> list[dict]:
    """Returns a sidecar/registry-safe snapshot of agents."""
    with state_lock:
        return [{
            "agent_id": info.get("agent_id") or agent_id,
            "name": info.get("name"),
            "aliases": info.get("aliases", []),
            "status": info.get("status", "unknown"),
            "agent_type": info.get("agent_type", "unknown"),
            "agent_cmd": info.get("agent_cmd", "unknown"),
            "cwd": info.get("cwd"),
        } for agent_id, info in state.items() if not info.get("no_registry", False)]


def publish_event(event_type: str, payload: dict) -> dict:
    """Publishes a best-effort in-memory event for live observers such as a TUI."""
    global event_seq
    with event_lock:
        event_seq += 1
        event = {
            **payload,
            "seq": event_seq,
            "type": event_type,
            "timestamp": time.time(),
        }
        events.append(event)
        del events[:-MAX_EVENTS]
        event_lock.notify_all()
        return event.copy()


def wait_events(since: int = 0, timeout: float = 25.0, filters: dict | None = None) -> dict:
    """Best-effort event long-poll for observers; callers must still read durable inboxes."""
    deadline = time.time() + max(0.0, min(float(timeout), 30.0))
    filters = filters or {}

    def event_matches(event: dict) -> bool:
        target_agent_id = filters.get("target_agent_id")
        target_agent_name = filters.get("target_agent_name")
        if target_agent_id and event.get("target_agent_id") != target_agent_id:
            return False
        if target_agent_name and event.get("target_agent_name") != target_agent_name:
            return False
        return True

    with event_lock:
        while True:
            reset = since > event_seq
            first_seq = events[0]["seq"] if events else event_seq + 1
            gap = bool(events and since < first_seq - 1)
            effective_since = 0 if reset else since
            matching = [event.copy() for event in events if event["seq"] > effective_since and event_matches(event)]
            if matching or reset or gap:
                return {"events": matching, "last_seq": event_seq, "reset": reset, "gap": gap}
            remaining = deadline - time.time()
            if remaining <= 0:
                return {"events": [], "last_seq": event_seq, "reset": False, "gap": False}
            event_lock.wait(timeout=remaining)


def get_local_configs_for_registry() -> list[dict]:
    """Loads local agent configs and strips out implementation details, sharing name and description only."""
    home = os.path.expanduser("~")
    agents_dir = os.path.join(home, ".config", "agent-tracker", "agents")
    configs = []
    if not os.path.isdir(agents_dir):
        return configs

    try:
        for name in os.listdir(agents_dir):
            path = os.path.join(agents_dir, name)
            if not os.path.isdir(path):
                continue
            config_file = os.path.join(path, "config.json")
            if not os.path.isfile(config_file):
                continue
            try:
                with open(config_file, "r") as f:
                    data = json.load(f)
                desc = data.get("description") or ""
                configs.append({"name": name, "description": desc})
            except Exception:
                pass
    except Exception:
        pass
    return configs
