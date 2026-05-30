import threading
import time
import uuid
import logging
import subprocess
import os
import hashlib
import json
import re
import tmux_util

CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "agent-tracker")
SOCKET_PATH = os.environ.get("AGENT_TRACKER_SOCKET", os.path.join(CACHE_DIR, "agent-tracker.sock"))
LOCK_PATH = os.path.join(CACHE_DIR, "agent-tracker.lock")
INBOX_DIR = os.path.join(CACHE_DIR, "inboxes")
GROUP_TIMELINE_DIR = os.path.join(CACHE_DIR, "group_timelines")
PANE_INPUT_DEDUPE_PATH = os.path.join(CACHE_DIR, "pane-input-dedupe.json")
PANE_INPUT_DEDUPE_MAX = int(os.environ.get("AGENT_PANE_INPUT_DEDUPE_MAX", "1000"))

state = {}  # keyed by stable agent_id
name_index = {}  # agent_name/alias -> agent_id
pane_index = {}  # tmux pane id -> agent_id
state_lock = threading.Lock()
event_lock = threading.Condition()
events = []
event_sequence_id = 0
MAX_EVENTS = 500

active_watchlists = {}  # client_id -> {"expires_at": float, "watch_list": set}
watchlist_lock = threading.Lock()

active_group_watches = {}  # watch_id -> {"expires_at": float, "group_id": str, "members": set, "include_body": bool}
group_watches_lock = threading.Lock()
group_timelines_lock = threading.Lock()

TRANSIENT_COMMS = {
    "ps", "grep", "pgrep", "ls", "cat", "sleep", "which", "sh", "bash", "zsh",
    "fish", "tmux", "home-manager", "nix", "env"
}


def normalize_model_type(*values: str | None) -> str:
    """Returns the canonical UI model type for agent metadata."""
    for value in values:
        if not value:
            continue
        basename = os.path.basename(str(value).strip()).lower()
        tokens = {token for token in re.split(r"[^a-z0-9]+", basename) if token}
        if "claude" in tokens or basename == "claude-code":
            return "claude"
        if "codex" in tokens:
            return "codex"
        if "pi" in tokens or basename == "pi-coding-agent":
            return "pi"
    return "unknown"


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
                        "tmux_socket": pane.get("tmux_socket") or tmux_util.default_tmux_socket() or "", # Prefer tmux-reported socket; fallback to configured default
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
        normalized["model_type"] = normalize_model_type(
            normalized.get("model_type"),
            normalized.get("agent_type"),
            normalized.get("agent_cmd"),
        )

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
        if any(k in kwargs for k in ("model_type", "agent_type", "agent_cmd")):
            info["model_type"] = normalize_model_type(info.get("model_type"), info.get("agent_type"), info.get("agent_cmd"))
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
            "model_type": normalize_model_type(info.get("model_type"), info.get("agent_type"), info.get("agent_cmd")),
            "cwd": info.get("cwd"),
        } for agent_id, info in state.items() if not info.get("no_registry", False)]


def publish_event(event_type: str, payload: dict) -> dict:
    """Publishes a best-effort in-memory event for live observers such as a TUI."""
    global event_sequence_id
    with event_lock:
        event_sequence_id += 1
        event = {
            **payload,
            "seq": event_sequence_id,
            "type": event_type,
            "timestamp": time.time(),
        }
        events.append(event)
        del events[:-MAX_EVENTS]
        event_lock.notify_all()
        return event.copy()


def update_watchlist_lease(client_id: str, watch_list: list[str], lease_seconds: float) -> None:
    """Atomically registers or replaces a client watchlist lease with a set TTL."""
    with watchlist_lock:
        expires_at = time.time() + lease_seconds
        active_watchlists[client_id] = {
            "expires_at": expires_at,
            "watch_list": set(watch_list)
        }
        logging.debug(f"Updated watchlist lease for client {client_id} with TTL {lease_seconds}s. Watchlist: {watch_list}")


