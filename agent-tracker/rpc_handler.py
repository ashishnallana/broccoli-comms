import json
import logging
import socket
import state
import tmux_util
import registry_client
import permission_detection
import datetime
import time
import threading
import uuid
import struct

import config
from handlers import pane_capture
from handlers import inbox_handlers
from handlers import agent_handlers
from handlers import messaging_handlers

BUFFER_SIZE = 4096
LOCAL_HOSTNAME = config.get("tracker", "hostname", socket.gethostname())
REMOTE_BROAD_WATCH_ENABLED = config.get("tracker", "broad_watch_enabled", False)


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


DeliveryTargetNotFound = messaging_handlers.DeliveryTargetNotFound
DeliveryValidationError = messaging_handlers.DeliveryValidationError


def _publish_message_notified(info: dict, agent_name: str, pending_item):
    return messaging_handlers._publish_message_notified(info, agent_name, pending_item)


def _resolve_target_agent_name(params: dict) -> str | None:
    return messaging_handlers._resolve_target_agent_name(params)


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
    return messaging_handlers.remote_message_focus_enabled()


def _maybe_focus_remote_delivery(info: dict, current_name: str, msg_obj: dict) -> None:
    return messaging_handlers._maybe_focus_remote_delivery(info, current_name, msg_obj)


def deliver_local_message(target_name_or_id: str, msg_obj: dict, notify_sender: str | None = None, verify: bool = False) -> str:
    return messaging_handlers.deliver_local_message(target_name_or_id, msg_obj, notify_sender, verify)


def _resolve_local_target_address(params: dict, allow_remote: bool) -> dict:
    return messaging_handlers._resolve_local_target_address(params, allow_remote)


def _validate_send_input_payload(params: dict) -> tuple[str, dict]:
    return messaging_handlers._validate_send_input_payload(params)


def _route_remote_send_input(params: dict, caller_pid: int = None) -> dict | None:
    return messaging_handlers._route_remote_send_input(params, caller_pid, _identify_agent)


def _is_mailbox_or_ui_agent(info: dict) -> bool:
    return messaging_handlers._is_mailbox_or_ui_agent(info)


def handle_send_input(params: dict, caller_pid: int = None) -> dict:
    return messaging_handlers.handle_send_input(params, caller_pid, _identify_agent)


def _sender_identification_params(params: dict) -> dict:
    return messaging_handlers._sender_identification_params(params)


def _sender_metadata(sender_name: str, sender_info: dict, sender_id: str | None) -> dict:
    return messaging_handlers._sender_metadata(sender_name, sender_info, sender_id)


def handle_send_message(params: dict, caller_pid: int = None) -> bool:
    return messaging_handlers.handle_send_message(params, caller_pid, _identify_agent, deliver_local_message)


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


def _validate_positive_int(value, field_name: str) -> int:
    try:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError(f"{field_name} must be a positive integer")
        return parsed
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer")


def _validate_swarm_name(name: str) -> str:
    if not isinstance(name, str) or not name or not agent_handlers.AGENT_NAME_RE.match(name):
        raise ValueError("swarm name must contain only letters, numbers, dot, underscore, and dash")
    return name


def _swarm_group_id(swarm_name: str) -> str:
    return f"swarm:local:{swarm_name}"


def _swarm_member_row(agent_name: str, info: dict, role: str) -> dict:
    return {
        "name": agent_name,
        "role": role,
        "agent_id": info.get("agent_id") or info.get("uuid"),
        "target_address": info.get("target_address") or agent_name,
        "hostname": info.get("hostname") or registry_client.HOSTNAME,
        "scope": info.get("scope", "local"),
    }


def _agents_for_swarm_derivation(include_remote: bool = True) -> dict:
    agents = {
        name: {**info, "scope": "local"}
        for name, info in state.get_all_agents().items()
    }
    if include_remote:
        try:
            agents.update(agent_handlers._fetch_registry_agents_for_list())
        except Exception as e:
            logging.warning("failed to fetch remote agents for swarm derivation: %s", e)
    return agents


