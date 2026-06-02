import base64
import binascii
import json
import logging
import socket
import state
import tmux_util
import registry_client
import permission_detection
import datetime
import time
import os
import threading
import uuid
import subprocess
import struct
import re
import fcntl
from contextlib import contextmanager

BUFFER_SIZE = 4096
LOCAL_HOSTNAME = os.environ.get("AGENT_TRACKER_HOSTNAME", socket.gethostname())
REMOTE_BROAD_WATCH_ENABLED = os.environ.get("AGENT_TRACKER_BROAD_WATCH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
DEFAULT_CAPTURE_PANE_LINES = 20


def _default_capture_pane_lines() -> int:
    raw = os.environ.get("AGENT_TRACKER_CAPTURE_PANE_DEFAULT_LINES", str(DEFAULT_CAPTURE_PANE_LINES))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CAPTURE_PANE_LINES
    return value if value > 0 else DEFAULT_CAPTURE_PANE_LINES


@contextmanager
def _locked_inbox(inbox_file: str):
    os.makedirs(os.path.dirname(inbox_file), exist_ok=True)
    lock_path = inbox_file + ".lock"
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _atomic_write_inbox(inbox_file: str, messages: list[dict]) -> None:
    tmp = inbox_file + ".tmp"
    with open(tmp, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")
    os.replace(tmp, inbox_file)


class DeliveryTargetNotFound(ValueError):
    pass


class DeliveryValidationError(ValueError):
    pass


class CursorExpiredError(ValueError):
    pass


class RPCStructuredError(ValueError):
    def __init__(self, message: str, data: dict, code: int = -32602):
        super().__init__(message)
        self.code = code
        self.data = data


def _utc_now_isoformat() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _generate_unique_agent_name(name: str, session: str = None, is_register: bool = False) -> str:
    agents = state.get_all_agents()
    if name:
        agent_name = name
        base_name = name
        num = 1
        m = re.match(r'^(.*)-(\d+)$', name)
        if m:
            base_name = m.group(1)
            num = int(m.group(2))
            has_conflict = state.get_agent_id_by_name(agent_name)
            if has_conflict:
                is_spawning = (state.get_agent(agent_name) or {}).get("status") == "spawning"
                if is_spawning and is_register:
                    return agent_name
            num += 1
            agent_name = f"{base_name}-{num}"

        while state.get_agent_id_by_name(agent_name):
            is_spawning = (state.get_agent(agent_name) or {}).get("status") == "spawning"
            if is_spawning and is_register:
                break
            agent_name = f"{base_name}-{num}"
            num += 1
        return agent_name
    else:
        num = 1
        while f"{session}-agent-{num}" in agents:
            num += 1
        return f"{session}-agent-{num}"


def _best_effort_update_tmux_metadata(tmux_pane, agent_name, agent_id, agent_type, agent_cmd, tmux_socket, no_notify_with_send_keys=False, no_registry=False):
    """Persist restart-recovery metadata in tmux without making registration depend on tmux."""
    try:
        tmux_util.set_agent_id(tmux_pane, agent_id, tmux_socket)
        tmux_util.set_agent_uuid(tmux_pane, agent_id, tmux_socket)
        tmux_util.set_agent_name(tmux_pane, agent_name, tmux_socket)
        tmux_util.set_agent_type(tmux_pane, agent_type or "unknown", tmux_socket)
        tmux_util.set_agent_cmd(tmux_pane, agent_cmd or "unknown", tmux_socket)
        tmux_util.set_agent_no_notify_with_send_keys(tmux_pane, no_notify_with_send_keys, tmux_socket)
        tmux_util.set_agent_no_registry(tmux_pane, no_registry, tmux_socket)
        tmux_util.set_pane_title(tmux_pane, agent_name, tmux_socket)
    except Exception as e:
        logging.warning("failed to update tmux metadata for agent %s pane %s: %s", agent_name, tmux_pane, e)


def handle_register(params: dict) -> str:
    """Handles agent registration, accepting a stable agent_id when provided."""
    session = params.get("session")
    tmux_pane = params.get("tmux_pane")
    wrapper_pid = params.get("wrapper_pid")
    tmux_socket = params.get("tmux_socket")
    name = params.get("name")
    agent_type = params.get("agent_type", "unknown")
    agent_cmd = params.get("agent_cmd", "unknown")
    model_type = state.normalize_model_type(params.get("model_type"), agent_type, agent_cmd)
    agent_id = params.get("agent_id") or str(uuid.uuid4())
    no_notify_with_send_keys = bool(params.get("no_notify_with_send_keys", False))
    no_registry = bool(params.get("no_registry", False))
    cwd = params.get("cwd")
    
    if not (session and tmux_pane and wrapper_pid and tmux_socket):
        raise ValueError("Invalid params")
        
    agents = state.get_all_agents()
    existing_name_for_id = state.get_agent_name_by_id(agent_id)

    # Remove any existing agent for the same pane to prevent duplicates.
    for existing_name, info in list(agents.items()):
        if info.get("tmux_pane") == tmux_pane and existing_name != existing_name_for_id:
            logging.info(f"Removing existing agent {existing_name} for pane {tmux_pane} before re-registering")
            state.delete_agent(existing_name)
            agents = state.get_all_agents()

    if existing_name_for_id:
        agent_name = existing_name_for_id
    else:
        agent_name = _generate_unique_agent_name(name, session, is_register=True)
        
    existing_info = state.get_agent(existing_name_for_id) if existing_name_for_id else None
    state.set_agent(agent_name, {
        **(existing_info or {}),
        "session": session,
        "tmux_pane": tmux_pane,
        "wrapper_pid": wrapper_pid,
        "tmux_socket": tmux_socket,
        "pid": (existing_info or {}).get("pid"),
        "status": (existing_info or {}).get("status", "idle"),
        "waiting_approval": (existing_info or {}).get("waiting_approval", False),
        "agent_id": agent_id,
        "uuid": agent_id,
        "agent_type": agent_type or (existing_info or {}).get("agent_type", "unknown"),
        "agent_cmd": agent_cmd or (existing_info or {}).get("agent_cmd", "unknown"),
        "model_type": model_type,
        "no_notify_with_send_keys": no_notify_with_send_keys,
        "no_registry": no_registry,
        "cwd": cwd or (existing_info or {}).get("cwd"),
        "last_heartbeat": time.time(),
        "recovered_at": None,
        "pending_notifications": (existing_info or {}).get("pending_notifications", [])
    })
    
    _best_effort_update_tmux_metadata(tmux_pane, agent_name, agent_id, agent_type, agent_cmd, tmux_socket, no_notify_with_send_keys, no_registry)
    registered_info = state.get_agent(agent_name) or {}
    state.publish_event("agent_registered", _agent_event_payload(agent_name, registered_info))
    
    return agent_name

def _fetch_registry_agents_for_list() -> dict:
    """Best-effort fetch of remote agents from configured registries."""
    remote_agents = {}
    for client in registry_client.load_registry_clients():
        status, body = client.fetch_agents()
        if status != 200:
            continue
        registry_name = client.name or "default"
        for agent in (body or {}).get("agents") or []:
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
            remote_agents[key] = {
                **agent,
                "name": key,
                "scope": "remote",
                "target_address": key,
                "registry_name": registry_name,
                "model_type": state.normalize_model_type(agent.get("model_type"), agent.get("agent_type"), agent.get("agent_cmd")),
            }
    return remote_agents


def _agent_event_payload(name: str, info: dict) -> dict:
    return {
        "target_agent_id": info.get("agent_id") or info.get("uuid"),
        "target_agent_name": name,
        "hostname": info.get("hostname") or registry_client.HOSTNAME,
        "tracker_id": info.get("tracker_id") or registry_client.TRACKER_ID,
        "status": info.get("status", "unknown"),
        "model_type": state.normalize_model_type(info.get("model_type"), info.get("agent_type"), info.get("agent_cmd")),
        "agent_type": info.get("agent_type"),
        "agent_cmd": info.get("agent_cmd"),
    }


def _local_agent_list_row(name: str, info: dict) -> dict:
    return {
        **info,
        "name": info.get("name") or name,
        "scope": "local",
        "hostname": info.get("hostname") or registry_client.HOSTNAME,
        "tracker_id": info.get("tracker_id") or registry_client.TRACKER_ID,
        "target_address": info.get("target_address") or name,
        "model_type": state.normalize_model_type(info.get("model_type"), info.get("agent_type"), info.get("agent_cmd")),
    }


def _merge_registry_agents_for_list(local_agents: dict, remote_agents: dict) -> dict:
    merged = {name: _local_agent_list_row(name, info) for name, info in (local_agents or {}).items()}
    local_agent_ids = {info.get("agent_id") for info in (local_agents or {}).values() if info.get("agent_id")}
    for name, info in (remote_agents or {}).items():
        if info.get("agent_id") in local_agent_ids:
            continue
        merged[name] = info
    return merged


def handle_list(params: dict, caller_pid: int = None) -> dict:
    """Returns agents in state, marking the caller if identified.

    Remote registry agents are opt-in so status-bar callers keep rendering only
    local active agents.
    """
    agents = state.get_all_agents()
    if params.get("include_remote"):
        agents = _merge_registry_agents_for_list(agents, _fetch_registry_agents_for_list())
    else:
        agents = {name: _local_agent_list_row(name, info) for name, info in (agents or {}).items()}
    caller_name = _identify_agent(params, caller_pid)
    
    detection_status = permission_detection.detection_status_snapshot()
    for name, detection in detection_status.items():
        if name in agents:
            agents[name]["detection"] = detection

    if caller_name and caller_name in agents:
        agents[caller_name]["is_this_me"] = True
        
    return agents



def _publish_message_notified(info: dict, agent_name: str, pending_item):
    sender_name = pending_item.get("sender") if isinstance(pending_item, dict) else pending_item
    message_id = pending_item.get("message_id") if isinstance(pending_item, dict) else None
    sender_agent_id = pending_item.get("sender_agent_id") if isinstance(pending_item, dict) else None
    sender_tracker_id = pending_item.get("sender_tracker_id") if isinstance(pending_item, dict) else None
    state.publish_event("message_notified", {
        "target_agent_id": info.get("agent_id"),
        "target_agent_name": agent_name,
        "sender": sender_name or "unknown",
        "message_id": message_id,
    })
    if sender_tracker_id and sender_tracker_id != registry_client.TRACKER_ID:
        registry_client.publish_tracker_event(sender_tracker_id, "message_notified", {
            "message_id": message_id,
            "sender_agent_id": sender_agent_id,
            "receiver_agent_id": info.get("agent_id"),
            "receiver_agent_name": agent_name,
        })




def handle_ensure_mailbox(params: dict) -> dict:
    """Ensures a local UI/mailbox identity exists without tmux pane control.

    Native frontends such as the Electron communicator need a stable inbox
    identity but should not masquerade as a controllable coding-agent pane.
    Mailbox identities are no-notify records that can be registry-visible for
    normal cross-host messages but cannot receive direct pane input.
    """
    name = params.get("agent_name") or params.get("name")
    if not isinstance(name, str) or not name.strip() or "/" in name or name.startswith("registry:"):
        raise ValueError("agent_name must be a local name")
    name = name.strip()
    agent_id = params.get("agent_id")
    if agent_id is not None and not isinstance(agent_id, str):
        raise ValueError("agent_id must be a string")
    if not agent_id:
        agent_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{registry_client.TRACKER_ID}:mailbox:{name}"))

    existing = state.get_agent(name) or {}
    preserve_pane = bool(params.get("preserve_pane", False)) and bool(existing.get("tmux_pane"))
    pane_fields = {
        "session": existing.get("session") if preserve_pane else None,
        "tmux_pane": existing.get("tmux_pane") if preserve_pane else None,
        "wrapper_pid": existing.get("wrapper_pid") if preserve_pane else None,
        "tmux_socket": existing.get("tmux_socket") if preserve_pane else None,
        "pid": existing.get("pid") if preserve_pane else None,
    }
    state.set_agent(name, {
        **existing,
        **pane_fields,
        "status": existing.get("status", "idle"),
        "waiting_approval": existing.get("waiting_approval", False),
        "agent_id": existing.get("agent_id") or agent_id,
        "uuid": existing.get("uuid") or existing.get("agent_id") or agent_id,
        "agent_type": "agent-communicator-ui",
        "agent_cmd": existing.get("agent_cmd", "agent-communicator"),
        "model_type": state.normalize_model_type("agent-communicator-ui", "agent-communicator-ui", existing.get("agent_cmd", "agent-communicator")),
        "no_notify_with_send_keys": True,
        "no_registry": existing.get("no_registry", params.get("no_registry", False)) if preserve_pane else params.get("no_registry", False),
        "direct_input_disabled": True,
        "cwd": params.get("cwd") or existing.get("cwd"),
        "last_heartbeat": time.time(),
        "recovered_at": None,
        "pending_notifications": existing.get("pending_notifications", []),
        "is_mailbox": True,
    })
    info = state.get_agent(name) or {}
    return {"name": name, "agent_id": info.get("agent_id"), "uuid": info.get("uuid")}


def handle_update_agent(params: dict, caller_pid: int = None) -> bool:
    """Updates agent state fields."""
    agent_name = _identify_agent(params, caller_pid)
    if not agent_name:
        raise ValueError("Agent not identified")
        
    kwargs = {k: v for k, v in params.items() if k not in ["agent_id", "agent_name", "tmux_pane"]}
    old_info = state.get_agent(agent_name) or {}
    old_status = old_info.get("status")
    if state.update_agent(agent_name, **kwargs):
        info = state.get_agent(agent_name) or {}
        if "status" in kwargs:
            registry_client.push_agent_update(info["agent_id"], kwargs["status"])
            if kwargs.get("status") != old_status:
                state.publish_event("agent_status_changed", {**_agent_event_payload(agent_name, info), "old_status": old_status})
        return True
    raise ValueError(f"Agent '{agent_name}' not found")


def handle_heartbeat(params: dict, caller_pid: int = None) -> bool:
    """Records a liveness heartbeat for an identified agent."""
    agent_name = _identify_agent(params, caller_pid)
    if not agent_name:
        raise ValueError("Agent not identified")

    old_info = state.get_agent(agent_name) or {}
    old_status = old_info.get("status")
    kwargs = {k: v for k, v in params.items() if k not in ["agent_id", "agent_name"]}
    kwargs["last_heartbeat"] = time.time()
    kwargs["recovered_at"] = None
    if state.update_agent(agent_name, **kwargs):
        if "status" in kwargs and kwargs.get("status") != old_status:
            info = state.get_agent(agent_name) or {}
            state.publish_event("agent_status_changed", {**_agent_event_payload(agent_name, info), "old_status": old_status})
        return True
    raise ValueError(f"Agent '{agent_name}' not found")

def handle_rename(params: dict, caller_pid: int = None) -> bool:
    """Renames an agent with safety checks. 
    Users can rename themselves by providing new_name.
    Renaming others requires old_name, new_name, and force=True.
    """
    old_name = params.get("old_name")
    new_name = params.get("new_name")
    force = params.get("force", False)
    
    caller_name = _identify_agent(params, caller_pid)
    
    if not caller_name and not force:
        raise ValueError("Could not identify caller. Use --force and provide old_name to rename.")

    # If old_name is not provided, assume self-rename
    if not old_name:
        old_name = caller_name
        
    if not old_name or not new_name:
        raise ValueError("Invalid params: new_name is required.")

    if old_name != caller_name and not force:
        raise ValueError(f"Cannot rename '{old_name}' (you are '{caller_name}'). Use --force to override.")
        
    logging.info(f"Attempting to rename agent from {old_name} to {new_name}")
    if state.rename_agent(old_name, new_name):
        info = state.get_agent(new_name)
        tmux_pane = info.get("tmux_pane")
        tmux_socket = info.get("tmux_socket")
        logging.info(f"Renamed {old_name} to {new_name} in state. Updating tmux pane {tmux_pane}")
        if tmux_pane:
            try:
                tmux_util.set_agent_name_sync(tmux_pane, new_name, tmux_socket)
                tmux_util.set_pane_title_sync(tmux_pane, new_name, tmux_socket)
            except Exception as e:
                logging.error(f"Failed to update tmux pane for {new_name}: {e}")
        return True
    logging.error(f"Failed to rename {old_name} to {new_name}. Agent not found or new name exists.")
    raise ValueError("Agent not found or new name exists")

def handle_unregister(params: dict, caller_pid: int = None) -> bool:
    """Unregisters an agent from state."""
    agent_name = _identify_agent(params, caller_pid)
    if not agent_name:
        # Try to find by tmux_pane if provided
        tmux_pane = params.get("tmux_pane")
        if tmux_pane:
            agent_name = state.get_agent_name_by_pane(tmux_pane)
                    
    if not agent_name:
        raise ValueError("Agent not identified")
        
    info = state.get_agent(agent_name)
    if not info:
        raise ValueError(f"Agent '{agent_name}' not found")
        
    logging.info(f"Unregistering agent: {agent_name}")
    
    # Remove inbox file
    uuid_str = info.get("uuid") or agent_name
    inbox_file = os.path.join(state.INBOX_DIR, f"{uuid_str}.inbox")
    if os.path.exists(inbox_file):
        try:
            os.remove(inbox_file)
        except OSError as e:
            logging.error(f"Failed to remove inbox file for {agent_name}: {e}")
            
    state.publish_event("agent_unregistered", _agent_event_payload(agent_name, info))
    state.delete_agent(agent_name)
    return True

def _resolve_target_agent_name(params: dict) -> str | None:
    """Resolves a target agent by explicit agent_id first, then display name."""
    agent_id = params.get("agent_id")
    if agent_id:
        resolved_name = state.get_agent_name_by_id(agent_id)
        if resolved_name:
            return resolved_name

    agent_name = params.get("agent_name")
    if agent_name and state.get_agent(agent_name):
        return agent_name

    return None


def handle_spin_agent(params: dict, caller_pid: int = None) -> str:
    """Spins a new agent in a new tmux pane."""
    command = params.get("command")
    directory = params.get("directory")
    name = params.get("name")
    env = params.get("env") or {}

    caller_name = _identify_agent({}, caller_pid) if caller_pid else None
    caller_info = state.get_agent(caller_name) if caller_name else None

    session = params.get("session") or (caller_info or {}).get("session")
    target_pane = params.get("target_pane") or (caller_info or {}).get("tmux_pane")
    tmux_socket = params.get("tmux_socket") or (caller_info or {}).get("tmux_socket")

    if not (session and command and name):
        raise ValueError("Invalid params")

    parent_id = (caller_info or {}).get("agent_id") or (caller_info or {}).get("uuid")
    if parent_id and (env.get("AGENT_ID") == parent_id or env.get("AGENT_UUID") == parent_id or env.get("AGENT_NAME") == caller_name):
        logging.info("Stripping inherited agent identity from spun agent environment for caller %s", caller_name)
        env.pop("AGENT_ID", None)
        env.pop("AGENT_NAME", None)
        env.pop("AGENT_UUID", None)
    for key in ("AGENT_ID", "AGENT_NAME", "AGENT_UUID"):
        if env.get(key) == "":
            env.pop(key, None)

    agent_name = _generate_unique_agent_name(name, session, is_register=False)
    env["SUGGESTED_AGENT_NAME"] = agent_name

    state.set_agent(agent_name, {"status": "spawning", "timestamp": time.time(), "cwd": directory or "unknown"})

    try:
        pane_id = tmux_util.spin_agent(agent_name, command, target_pane, session=session, directory=directory, env=env, tmux_socket=tmux_socket)
        placeholder_updates = {}
        if session:
            placeholder_updates["session"] = session
        if pane_id:
            placeholder_updates["tmux_pane"] = pane_id
        if placeholder_updates:
            state.update_agent(agent_name, **placeholder_updates)
        return agent_name
    except Exception as e:
        state.delete_agent(agent_name)
        raise RuntimeError(f"Failed to spin agent: {e}")

def remote_message_focus_enabled() -> bool:
    """Whether remote-origin inbox delivery should best-effort focus target pane.

    Conservative Broccoli default: disabled unless explicitly enabled.
    """
    return os.environ.get("BROCCOLI_COMMS_FOCUS_REMOTE_MESSAGES", "").lower() in {"1", "true", "yes", "on"}


def _maybe_focus_remote_delivery(info: dict, current_name: str, msg_obj: dict) -> None:
    sender_tracker_id = msg_obj.get("sender_tracker_id")
    if not sender_tracker_id or sender_tracker_id == registry_client.TRACKER_ID:
        return
    if not remote_message_focus_enabled():
        return
    tmux_pane = info.get("tmux_pane")
    tmux_socket = info.get("tmux_socket")
    if not tmux_pane or not tmux_socket:
        logging.warning("Skipping remote message focus for %s: missing registered pane or tmux socket", current_name)
        return
    try:
        tmux_util.focus_pane(tmux_pane, session=info.get("session"), socket_path=tmux_socket)
    except Exception as e:
        logging.warning("Best-effort remote message focus failed for %s pane %s: %s", current_name, tmux_pane, e)


def deliver_local_message(target_name_or_id: str, msg_obj: dict, notify_sender: str | None = None, verify: bool = False) -> str:
    """Writes a message to a local agent inbox and triggers/queues notification."""
    msg_id = msg_obj.get("message_id") or str(uuid.uuid4())
    msg_obj["message_id"] = msg_id

    info = state.get_agent(target_name_or_id)
    if not info:
        raise DeliveryTargetNotFound("Target agent not found")

    current_name = state.get_agent_name_by_id(info["agent_id"]) or target_name_or_id
    uuid_str = info.get("uuid") or current_name
    inbox_file = os.path.join(state.INBOX_DIR, f"{uuid_str}.inbox")
    notify_sender = notify_sender or msg_obj.get("sender", "unknown")
    attach_dir = None

    try:
        with _locked_inbox(inbox_file):
            if msg_id and os.path.exists(inbox_file):
                with open(inbox_file, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            if json.loads(line).get("message_id") == msg_id:
                                logging.info(f"Skipping duplicate delivery {msg_id} for {current_name}")
                                return current_name
                        except json.JSONDecodeError:
                            continue

            attachments = []
            if msg_obj.get("attachments"):
                msg_id = msg_id or str(uuid.uuid4())
                attach_dir = os.path.join(state.INBOX_DIR, "attachments", uuid_str, msg_id)
                os.makedirs(attach_dir, exist_ok=True)
                seen_names = set()
                for att in msg_obj["attachments"]:
                    raw_name = att.get("name")
                    safe_name = os.path.basename(raw_name or "")
                    if not safe_name or "content_b64" not in att:
                        raise DeliveryValidationError("invalid attachments")
                    if safe_name in seen_names:
                        raise DeliveryValidationError("duplicate attachment name")
                    seen_names.add(safe_name)
                    try:
                        content = base64.b64decode(att["content_b64"], validate=True)
                    except (binascii.Error, ValueError) as e:
                        raise DeliveryValidationError(f"invalid attachment payload: {e}")
                    path = os.path.join(attach_dir, safe_name)
                    with open(path, "wb") as af:
                        af.write(content)
                    attachments.append({
                        "name": safe_name,
                        "path": path,
                        "content_type": att.get("content_type", "application/octet-stream"),
                        "size": os.path.getsize(path),
                    })
                msg_obj = {**msg_obj, "message_id": msg_id, "attachments": attachments}

            with open(inbox_file, "a") as f:
                f.write(json.dumps(msg_obj) + "\n")

        try:
            state.record_to_matching_group_timelines(notify_sender, current_name, msg_obj)
        except Exception as ge:
            logging.warning("Failed to record observed message to group timelines: %s", ge)

        notification = {
            "target_agent_id": info.get("agent_id"),
            "target_agent_name": current_name,
            "sender": notify_sender,
            "message_id": msg_obj.get("message_id"),
            "has_attachments": bool(msg_obj.get("attachments")),
        }
        state.publish_event("message_delivered", notification)
        if msg_obj.get("sender_tracker_id") and msg_obj.get("sender_tracker_id") != registry_client.TRACKER_ID:
            registry_client.publish_tracker_event(msg_obj.get("sender_tracker_id"), "message_delivered", {
                "message_id": msg_obj.get("message_id"),
                "sender_agent_id": msg_obj.get("sender_agent_id"),
                "receiver_agent_id": info.get("agent_id"),
                "receiver_agent_name": current_name,
            })

        _maybe_focus_remote_delivery(info, current_name, msg_obj)

        pending_item = {
            "sender": notify_sender,
            "message_id": msg_obj.get("message_id"),
            "sender_agent_id": msg_obj.get("sender_agent_id"),
            "sender_tracker_id": msg_obj.get("sender_tracker_id"),
        }
        if info.get("no_notify_with_send_keys", False):
            logging.info(f"Skipping tmux send-keys notification for {current_name} from {notify_sender}")
        else:
            notify_msg = f"New message in inbox from {notify_sender}"
            enable_reliable = os.environ.get("ENABLE_RELIABLE_SEND_KEYS", "true").lower() == "true"
            delivered = False
            if enable_reliable or verify:
                try:
                    logging.info(f"Attempting reliable notification delivery for {current_name} to pane {info['tmux_pane']} (verify={verify})")
                    delivered = tmux_util.send_keys_reliable(info["tmux_pane"], notify_msg, info["tmux_socket"], timeout=5)
                    if delivered:
                        logging.info(f"Reliable notification successfully delivered to {current_name} in pane {info['tmux_pane']}")
                    else:
                        if verify:
                            raise RuntimeError("Notification delivery timed out")
                        logging.warning(f"Reliable notification delivery timed out/failed for {current_name} in pane {info['tmux_pane']}. Falling back to legacy send_keys.")
                except Exception as e:
                    if verify:
                        raise RuntimeError(f"Reliable notification delivery failed: {e}")
                    logging.warning(f"Error during reliable notification delivery: {e}. Falling back to legacy send_keys.")

            if not delivered:
                tmux_util.send_keys(info["tmux_pane"], notify_msg, info["tmux_socket"])
                
            _publish_message_notified(info, current_name, pending_item)
        return current_name
    except DeliveryValidationError:
        if attach_dir and os.path.isdir(attach_dir):
            for root, _, files in os.walk(attach_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)
        raise
    except OSError as e:
        if attach_dir and os.path.isdir(attach_dir):
            for root, _, files in os.walk(attach_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)
        logging.error(f"Failed to write to inbox file for {target_name_or_id}: {e}")
        raise RuntimeError(f"Failed to send message: {e}")


def _resolve_local_target_address(params: dict, allow_remote: bool) -> dict:
    """Resolve local target_address forms while rejecting remote direct-input targets."""
    target_address = params.get("target_address")
    if not target_address or "/" not in target_address:
        return params

    hostname, target = target_address.split("/", 1)
    if ":" in hostname:
        _, hostname = hostname.split(":", 1)
    if hostname not in {"local", LOCAL_HOSTNAME}:
        if allow_remote:
            return params
        raise RuntimeError("remote direct pane input is disabled")
    return {**params, **({"agent_id": target} if _is_uuid(target) else {"agent_name": target})}


def _validate_send_input_payload(params: dict) -> tuple[str, dict]:
    mode = (params.get("input_type") or params.get("mode") or "").lower()
    if mode not in {"text", "keys"}:
        raise ValueError("Invalid params")
    if mode == "text":
        text = params.get("text")
        if not isinstance(text, str) or text == "":
            raise ValueError("text must be a non-empty string")
        max_bytes = int(os.environ.get("AGENT_REMOTE_PANE_INPUT_MAX_TEXT_BYTES", "4096"))
        if len(text.encode("utf-8")) > max_bytes:
            raise ValueError(f"text exceeds max bytes ({max_bytes})")
        submit = params.get("submit", True)
        if not isinstance(submit, bool):
            raise ValueError("submit must be a boolean")
        return mode, {"text": text, "submit": submit}
    keys = params.get("keys")
    if keys is None and params.get("key") is not None:
        keys = [params.get("key")]
    max_keys = int(os.environ.get("AGENT_REMOTE_PANE_INPUT_MAX_KEYS", "16"))
    if isinstance(keys, (list, tuple)) and len(keys) > max_keys:
        raise ValueError(f"keys exceed max count ({max_keys})")
    normalized = tmux_util.normalize_key_tokens(keys)
    return mode, {"keys": normalized}


def _route_remote_send_input(params: dict, caller_pid: int = None) -> dict | None:
    target_address = params.get("target_address")
    if not target_address or "/" not in target_address:
        return None
    registry_name = None
    hostname, target = target_address.split("/", 1)
    if ":" in hostname:
        registry_name, hostname = hostname.split(":", 1)
    if hostname in {"local", LOCAL_HOSTNAME}:
        return None
    if not registry_client.remote_pane_input_send_enabled():
        raise RuntimeError("remote direct pane input is disabled")
    mode, payload = _validate_send_input_payload(params)
    sender_name = _identify_agent(_sender_identification_params(params), caller_pid) or "cli-user"
    sender_info = state.get_agent(params.get("sender_id") or sender_name) or {}
    sender_id = sender_info.get("agent_id") or params.get("sender_id")
    pane_input_id = params.get("pane_input_id") or params.get("request_id") or str(uuid.uuid4())
    request_id = params.get("request_id") or pane_input_id
    if registry_name:
        status, body = registry_client.send_remote_pane_input_to_registry(
            registry_name,
            sender_name,
            sender_id,
            registry_client.TRACKER_ID,
            hostname,
            target,
            mode,
            text=payload.get("text"),
            keys=payload.get("keys"),
            submit=payload.get("submit", True),
            pane_input_id=pane_input_id,
            request_id=request_id,
        )
    else:
        status, body = registry_client.send_remote_pane_input(
            sender_name,
            sender_id,
            registry_client.TRACKER_ID,
            hostname,
            target,
            mode,
            text=payload.get("text"),
            keys=payload.get("keys"),
            submit=payload.get("submit", True),
            pane_input_id=pane_input_id,
            request_id=request_id,
        )
    if status == 202:
        return {"success": True, "queued": True, "mode": mode, "pane_input_id": (body or {}).get("pane_input_id", pane_input_id), "request_id": (body or {}).get("request_id", request_id)}
    raise RuntimeError(f"Remote pane input failed: {(body or {}).get('message', 'unknown error')}")


def _is_mailbox_or_ui_agent(info: dict) -> bool:
    if not info:
        return False
    return bool(info.get("direct_input_disabled")) or bool(info.get("is_mailbox")) or info.get("agent_type") == "agent-communicator-ui"


def handle_send_input(params: dict, caller_pid: int = None) -> dict:
    """Sends direct pane input to a registered agent pane.

    Local input uses the registered/private tmux socket. Remote target_address
    routing is registry-mediated and remains default-disabled behind sender,
    registry, and receiver gates.
    """
    remote_result = _route_remote_send_input(params, caller_pid)
    if remote_result is not None:
        return remote_result
    params = _resolve_local_target_address(params, allow_remote=False)
    agent_name = _resolve_target_agent_name(params)
    try:
        mode, input_payload = _validate_send_input_payload(params)
    except ValueError:
        raise
    if not agent_name:
        raise ValueError("Invalid params")

    info = state.get_agent(agent_name)
    if not info:
        raise ValueError("Target agent not found")
    if _is_mailbox_or_ui_agent(info):
        raise RuntimeError("Target is a Broccoli Comms UI/mailbox; direct pane input is disabled")
    tmux_pane = info.get("tmux_pane")
    tmux_socket = info.get("tmux_socket")
    if not tmux_pane:
        raise RuntimeError("Target agent has no registered tmux pane")
    if not tmux_socket:
        raise RuntimeError("Target agent has no registered tmux socket; refusing to use default tmux")

    current_name = state.get_agent_name_by_id(info.get("agent_id")) or agent_name
    try:
        if mode == "text":
            text = input_payload["text"]
            submit = input_payload["submit"]
            tmux_util.send_literal_text(tmux_pane, text, submit=submit, socket_path=tmux_socket)
            return {"success": True, "target": current_name, "mode": "text", "submitted": submit}
        normalized = input_payload["keys"]
        tmux_util.send_symbolic_keys(tmux_pane, normalized, socket_path=tmux_socket)
        return {"success": True, "target": current_name, "mode": "keys", "keys": normalized}
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to send direct pane input: {e}")


def _sender_identification_params(params: dict) -> dict:
    """Return only explicit sender identity fields safe for sender inference.

    send-message params may also contain target identifiers such as agent_name,
    agent_id, or target_address. Those must never be fed into _identify_agent()
    when resolving the sender.
    """
    result = {}
    if params.get("sender_id"):
        result["sender_id"] = params["sender_id"]
    if params.get("sender_name"):
        result["agent_name"] = params["sender_name"]
    return result


def _sender_metadata(sender_name: str, sender_info: dict, sender_id: str | None) -> dict:
    return {
        "sender_agent_id": sender_id,
        "sender_hostname": registry_client.HOSTNAME,
        "sender_model_type": state.normalize_model_type(sender_info.get("model_type"), sender_info.get("agent_type"), sender_info.get("agent_cmd")),
        "sender_agent_type": sender_info.get("agent_type"),
        "sender_agent_cmd": sender_info.get("agent_cmd"),
        "kind": "text",
    }


def handle_send_message(params: dict, caller_pid: int = None) -> bool:
    """Sends a message locally or routes it remotely via the registry when target_address is hostname-qualified."""
    sender_name = _identify_agent(_sender_identification_params(params), caller_pid) or "cli-user"
    msg = params.get("message")
    attachments = params.get("attachments")
    target_address = params.get("target_address")
    sender_info = state.get_agent(params.get("sender_id") or sender_name) or {}
    sender_id = sender_info.get("agent_id") or params.get("sender_id")
    sender_metadata = _sender_metadata(sender_name, sender_info, sender_id)

    if target_address and "/" in target_address:
        registry_name = None
        hostname, target = target_address.split("/", 1)
         
        logging.info("handle_send_message sender=%s sender_id=%s target_address=%s message_id=%s attachments=%s", sender_name, sender_id, target_address, params.get("message_id"), bool(attachments))
        if ":" in hostname:
            registry_name, hostname = hostname.split(":", 1)
        if hostname not in {"local", LOCAL_HOSTNAME}:
            if registry_name:
                status, body = registry_client.send_remote_message_to_registry(
                    registry_name, sender_name, sender_id, registry_client.TRACKER_ID, hostname, target, msg, attachments, params.get("message_id"), sender_metadata
                )
            else:
                status, body = registry_client.send_remote_message(
                    sender_name,
                    sender_id,
                    registry_client.TRACKER_ID,
                    hostname,
                    target,
                    msg,
                    attachments,
                    params.get("message_id"),
                    sender_metadata,
                )
            if status == 202:
                return True
            raise RuntimeError(f"Remote delivery failed: {(body or {}).get('message', 'unknown error')}")
        params = {**params, **({"agent_id": target} if _is_uuid(target) else {"agent_name": target})}

    agent_name = _resolve_target_agent_name(params)
    if not agent_name or (not msg and not attachments):
        raise ValueError("Invalid params")

    current_name = state.get_agent_name_by_id(state.get_agent(agent_name)["agent_id"])
    warning_msg = None
    if agent_name != current_name:
        warning_msg = f"Note: Agent '{agent_name}' was renamed to '{current_name}'."
        logging.info(warning_msg)

    payload = {
        "sender": sender_name,
        "timestamp": _utc_now_isoformat(),
        "message": msg,
        "attachments": attachments,
        "read": False,
        "message_id": params.get("message_id"),
        **sender_metadata,
        "sender_tracker_id": registry_client.TRACKER_ID,
    }
    logging.info("local delivery payload target=%s sender=%s message_id=%s sender_agent_id=%s sender_tracker_id=%s", agent_name, sender_name, payload.get("message_id"), payload.get("sender_agent_id"), payload.get("sender_tracker_id"))
    verify = params.get("verify", False)
    deliver_local_message(agent_name, payload, sender_name, verify=verify)
    return {"success": True, "warning": warning_msg} if warning_msg else True

def _read_and_update_inbox_file(
    inbox_file: str,
    clear: bool,
    last_n: int = None,
    agent_name: str | None = None,
    agent_info: dict | None = None,
    mark_read: bool = True,
    sender_name: str | None = None,
    sender_agent_id: str | None = None,
    sender_tracker_id: str | None = None,
) -> dict:
    """Reads inbox history and optionally marks returned messages read under a file lock."""
    if not os.path.exists(inbox_file):
        return {"mode": "history", "messages": []}

    try:
        with _locked_inbox(inbox_file):
            all_messages = []
            with open(inbox_file, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            all_messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

            def matches_filters(msg):
                if sender_agent_id and msg.get("sender_agent_id") != sender_agent_id:
                    return False
                if sender_tracker_id:
                    msg_tracker_id = msg.get("sender_tracker_id")
                    if msg_tracker_id != sender_tracker_id:
                        if not (sender_tracker_id == registry_client.TRACKER_ID and not msg_tracker_id):
                            return False
                if sender_name and msg.get("sender") != sender_name:
                    return False
                return True

            candidate_messages = [m for m in all_messages if matches_filters(m)]

            mode = "unread"
            newly_read = []
            if last_n is not None:
                mode = "last_n"
                result_messages = candidate_messages[-last_n:] if last_n > 0 else []
            else:
                result_messages = [m for m in candidate_messages if not m.get("read", False)]
                if not result_messages:
                    mode = "history"
                    result_messages = candidate_messages[-5:]

            if mark_read and mode != "history":
                for msg in result_messages:
                    if not msg.get("read", False):
                        newly_read.append(msg)
                    msg["read"] = True

            if clear:
                remaining = all_messages[-25:] if len(all_messages) > 25 else all_messages
                _atomic_write_inbox(inbox_file, remaining)
            else:
                _atomic_write_inbox(inbox_file, all_messages)

        if agent_name and agent_info:
            for msg in newly_read:
                logging.info("publishing message_read target=%s sender=%s message_id=%s sender_agent_id=%s sender_tracker_id=%s", agent_name, msg.get("sender", "unknown"), msg.get("message_id"), msg.get("sender_agent_id"), msg.get("sender_tracker_id"))
                state.publish_event("message_read", {
                    "target_agent_id": agent_info.get("agent_id"),
                    "target_agent_name": agent_name,
                    "sender": msg.get("sender", "unknown"),
                    "message_id": msg.get("message_id"),
                })
                if msg.get("sender_tracker_id") and msg.get("sender_tracker_id") != registry_client.TRACKER_ID:
                    logging.info("relaying remote message_read back to sender_tracker_id=%s message_id=%s reader=%s", msg.get("sender_tracker_id"), msg.get("message_id"), agent_name)
                    registry_client.publish_tracker_event(msg.get("sender_tracker_id"), "message_read", {
                        "message_id": msg.get("message_id"),
                        "sender_agent_id": msg.get("sender_agent_id"),
                        "reader_agent_id": agent_info.get("agent_id"),
                        "reader_agent_name": agent_name,
                    })
        return {"mode": mode, "messages": result_messages}
    except IOError as e:
        raise RuntimeError(f"Failed to access inbox file: {e}")


def _identify_agent(params: dict, caller_pid: int = None) -> str:
    """Identifies the agent name based on params (id/name/pane) or caller PID."""
    agent_id = params.get("sender_id") or params.get("agent_id")
    if agent_id:
        resolved_name = state.get_agent_name_by_id(agent_id)
        if resolved_name:
            return resolved_name

    agent_name = params.get("agent_name")
    if agent_name:
        return agent_name
        
    tmux_pane = params.get("tmux_pane")
    agents = state.get_all_agents()
    
    if tmux_pane:
        resolved_name = state.get_agent_name_by_pane(tmux_pane)
        if resolved_name:
            return resolved_name
                
    if caller_pid:
        # Trace up the process tree to find a match with wrapper_pid or pid
        curr_pid = caller_pid
        while curr_pid > 1:
            for name, info in agents.items():
                if info.get("wrapper_pid") == curr_pid or info.get("pid") == curr_pid:
                    return name
            try:
                with open(f"/proc/{curr_pid}/status", "r") as f:
                    for line in f:
                        if line.startswith("PPid:"):
                            curr_pid = int(line.split()[1])
                            break
                    else:
                        break
            except (IOError, ValueError):
                break
    return None


def _unread_count_key(msg: dict) -> str | None:
    sender_agent_id = msg.get("sender_agent_id")
    sender_tracker_id = msg.get("sender_tracker_id")
    if sender_agent_id:
        if sender_tracker_id and sender_tracker_id != registry_client.TRACKER_ID:
            return f"remote:{sender_tracker_id}:{sender_agent_id}"
        return f"local:{sender_agent_id}"
    sender = str(msg.get("sender") or "").strip()
    if sender:
        return f"sender:{sender}"
    return None


def handle_get_unread_counts(params: dict, caller_pid: int = None) -> dict:
    """Counts unread messages in an agent inbox by stable sender conversation keys."""
    agent_name = _identify_agent(params, caller_pid)
    if not agent_name:
        raise RPCStructuredError("Agent not identified. Provide agent_name or run from an agent pane.", {
            "error_code": "agent_not_identified",
            "operation": "get_unread_counts",
            "retryable": True,
        })

    info = state.get_agent(agent_name)
    if not info:
        raise RPCStructuredError(f"Agent '{agent_name}' not found", {
            "error_code": "agent_not_found",
            "agent": agent_name,
            "hostname": registry_client.HOSTNAME,
            "operation": "get_unread_counts",
            "retryable": True,
        }, code=-32004)

    uuid_str = info.get("uuid") or agent_name
    inbox_file = os.path.join(state.INBOX_DIR, f"{uuid_str}.inbox")
    counts = {}
    total = 0
    if not os.path.exists(inbox_file):
        return {"counts": counts, "total": total}
    try:
        with _locked_inbox(inbox_file):
            with open(inbox_file, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("read", False):
                        continue
                    key = _unread_count_key(msg)
                    if not key:
                        continue
                    counts[key] = counts.get(key, 0) + 1
                    total += 1
        return {"counts": counts, "total": total}
    except IOError as e:
        raise RuntimeError(f"Failed to access inbox file: {e}")


def handle_get_inbox(params: dict, caller_pid: int = None) -> dict:
    """Handles get_inbox RPC call by reading directly from the inbox file."""
    clear = params.get("clear", False)
    mark_read = params.get("mark_read", True)
    sender_name = params.get("sender_name")
    sender_agent_id = params.get("sender_agent_id")
    sender_tracker_id = params.get("sender_tracker_id")
    last_n = params.get("last_n")

    if not isinstance(mark_read, bool):
        raise ValueError("mark_read must be a boolean")
    if sender_name is not None and not isinstance(sender_name, str):
        raise ValueError("sender_name must be a string")
    if sender_agent_id is not None and not isinstance(sender_agent_id, str):
        raise ValueError("sender_agent_id must be a string")
    if sender_tracker_id is not None and not isinstance(sender_tracker_id, str):
        raise ValueError("sender_tracker_id must be a string")
    
    if last_n is not None:
        try:
            last_n = int(last_n)
        except ValueError:
            raise ValueError("last_n must be an integer")
            
    agent_name = _identify_agent(params, caller_pid)
    if not agent_name:
        raise RPCStructuredError("Agent not identified. Provide agent_name or run from an agent pane.", {
            "error_code": "agent_not_identified",
            "operation": "get_inbox",
            "retryable": True,
        })
        
    info = state.get_agent(agent_name)
    if not info:
        raise RPCStructuredError(f"Agent '{agent_name}' not found", {
            "error_code": "agent_not_found",
            "agent": agent_name,
            "hostname": registry_client.HOSTNAME,
            "operation": "get_inbox",
            "retryable": True,
        }, code=-32004)
        
    uuid_str = info.get("uuid") or agent_name
    inbox_file = os.path.join(state.INBOX_DIR, f"{uuid_str}.inbox")
            
    return _read_and_update_inbox_file(
        inbox_file,
        clear,
        last_n,
        agent_name,
        info,
        mark_read=mark_read,
        sender_name=sender_name,
        sender_agent_id=sender_agent_id,
        sender_tracker_id=sender_tracker_id,
    )


def handle_get_group_timeline(params: dict) -> dict:
    """Handles get_group_timeline RPC call by reading directly from the group's cached timeline file."""
    group_id = params.get("group_id")
    last_n = params.get("last_n", 200)

    if not group_id:
        raise ValueError("group_id is required")
    if not isinstance(group_id, str):
        raise ValueError("group_id must be a string")

    if last_n is not None:
        try:
            last_n = int(last_n)
            if last_n <= 0:
                raise ValueError("last_n must be a positive integer")
        except ValueError:
            raise ValueError("last_n must be a positive integer")

    messages = state.read_group_timeline(group_id, last_n)
    return {"messages": messages}


def _delegate_group_watch_to_remote_trackers(watch_id: str, group_id: str, members: list[str], lease_seconds: float, include_body: bool) -> None:
    """Delegates group watch request to active remote trackers over the registry."""
    status, body = registry_client.fetch_trackers()
    if status != 200:
        logging.warning("Failed to fetch active trackers for group watch delegation")
        return

    trackers = body.get("trackers") or []
    remote_hosts = set()
    for m in members:
        norm = state.normalize_group_member(m)
        host = norm.get("hostname")
        if host and host != registry_client.HOSTNAME:
            remote_hosts.add(host)

    for host in remote_hosts:
        target_tid = None
        for t in trackers:
            if t.get("hostname") == host:
                target_tid = t.get("tracker_id")
                break

        if target_tid:
            try:
                registry_client.publish_tracker_event(target_tid, "watch_group_request", {
                    "watch_id": watch_id,
                    "group_id": group_id,
                    "members": members,
                    "include_body": include_body,
                    "lease_seconds": lease_seconds,
                    "reply_to_tracker_id": registry_client.TRACKER_ID
                })
                logging.info("delegated watch_group_request to remote tracker host=%s tid=%s", host, target_tid)
            except Exception as e:
                logging.warning("failed to delegate group watch to host %s: %s", host, e)


def handle_update_watchlist(params: dict) -> bool:
    """Handles update_watchlist RPC call supporting group watch mode with expiries."""
    watch_id = params.get("watch_id")
    mode = params.get("mode", "standard")
    lease_seconds = params.get("lease_seconds", 120)

    if not watch_id:
        raise ValueError("watch_id is required")
    if not isinstance(watch_id, str):
        raise ValueError("watch_id must be a string")

    try:
        lease_seconds = float(lease_seconds)
    except ValueError:
        raise ValueError("lease_seconds must be a number")

    if mode == "group":
        group_id = params.get("group_id")
        members = params.get("members", [])
        include_body = params.get("include_body", True)

        if not group_id:
            raise ValueError("group_id is required for group watch mode")
        if not isinstance(group_id, str):
            raise ValueError("group_id must be a string")
        if not isinstance(members, list):
            raise ValueError("members must be a list of strings")

        state.update_group_watch(watch_id, group_id, members, lease_seconds, include_body)
        
        # Asynchronously delegate watch requests to remote trackers
        threading.Thread(
            target=_delegate_group_watch_to_remote_trackers,
            args=(watch_id, group_id, members, lease_seconds, include_body),
            daemon=True
        ).start()
        return True
    else:
        watchlist = params.get("watchlist", [])
        state.update_watchlist_lease(watch_id, watchlist, lease_seconds)
        return True


def handle_wait_events(params: dict, caller_pid: int = None) -> dict:
    """Best-effort cursored, lease-bound event long-poll or legacy filters-based poll."""
    try:
        cursor = int(params.get("cursor", params.get("since", 0)) if params.get("cursor", params.get("since")) is not None else 0)
        timeout = float(params.get("timeout", 25.0) if params.get("timeout") is not None else 25.0)
    except (TypeError, ValueError):
        raise ValueError("cursor/since must be an integer and timeout must be a number")
    if cursor < 0 or timeout < 0:
        raise ValueError("cursor/since and timeout must be non-negative")

    client_id = params.get("client_id")
    watch_list = params.get("watch_list")
    lease_seconds = params.get("lease_seconds")
    scope = params.get("scope", "narrow")
    
    if client_id:
        if not isinstance(client_id, str):
            raise ValueError("client_id must be a string")
        if watch_list is not None and not isinstance(watch_list, list):
            raise ValueError("watch_list must be a list of strings")
        if not isinstance(scope, str) or scope not in {"narrow", "broad"}:
            raise ValueError("scope must be narrow or broad")
            
        if scope == "broad" and not REMOTE_BROAD_WATCH_ENABLED:
            raise ValueError("Broad passive remote observation is disabled on this tracker")

        if lease_seconds is not None:
            try:
                lease_seconds = float(lease_seconds)
            except ValueError:
                raise ValueError("lease_seconds must be a number")
        else:
            lease_seconds = 60.0  # Default lease to 60 seconds if not specified
            
        # Atomically register/renew client lease
        state.update_watchlist_lease(client_id, watch_list or [], lease_seconds)

        # Classify local vs remote watched targets
        remote_watchlist = [item for item in (watch_list or []) if "/" in item]
        if remote_watchlist:
            try:
                registry_client.set_remote_watch_leases(client_id, remote_watchlist, lease_seconds, scope=scope)
            except Exception as e:
                logging.warning(f"Failed to delegate remote watch lease to registry: {e}")
        else:
            try:
                registry_client.clear_remote_watch_leases(client_id)
            except Exception as e:
                logging.debug(f"Failed to clear remote watch lease on registry: {e}")

    # Enforce buffer queue eviction checks
    with state.event_lock:
        oldest_seq = state.events[0]["seq"] if state.events else state.event_sequence_id
        if cursor > 0 and cursor < oldest_seq - 1:
            raise CursorExpiredError("cursor_expired")

    # Extract backward-compatibility filters if client_id not used
    filters = None
    if not client_id:
        filters = {
            key: params[key]
            for key in ("target_agent_id", "target_agent_name")
            if params.get(key)
        }

    return state.wait_events(since=cursor, timeout=timeout, filters=filters, client_id=client_id, watch_list=watch_list)


def _read_registry_status() -> dict:
    try:
        with open(registry_client.STATUS_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def handle_tracker_info(params: dict) -> dict:
    """Returns this tracker's registry identity and UI-friendly health snapshot."""
    agents = state.get_all_agents()
    online_statuses = {"running", "active", "online", "idle", "ready"}
    online_agents = sum(1 for info in agents.values() if str(info.get("status", "")).lower() in online_statuses)
    registry_status = _read_registry_status()
    registries = [{**value, "name": name} for name, value in (registry_status.get("registries") or {}).items()]
    remote_tracker_count = 0
    online_remote_tracker_count = 0
    try:
        tracker_status, tracker_body = registry_client.fetch_trackers()
        if tracker_status == 200:
            trackers = (tracker_body or {}).get("trackers") or []
            remote_tracker_count = len([t for t in trackers if t.get("tracker_id") != registry_client.TRACKER_ID])
            online_remote_tracker_count = len([t for t in trackers if t.get("tracker_id") != registry_client.TRACKER_ID and t.get("status") == "active"])
    except Exception:
        pass
    status = "ok"
    if registry_status and not registry_status.get("connected", False):
        status = "degraded"
    return {
        "hostname": registry_client.HOSTNAME,
        "tracker_id": registry_client.TRACKER_ID,
        "http_port": registry_client.HTTP_PORT,
        "status": status,
        "agent_count": len(agents),
        "online_agent_count": online_agents,
        "registry_connected": registry_status.get("connected"),
        "registries": registries,
        "remote_tracker_count": remote_tracker_count,
        "online_remote_tracker_count": online_remote_tracker_count,
    }


def handle_whoami(params: dict, caller_pid: int = None) -> dict:
    """Returns information about the calling agent."""
    agent_name = _identify_agent(params, caller_pid)
    if not agent_name:
        raise ValueError("Agent not identified. Run from an agent pane or process.")
        
    info = state.get_agent(agent_name)
    if not info:
        raise ValueError(f"Agent '{agent_name}' not found in state.")
        
    return {
        "name": agent_name,
        "agent_id": info.get("agent_id") or info.get("uuid"),
        "uuid": info.get("uuid"),
        "pid": info.get("pid"),
        "pane_id": info.get("tmux_pane")
    }


def handle_capture_pane(params: dict, caller_pid: int = None) -> dict:
    """Captures visible text and details for a specified agent or tmux pane."""
    last_lines = params.get("last_lines", _default_capture_pane_lines())
    if last_lines is not None:
        try:
            last_lines = int(last_lines)
        except ValueError:
            raise ValueError("last_lines must be an integer")
        
        # Enforce safety bounds: cap last_lines at 1000 and set floor at 1
        if last_lines > 1000:
            logging.info(f"Capping requested last_lines={last_lines} to 1000 for safety.")
            last_lines = 1000
        elif last_lines <= 0:
            last_lines = 1
            
    include_ansi = bool(params.get("include_ansi", False))

    agent_name = None
    agent_id = None
    tmux_pane = params.get("tmux_pane") or params.get("pane")
    tmux_socket = params.get("tmux_socket")
    session = None

    # Try to resolve via agent_name or agent_id
    resolved_agent_name = _resolve_target_agent_name(params)
    if resolved_agent_name:
        agent_name = resolved_agent_name
        info = state.get_agent(agent_name)
        if info:
            agent_id = info.get("agent_id")
            tmux_pane = tmux_pane or info.get("tmux_pane")
            tmux_socket = tmux_socket or info.get("tmux_socket")
            session = info.get("session")
    
    # If no agent was resolved but we have a tmux_pane, look up if there is a matching agent.
    if not agent_name and tmux_pane:
        resolved_agent_name = state.get_agent_name_by_pane(tmux_pane)
        if resolved_agent_name:
            agent_name = resolved_agent_name
            info = state.get_agent(agent_name)
            if info:
                agent_id = info.get("agent_id")
                tmux_socket = tmux_socket or info.get("tmux_socket")
                session = info.get("session")

    # If we still don't have a tmux_pane, identify the caller agent (self-capture)
    if not tmux_pane:
        caller_name = _identify_agent(params, caller_pid)
        if caller_name:
            agent_name = caller_name
            info = state.get_agent(agent_name)
            if info:
                agent_id = info.get("agent_id")
                tmux_pane = info.get("tmux_pane")
                tmux_socket = tmux_socket or info.get("tmux_socket")
                session = info.get("session")

    if not tmux_pane:
        raise ValueError("Target agent or tmux pane could not be resolved")

    # Query session info if not already retrieved
    if not session:
        pane_info = tmux_util.get_pane_info(tmux_pane, tmux_socket)
        if pane_info:
            session = pane_info.get("session")

    # Query copy-mode status
    copy_mode = tmux_util.is_pane_in_copy_mode(tmux_pane, tmux_socket)

    # Capture visible text with graceful failure handling
    try:
        content = tmux_util.capture_pane_visible_text(
            tmux_pane,
            last_lines=last_lines,
            socket_path=tmux_socket,
            include_ansi=include_ansi
        )
    except Exception as e:
        raise RuntimeError(f"Failed to capture pane visible text buffer: {e}")

    captured_at = _utc_now_isoformat()

    return {
        "agent_name": agent_name,
        "agent_id": agent_id,
        "tmux_pane": tmux_pane,
        "session": session,
        "copy_mode": copy_mode,
        "captured_at": captured_at,
        "lines_requested": last_lines,
        "content": content
    }


def handle_publish_tracker_event(params: dict) -> dict:
    target_tracker_id = params.get("target_tracker_id")
    event_type = params.get("event_type")
    payload = params.get("payload")
    if not target_tracker_id or not event_type or not payload:
        raise ValueError("target_tracker_id, event_type, and payload are required")

    status = registry_client.publish_tracker_event(target_tracker_id, event_type, payload)
    if status in (200, 202):
        return {"success": True}
    raise RuntimeError(f"Failed to publish tracker event: status {status}")


def handle_list_trackers(params: dict) -> list[dict]:
    """Fetches registered trackers and configs from the registry."""
    status, body = registry_client.fetch_trackers()
    if status == 200:
        return body.get("trackers") or []
    raise RuntimeError(f"Failed to list trackers from registry: status {status}")


dispatcher = {
    "register": handle_register,
    "ensure_mailbox": handle_ensure_mailbox,
    "list": handle_list,
    "update_agent": handle_update_agent,
    "heartbeat": handle_heartbeat,
    "rename": handle_rename,
    "spin_agent": handle_spin_agent,
    "send_message": handle_send_message,
    "send_input": handle_send_input,
    "get_inbox": handle_get_inbox,
    "get_unread_counts": handle_get_unread_counts,
    "get_group_timeline": handle_get_group_timeline,
    "update_watchlist": handle_update_watchlist,
    "wait_events": handle_wait_events,
    "tracker_info": handle_tracker_info,
    "whoami": handle_whoami,
    "unregister": handle_unregister,
    "publish_tracker_event": handle_publish_tracker_event,
    "list_trackers": handle_list_trackers,
    "capture_pane": handle_capture_pane
}

def handle_client(conn: socket.socket) -> None:
    """Handles a single client connection, reading JSON-RPC request and sending response."""
    try:
        conn.settimeout(2.0)
        
        # Try to get peer credentials (PID)
        caller_pid = None
        try:
            # SO_PEERCRED returns (pid, uid, gid) as 3 integers
            creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
            caller_pid, _, _ = struct.unpack('3i', creds)
        except Exception as e:
            logging.debug(f"Failed to get SO_PEERCRED: {e}")

        data = b""
        while True:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            data += chunk
            
        if not data:
            return
            
        try:
            req = json.loads(data.decode())
        except json.JSONDecodeError:
            return
            
        method = req.get("method")
        params = req.get("params", {})
        req_id = req.get("id")
        
        result = None
        error = None
        
        handler = dispatcher.get(method)
        if handler:
            try:
                # Pass caller_pid to handlers that might need it
                if method in ["get_inbox", "update_agent", "heartbeat", "send_message", "send_input", "wait_events", "whoami", "list", "rename", "unregister", "spin_agent", "capture_pane"]:
                    result = handler(params, caller_pid=caller_pid)
                else:
                    result = handler(params)
            except CursorExpiredError as e:
                error = {"code": -32001, "message": "cursor_expired"}
            except RPCStructuredError as e:
                error = {"code": e.code, "message": str(e), "data": e.data}
            except ValueError as e:
                error = {"code": -32602, "message": str(e)}
            except RuntimeError as e:
                error = {"code": -32603, "message": str(e)}
            except Exception as e:
                error = {"code": -32603, "message": f"Internal error: {e}"}
        else:
            error = {"code": -32601, "message": "Method not found"}
            
        resp = {"jsonrpc": "2.0", "id": req_id}
        if error:
            resp["error"] = error
        else:
            resp["result"] = result
            
        conn.sendall(json.dumps(resp).encode())
    except (socket.error, socket.timeout) as e:
        logging.error(f"Socket error handling client: {e}")
    except Exception as e:
        logging.error(f"Unexpected error handling client: {e}")
    finally:
        conn.close()