def sweep_expired_watchlists() -> None:
    """Sweeps and purges expired client watchlists from in-memory tracking."""
    now = time.time()
    with watchlist_lock:
        expired = [cid for cid, data in active_watchlists.items() if data["expires_at"] < now]
        for cid in expired:
            active_watchlists.pop(cid)
            logging.info(f"Purged expired watchlist lease for client {cid}")


def wait_events(since: int = 0, timeout: float = 25.0, filters: dict | None = None, client_id: str | None = None, watch_list: list[str] | None = None) -> dict:
    """Best-effort event long-poll for observers; callers must still read durable inboxes."""
    deadline = time.time() + max(0.0, min(float(timeout), 30.0))
    filters = filters or {}
    
    effective_watchlist = set()
    if watch_list:
        effective_watchlist.update(watch_list)
    if client_id:
        effective_watchlist.add(client_id)

    def event_matches(event: dict) -> bool:
        # Backward-compatibility filters
        target_agent_id = filters.get("target_agent_id")
        target_agent_name = filters.get("target_agent_name")
        if target_agent_id and event.get("target_agent_id") != target_agent_id:
            return False
        if target_agent_name and event.get("target_agent_name") != target_agent_name:
            return False
            
        # Active watchlist-based filtering
        if effective_watchlist:
            t_id = event.get("target_agent_id")
            t_name = event.get("target_agent_name")
            sender = event.get("sender")
            # Match if either the target ID, target name, or sender is in effective watchlist
            if not (t_id in effective_watchlist or t_name in effective_watchlist or sender in effective_watchlist):
                return False
        return True

    with event_lock:
        while True:
            reset = since > event_sequence_id
            first_seq = events[0]["seq"] if events else event_sequence_id + 1
            gap = bool(events and since < first_seq - 1)
            effective_since = 0 if reset else since
            matching = [event.copy() for event in events if event["seq"] > effective_since and event_matches(event)]
            if matching or reset or gap:
                return {"events": matching, "last_seq": event_sequence_id, "reset": reset, "gap": gap}
            remaining = deadline - time.time()
            if remaining <= 0:
                return {"events": [], "last_seq": event_sequence_id, "reset": False, "gap": False}
            event_lock.wait(timeout=remaining)


def _load_pane_input_dedupe() -> dict:
    try:
        with open(PANE_INPUT_DEDUPE_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.warning("failed to load pane input dedupe store %s: %s", PANE_INPUT_DEDUPE_PATH, e)
        return {}


def _write_pane_input_dedupe(data: dict) -> None:
    os.makedirs(os.path.dirname(PANE_INPUT_DEDUPE_PATH), exist_ok=True)
    trimmed_items = sorted(data.items(), key=lambda item: item[1].get("applied_at", 0))[-PANE_INPUT_DEDUPE_MAX:]
    tmp = PANE_INPUT_DEDUPE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dict(trimmed_items), f)
    os.replace(tmp, PANE_INPUT_DEDUPE_PATH)


def pane_input_was_applied(request_id: str) -> bool:
    if not request_id:
        return False
    with state_lock:
        return request_id in _load_pane_input_dedupe()


def mark_pane_input_applied(request_id: str, pane_input_id: str | None = None, target_agent_id: str | None = None) -> None:
    if not request_id:
        raise ValueError("request_id is required")
    with state_lock:
        data = _load_pane_input_dedupe()
        data[request_id] = {
            "request_id": request_id,
            "pane_input_id": pane_input_id or request_id,
            "target_agent_id": target_agent_id,
            "applied_at": time.time(),
        }
        _write_pane_input_dedupe(data)


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


def _get_group_timeline_path(group_id: str) -> str:
    group_hash = hashlib.md5(group_id.encode("utf-8")).hexdigest()
    return os.path.join(GROUP_TIMELINE_DIR, f"{group_hash}.jsonl")


