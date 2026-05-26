import time
import logging
import os
import json
import subprocess
import state
import tmux_util

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 5))
HEARTBEAT_STALE_SECONDS = int(os.environ.get("HEARTBEAT_STALE_SECONDS", 20))
HEARTBEAT_GRACE_SECONDS = int(os.environ.get("HEARTBEAT_GRACE_SECONDS", 30))

def is_process_alive(pid):
    """Checks if a process is alive. Note: This is Linux-specific due to /proc usage."""
    try:
        state_char = None
        ppid = None
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("State:"):
                    state_char = line.split()[1]
                elif line.startswith("PPid:"):
                    ppid = int(line.split()[1])
        
        if state_char is None or ppid is None:
            return False
            
        # Consider dead only if it's a zombie. 
        # We don't care about PPID=1 (orphans) because agents might persist 
        # even if their wrapper dies, and we want to keep tracking them.
        if state_char == "Z":
            return False
        return True
    except FileNotFoundError:
        return False
    except (IOError, ValueError) as e:
        logging.debug(f"Error reading process status for PID {pid}: {e}")
        return False
    except Exception as e:
        logging.debug(f"Unexpected error in is_process_alive for PID {pid}: {e}")
        return False

def get_liveness_phase(info: dict, now: float | None = None) -> str:
    """Classifies heartbeat/recovery liveness as fresh, stale, expired, or none."""
    now = now if now is not None else time.time()
    reference = info.get("last_heartbeat") or info.get("recovered_at")
    if reference is None:
        return "none"
    age = now - reference
    if age <= HEARTBEAT_STALE_SECONDS:
        return "fresh"
    if age <= HEARTBEAT_GRACE_SECONDS:
        return "stale"
    return "expired"


def monitor_once(now: float | None = None):
    """Runs a single monitor pass."""
    now = now if now is not None else time.time()
    to_remove = []

    agents_snapshot = state.get_all_agents()
    active_panes = tmux_util.list_panes()
    if active_panes is None:
        logging.warning("Skipping monitor pass because tmux panes could not be listed.")
        return

    active_pane_ids = {pane["pane_id"] for pane in active_panes}
    pane_info_by_id = {pane["pane_id"]: pane for pane in active_panes}
    alive_cache = {}
    discovered_proc_cache = {}

    def cached_is_process_alive(pid):
        if not pid:
            return False
        if pid not in alive_cache:
            alive_cache[pid] = is_process_alive(pid)
        return alive_cache[pid]

    def cached_discover_agent_process(pane_id, agent_cmd):
        cache_key = (pane_id, agent_cmd)
        if cache_key not in discovered_proc_cache:
            discovered_proc_cache[cache_key] = state.discover_agent_process(pane_id, agent_cmd)
        return discovered_proc_cache[cache_key]

    for name, info in agents_snapshot.items():
        pane_id = info.get("tmux_pane")
        pane_info = pane_info_by_id.get(pane_id) if pane_id else None

        # Acknowledgment logic
        if info.get("status") == "waiting" and pane_info and pane_info.get("pane_active"):
            logging.info(f"Agent {name} acknowledged by user (pane active). Transitioning to idle.")
            state.update_agent(name, status="idle")
            info["status"] = "idle"

        if pane_id and pane_id not in active_pane_ids:
            logging.info(f"Pane {pane_id} for agent {name} no longer exists.")
            to_remove.append(name)
            continue

        liveness_phase = get_liveness_phase(info, now)
        if pane_id and liveness_phase == "expired":
            proc = cached_discover_agent_process(pane_id, info.get("agent_cmd"))
            if proc:
                logging.info(f"Keeping stale agent {name}; found live pane process PID {proc['pid']} ({proc['comm']})")
                state.update_agent(name, pid=proc["pid"], wrapper_pid=None)
            else:
                logging.info(f"Removing stale agent {name}; no live pane process found after heartbeat grace period.")
                to_remove.append(name)
                continue

        wrapper_pid = info.get("wrapper_pid")
        pid = info.get("pid")
        use_procfs_fallback = (liveness_phase == "none")

        wrapper_alive = cached_is_process_alive(wrapper_pid) if use_procfs_fallback else False
        child_alive = cached_is_process_alive(pid) if use_procfs_fallback else False

        # Update child PID if not already known, or recover if the tracked child died.
        if use_procfs_fallback and wrapper_pid and (not info.get("pid") or (pid and not child_alive)):
            try:
                out = subprocess.check_output(["pgrep", "-P", str(wrapper_pid)], timeout=1).decode("utf-8").strip()
                if out:
                    actual_pid = int(out.split()[0])
                    state.update_agent(name, pid=actual_pid)
                    pid = actual_pid
                    child_alive = cached_is_process_alive(actual_pid)
            except Exception as e:
                logging.debug(f"Failed to pgrep child PID for {name}: {e}")

        # If wrapper/child tracking is stale, fall back to inspecting the pane's tty.
        if use_procfs_fallback and pane_id and ((wrapper_pid and not wrapper_alive and not child_alive) or (pid and not child_alive)):
            proc = cached_discover_agent_process(pane_id, info.get("agent_cmd"))
            if proc:
                logging.info(f"Recovered live pane process for {name}: PID {proc['pid']} ({proc['comm']})")
                state.update_agent(name, pid=proc["pid"], wrapper_pid=None)
                pid = proc["pid"]
                child_alive = True
                wrapper_pid = None

        if use_procfs_fallback and wrapper_pid:
            if not wrapper_alive and not child_alive:
                to_remove.append(name)
                continue
        elif use_procfs_fallback:
            # Spawning agent timeout check
            if info.get("status") == "spawning":
                spawn_time = info.get("timestamp", 0)
                if now - spawn_time > 60:
                    to_remove.append(name)
                    continue
            # Recovered agent fallback
            elif pid and not child_alive:
                to_remove.append(name)
                continue

        # Flush inbox to file
        inbox = info.get("inbox", [])
        if inbox:
            uuid_str = info.get("uuid")
            if not uuid_str:
                uuid_str = name
            inbox_file = os.path.join(state.INBOX_DIR, f"{uuid_str}.inbox")
            try:
                os.makedirs(os.path.dirname(inbox_file), exist_ok=True)
                with open(inbox_file, "a") as f:
                    for msg_obj in inbox:
                        f.write(json.dumps(msg_obj) + "\n")
                state.clear_inbox(name)
            except IOError as e:
                logging.error(f"Failed to flush inbox for {name}: {e}")

    if to_remove:
        for name in to_remove:
            logging.info(f"Removing dead agent: {name}")
            state.delete_agent(name)

    # Sweep expired client event watchlists
    state.sweep_expired_watchlists()


