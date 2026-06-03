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

import config
from handlers import pane_capture
from handlers import inbox_handlers
from handlers import agent_handlers
from handlers.inbox_handlers import _locked_inbox

BUFFER_SIZE = 4096
LOCAL_HOSTNAME = config.get("tracker", "hostname", socket.gethostname())
REMOTE_BROAD_WATCH_ENABLED = config.get("tracker", "broad_watch_enabled", False)


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
    return agent_handlers.generate_unique_agent_name(name, session, is_register)


def _agent_event_payload(name: str, info: dict) -> dict:
    return agent_handlers.agent_event_payload(name, info)


def handle_register(params: dict) -> str:
    return agent_handlers.handle_register(params)


def handle_ensure_mailbox(params: dict) -> dict:
    return agent_handlers.handle_ensure_mailbox(params)


def handle_list(params: dict, caller_pid: int = None) -> dict:
    return agent_handlers.handle_list(params, caller_pid, _identify_agent)


def handle_update_agent(params: dict, caller_pid: int = None) -> bool:
    return agent_handlers.handle_update_agent(params, caller_pid, _identify_agent)


def handle_heartbeat(params: dict, caller_pid: int = None) -> bool:
    return agent_handlers.handle_heartbeat(params, caller_pid, _identify_agent)


def handle_rename(params: dict, caller_pid: int = None) -> bool:
    return agent_handlers.handle_rename(params, caller_pid, _identify_agent)


def handle_unregister(params: dict, caller_pid: int = None) -> bool:
    return agent_handlers.handle_unregister(params, caller_pid, _identify_agent)


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
    val = os.environ.get("BROCCOLI_COMMS_FOCUS_REMOTE_MESSAGES")
    if val is not None:
        return val in ("1", "true", "yes")
    return config.get("ui", "focus_remote_messages", False)


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
            enable_reliable = config.get("core", "enable_reliable_send_keys", True)
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
        max_bytes = config.get("registry", "remote_pane_input_max_text_bytes", 4096)
        if len(text.encode("utf-8")) > max_bytes:
            raise ValueError(f"text exceeds max bytes ({max_bytes})")
        submit = params.get("submit", True)
        if not isinstance(submit, bool):
            raise ValueError("submit must be a boolean")
        return mode, {"text": text, "submit": submit}
    keys = params.get("keys")
    if keys is None and params.get("key") is not None:
        keys = [params.get("key")]
    max_keys = config.get("registry", "remote_pane_input_max_keys", 16)
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


def handle_get_unread_counts(params: dict, caller_pid: int = None) -> dict:
    return inbox_handlers.handle_get_unread_counts(
        params,
        caller_pid=caller_pid,
        identify_agent=_identify_agent,
        state=state,
        registry_client=registry_client,
        RPCError=RPCStructuredError
    )


def handle_get_inbox(params: dict, caller_pid: int = None) -> dict:
    return inbox_handlers.handle_get_inbox(
        params,
        caller_pid=caller_pid,
        identify_agent=_identify_agent,
        state=state,
        registry_client=registry_client,
        RPCError=RPCStructuredError
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
    """Wrapper to call the extracted capture pane logic with required dependencies."""
    return pane_capture.handle_capture_pane(
        params,
        caller_pid=caller_pid,
        resolve_agent_name=_resolve_target_agent_name,
        identify_agent=_identify_agent,
        utc_now=_utc_now_isoformat
    )


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
            logging.info("JSON-RPC Request: %s", req)
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