def append_to_group_timeline(group_id: str, message_payload: dict) -> None:
    msg_id = message_payload.get("message_id")
    if not msg_id:
        return

    os.makedirs(GROUP_TIMELINE_DIR, exist_ok=True)
    timeline_path = _get_group_timeline_path(group_id)

    with group_timelines_lock:
        exists = False
        if os.path.exists(timeline_path):
            try:
                with open(timeline_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("message_id") == msg_id:
                                exists = True
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logging.warning("failed to read group timeline for deduplication: %s", e)

        if exists:
            return

        try:
            with open(timeline_path, "a") as f:
                f.write(json.dumps(message_payload) + "\n")
        except Exception as e:
            logging.warning("failed to append to group timeline %s: %s", timeline_path, e)


def read_group_timeline(group_id: str, last_n: int = 200) -> list[dict]:
    timeline_path = _get_group_timeline_path(group_id)
    if not os.path.exists(timeline_path):
        return []

    entries = []
    try:
        with open(timeline_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logging.warning("failed to read group timeline %s: %s", timeline_path, e)
        return []

    entries.sort(key=lambda e: e.get("timestamp", ""))
    return entries[-last_n:]


def update_group_watch(watch_id: str, group_id: str, members: list[str], lease_seconds: float, include_body: bool = True, reply_to_tracker_id: str | None = None) -> None:
    watch_key = f"{reply_to_tracker_id}:{watch_id}" if reply_to_tracker_id else watch_id
    with group_watches_lock:
        active_group_watches[watch_key] = {
            "expires_at": time.time() + lease_seconds,
            "group_id": group_id,
            "members": set(members),
            "include_body": include_body,
            "reply_to_tracker_id": reply_to_tracker_id
        }


def sweep_expired_group_watches() -> None:
    now = time.time()
    with group_watches_lock:
        expired = [wid for wid, watch in active_group_watches.items() if watch.get("expires_at", 0) < now]
        for wid in expired:
            del active_group_watches[wid]
            logging.info("swept expired group watch lease watch_id=%s", wid)


def normalize_group_member(member: str) -> dict:
    """Normalizes a qualified group member address into registry, hostname, and agent bare name."""
    addr = member
    if addr.startswith("remote:"):
        addr = addr[len("remote:"):]

    if "/" in addr:
        parts = addr.split("/")
        host_part = parts[0]
        agent_part = parts[1]
        if ":" in host_part:
            host_part = host_part.split(":")[-1]
        return {
            "hostname": host_part,
            "agent": agent_part
        }
    else:
        if ":" in addr:
            addr = addr.split(":")[-1]
        return {
            "hostname": None,
            "agent": addr
        }


def _member_matches(member_address: str, logical_name: str) -> bool:
    norm = normalize_group_member(member_address)
    return norm.get("agent") == logical_name


def record_to_matching_group_timelines(sender: str, recipient: str, msg_obj: dict) -> None:
    sweep_expired_group_watches()
    with group_watches_lock:
        for watch_id, watch in active_group_watches.items():
            members = watch.get("members", set())
            has_sender = any(_member_matches(m, sender) for m in members)
            has_recipient = any(_member_matches(m, recipient) for m in members)
            
            if has_sender and has_recipient:
                group_id = watch["group_id"]
                
                timeline_payload = {
                    "message_id": msg_obj.get("message_id"),
                    "sender": sender,
                    "sender_agent_id": msg_obj.get("sender_agent_id"),
                    "sender_tracker_id": msg_obj.get("sender_tracker_id"),
                    "recipient": recipient,
                    "recipient_agent_id": get_agent_id_by_name(recipient) or msg_obj.get("recipient_agent_id"),
                    "timestamp": msg_obj.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "message": msg_obj.get("message") if watch.get("include_body", True) else "[Observed Body Encrypted/Omitted]"
                }
                
                append_to_group_timeline(group_id, timeline_payload)
                logging.info("observed message message_id=%s recorded to group timeline group_id=%s", msg_obj.get("message_id"), group_id)
                
                reply_tid = watch.get("reply_to_tracker_id")
                if reply_tid:
                    try:
                        import registry_client
                        registry_client.publish_tracker_event(reply_tid, "group_message_observed", {
                            "group_id": group_id,
                            "message": timeline_payload
                        })
                        logging.info("emitted group_message_observed back to requester tracker %s", reply_tid)
                    except Exception as re:
                        logging.warning("failed to propagate delegated group_message_observed: %s", re)