def _derive_swarms(include_remote: bool = True) -> list[dict]:
    swarms: dict[str, dict] = {}
    for agent_name, info in _agents_for_swarm_derivation(include_remote).items():
        for membership in agent_handlers.normalize_swarms(info.get("swarms", [])):
            swarm_name = membership["name"]
            role = membership["role"]
            swarm = swarms.setdefault(swarm_name, {"name": swarm_name, "main": None, "members": [], "warnings": []})
            member = _swarm_member_row(agent_name, info, role)
            swarm["members"].append(member)
            if role == "main":
                swarm["main"] = member
    for swarm in swarms.values():
        mains = [member for member in swarm["members"] if member.get("role") == "main"]
        if not mains:
            swarm["warnings"].append("no main agent configured/running")
        elif len(mains) > 1:
            swarm["warnings"].append("duplicate main agents: " + ", ".join(member.get("name", "") for member in mains))
            swarm["main"] = mains[-1]
    return [swarms[name] for name in sorted(swarms)]


def _find_swarm_or_error(swarm_name: str, include_remote: bool = True) -> dict:
    swarm_name = _validate_swarm_name(swarm_name)
    for swarm in _derive_swarms(include_remote):
        if swarm["name"] == swarm_name:
            return swarm
    raise ValueError(f"swarm {swarm_name!r} not found")


def handle_list_swarms(params: dict) -> dict:
    """Derives swarms from current local and registry-discovered agent metadata."""
    include_remote = bool(params.get("include_remote", True))
    return {"swarms": _derive_swarms(include_remote)}


def handle_get_group_timeline(params: dict) -> dict:
    """Handles get_group_timeline RPC call by reading directly from the group's cached timeline file."""
    group_id = params.get("group_id")
    last_n = params.get("last_n", 200)

    if not group_id:
        raise ValueError("group_id is required")
    if not isinstance(group_id, str):
        raise ValueError("group_id must be a string")

    if last_n is not None:
        last_n = _validate_positive_int(last_n, "last_n")

    messages = state.read_group_timeline(group_id, last_n)
    return {"messages": messages}


def handle_get_swarm_timeline(params: dict) -> dict:
    swarm_name = _validate_swarm_name(params.get("swarm"))
    last_n = params.get("last_n", 200)
    if last_n is not None:
        last_n = _validate_positive_int(last_n, "last_n")
    group_id = _swarm_group_id(swarm_name)
    return {"group_id": group_id, "messages": state.read_group_timeline(group_id, last_n)}


def handle_watch_swarm(params: dict) -> dict:
    include_remote = bool(params.get("include_remote", True))
    swarm = _find_swarm_or_error(params.get("swarm"), include_remote)
    watch_id = params.get("watch_id") or f"swarm:{swarm['name']}"
    if not isinstance(watch_id, str) or not watch_id:
        raise ValueError("watch_id must be a non-empty string")
    try:
        lease_seconds = float(params.get("lease_seconds", 30))
    except (TypeError, ValueError):
        raise ValueError("lease_seconds must be a number")
    include_body = bool(params.get("include_body", True))
    members = [member["target_address"] for member in swarm.get("members", []) if member.get("target_address")]
    group_id = _swarm_group_id(swarm["name"])
    state.update_group_watch(watch_id, group_id, members, lease_seconds, include_body)
    threading.Thread(
        target=_delegate_group_watch_to_remote_trackers,
        args=(watch_id, group_id, members, lease_seconds, include_body),
        daemon=True,
    ).start()
    return {"ok": True, "watch_id": watch_id, "group_id": group_id, "members": members}


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
    "list_swarms": handle_list_swarms,
    "get_group_timeline": handle_get_group_timeline,
    "get_swarm_timeline": handle_get_swarm_timeline,
    "watch_swarm": handle_watch_swarm,
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