def background_monitor():
    """Periodically checks process health and scrapes panes for status."""
    logging.info("Starting background monitor...")
    while True:
        time.sleep(POLL_INTERVAL)
        monitor_once()


def check_unread_messages_and_remind():
    """Checks all inboxes for unread messages, sends reminders to live agents, and resolves gone ones."""
    import glob
    import rpc_handler

    inbox_pattern = os.path.join(state.INBOX_DIR, "*.inbox")
    inbox_files = glob.glob(inbox_pattern)
    if not inbox_files:
        return

    logging.debug(f"Checking {len(inbox_files)} inbox files for unread messages...")

    active_panes = tmux_util.list_panes()
    active_pane_ids = {pane["pane_id"] for pane in active_panes} if active_panes is not None else set()

    for inbox_file in inbox_files:
        basename = os.path.basename(inbox_file)
        target_id_or_name = basename[:-6] # remove ".inbox"

        try:
            with rpc_handler._locked_inbox(inbox_file):
                messages = []
                if os.path.exists(inbox_file):
                    with open(inbox_file, "r") as f:
                        for line in f:
                            if line.strip():
                                try:
                                    messages.append(json.loads(line))
                                except json.JSONDecodeError:
                                    pass

                unread_msgs = [m for m in messages if not m.get("read", False)]
                if not unread_msgs:
                    continue

                info = state.get_agent(target_id_or_name)
                pane_id = info.get("tmux_pane") if info else None
                pane_exists = (pane_id in active_pane_ids) if pane_id else False

                agent_is_alive = (info is not None) and pane_exists

                if agent_is_alive:
                    if info.get("no_notify_with_send_keys", False):
                        logging.info(f"Skipping periodic reminder send-keys for agent {target_id_or_name} (no_notify_with_send_keys is enabled)")
                        continue

                    senders = {m.get("sender", "unknown") for m in unread_msgs}
                    logging.info(f"Agent {target_id_or_name} is alive in pane {pane_id}. Sending inbox reminders from: {senders}")
                    for sender in senders:
                        notify_msg = f"New message in inbox from {sender}"
                        tmux_util.send_keys(pane_id, notify_msg, info.get("tmux_socket"))
                else:
                    logging.info(f"Agent {target_id_or_name} is gone. Marking {len(unread_msgs)} unread messages as no-receiver.")
                    for msg in unread_msgs:
                        msg["read"] = True
                        msg["status"] = "no-receiver"

                    rpc_handler._atomic_write_inbox(inbox_file, messages)
        except Exception as e:
            logging.error(f"Failed to process inbox {inbox_file} for reminder/cleanup: {e}")


def background_inbox_reminder():
    """Periodically checks for unread inbox messages to remind active agents or resolve gone ones."""
    logging.info("Starting background inbox reminder...")
    interval = int(os.environ.get("REMINDER_INTERVAL_SECONDS", 900))
    while True:
        time.sleep(interval)
        try:
            check_unread_messages_and_remind()
        except Exception as e:
            logging.error(f"Error in background inbox reminder pass: {e}")

