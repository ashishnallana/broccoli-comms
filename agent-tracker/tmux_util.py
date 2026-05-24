import subprocess
import logging
import threading
import queue
import sys
import os
import re
import tmux_reliability

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', stream=sys.stderr)

task_queue = queue.Queue()
last_send_keys_time = 0.0
send_keys_lock = threading.Lock()

def tmux_worker():
    """Worker thread for executing tmux commands sequentially."""
    while True:
        task = task_queue.get()
        if task is None: break
        try:
            cmd = task['cmd']
            # Use a reasonable timeout for tmux commands
            subprocess.run(cmd, check=True, capture_output=True, timeout=5)
        except Exception as e:
            logging.error(f"Tmux worker error: {e}")
        finally:
            task_queue.task_done()

# Start tmux worker
threading.Thread(target=tmux_worker, daemon=True).start()

def enqueue_tmux_cmd(cmd):
    """Enqueues a tmux command for background execution."""
    task_queue.put({'cmd': cmd})

def run_tmux_cmd(cmd, timeout=5):
    """Helper to run tmux commands synchronously."""
    try:
        result = subprocess.run(["tmux"] + cmd, check=True, capture_output=True, timeout=timeout)
        return result.stdout.decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Tmux command failed: {e} - {e.stderr.decode('utf-8')}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error running tmux command: {e}")
        raise

def set_agent_id(pane_id, agent_id, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-t", pane_id, "@agent_id", agent_id])
    enqueue_tmux_cmd(cmd)


def set_agent_uuid(pane_id, uuid, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-t", pane_id, "@agent_uuid", uuid])
    enqueue_tmux_cmd(cmd)


def set_agent_type(pane_id, agent_type, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-t", pane_id, "@agent_type", agent_type])
    enqueue_tmux_cmd(cmd)


def set_agent_cmd(pane_id, agent_cmd, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-t", pane_id, "@agent_cmd", agent_cmd])
    enqueue_tmux_cmd(cmd)


def set_agent_no_notify_with_send_keys(pane_id, value, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-t", pane_id, "@agent_no_notify_with_send_keys", "on" if value else "off"])
    enqueue_tmux_cmd(cmd)


def set_agent_no_registry(pane_id, value, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-t", pane_id, "@agent_no_registry", "on" if value else "off"])
    enqueue_tmux_cmd(cmd)


def list_panes():
    """Lists panes with ID, agent identity, type, cmd, and active state.

    Returns None when tmux itself cannot be queried. This lets the monitor
    distinguish "no panes" from "tmux unavailable" and avoid deleting every
    tracked agent during transient PATH/launchd issues on macOS.
    """
    try:
        out = run_tmux_cmd(["list-panes", "-a", "-F", "#{pane_id}|#{@agent_name}|#{@agent_id}|#{@agent_uuid}|#{@agent_type}|#{@agent_cmd}|#{@agent_no_notify_with_send_keys}|#{@agent_no_registry}|#{pane_active}|#{pane_current_path}"])
        panes = []
        if out:
            for line in out.split("\n"):
                parts = line.split('|')
                if len(parts) < 9:
                    continue
                pane_info = {
                    "pane_id": parts[0],
                    "agent_name": parts[1] if parts[1] else None,
                    "agent_id": parts[2] if parts[2] else (parts[3] if parts[3] else None),
                    "agent_uuid": parts[3] if parts[3] else None,
                    "agent_type": parts[4] if parts[4] else "unknown",
                    "agent_cmd": parts[5] if parts[5] else None,
                    "no_notify_with_send_keys": (parts[6] == "on"),
                    "no_registry": (parts[7] == "on"),
                    "pane_active": (parts[8] == "1"),
                    "cwd": parts[9] if len(parts) > 9 and parts[9] else None
                }
                panes.append(pane_info)
        return panes
    except Exception as e:
        logging.error(f"Failed to list panes: {e}")
        return None

def get_pane_info(pane_id):
    """Gets tty, session, and shell pid for a pane."""
    try:
        out = run_tmux_cmd(["display-message", "-p", "-t", pane_id, "#{pane_tty} #S #{pane_pid}"])
        parts = out.split()
        if len(parts) >= 3:
            return {"tty": parts[0], "session": parts[1], "pid": int(parts[2])}
    except Exception as e:
        logging.error(f"Failed to get pane info for {pane_id}: {e}")
    return None

def set_agent_name(pane_id, name, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-t", pane_id, "@agent_name", name])
    enqueue_tmux_cmd(cmd)

def set_agent_name_sync(pane_id, name, socket_path=None):
    cmd = ["set-option", "-p", "-t", pane_id, "@agent_name", name]
    if socket_path:
        run_tmux_cmd(["-S", socket_path] + cmd)
    else:
        run_tmux_cmd(cmd)

def unset_agent_name(pane_id, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["set-option", "-p", "-u", "-t", pane_id, "@agent_name"])
    enqueue_tmux_cmd(cmd)

def set_pane_title(pane_id, title, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["select-pane", "-t", pane_id, "-T", title])
    enqueue_tmux_cmd(cmd)

def set_pane_title_sync(pane_id, title, socket_path=None):
    cmd = ["select-pane", "-t", pane_id, "-T", title]
    if socket_path:
        run_tmux_cmd(["-S", socket_path] + cmd)
    else:
        run_tmux_cmd(cmd)

def unset_pane_title(pane_id, socket_path=None):
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["select-pane", "-t", pane_id, "-T", ""])
    enqueue_tmux_cmd(cmd)

def send_keys(pane_id, keys, socket_path=None):
    """Sends keys followed by a short delay and Enter to ensure submission."""
    global last_send_keys_time
    cmd_base = ["tmux"]
    if socket_path:
        cmd_base.extend(["-S", socket_path])
    
    import time
    with send_keys_lock:
        now = time.time()
        delay = 3.0 - (now - last_send_keys_time)
        if delay > 0:
            enqueue_tmux_cmd(["sleep", f"{delay:.2f}"])
            last_send_keys_time = now + delay
        else:
            last_send_keys_time = now

        # 1. Send the actual message keys
        enqueue_tmux_cmd(cmd_base + ["send-keys", "-t", pane_id, keys])
        
        # 2. Enqueue a short sleep to allow the terminal/app to process the input buffer
        enqueue_tmux_cmd(["sleep", "0.5"])
        last_send_keys_time += 0.5
        
        # 3. Send the Enter key to submit
        enqueue_tmux_cmd(cmd_base + ["send-keys", "-t", pane_id, "Enter"])

def spin_agent(agent_name, command, target_pane=None, session=None, directory=None, env=None, tmux_socket=None):
    import os
    import shlex

    identity_keys = ("AGENT_ID", "AGENT_NAME", "AGENT_UUID")
    tmux_base = ["tmux"]
    if tmux_socket:
        tmux_base.extend(["-S", tmux_socket])

    command_parts = shlex.split(command)
    spawn_env = dict(env or {})
    for key in identity_keys:
        if spawn_env.get(key) == "":
            spawn_env.pop(key, None)
    spawn_env["SUGGESTED_AGENT_NAME"] = agent_name

    env_args = []
    for k, v in spawn_env.items():
        env_args.extend(["-e", f"{k}={v}"])

    should_unset_identity = not any(key in spawn_env for key in identity_keys)
    command_prefix = []
    if should_unset_identity:
        command_prefix.append("unset AGENT_ID AGENT_NAME AGENT_UUID")
    command_prefix.append(f"export SUGGESTED_AGENT_NAME={shlex.quote(agent_name)}")
    wrapped_command = "; ".join(command_prefix) + f"; exec {command}"

    run_env = os.environ.copy()
    for key in identity_keys:
        run_env.pop(key, None)
    run_env["SUGGESTED_AGENT_NAME"] = agent_name

    try:
        logging.info(
            "spin_agent request agent_name=%s session=%s directory=%s target_pane=%s command=%s parsed_command=%s env=%s",
            agent_name,
            session,
            directory,
            target_pane,
            command,
            command_parts,
            list(spawn_env.keys()) if spawn_env else None,
        )
        if session and directory:
            has_session = subprocess.run(tmux_base + ["has-session", "-t", session], capture_output=True, env=run_env).returncode == 0
            if has_session:
                cmd = tmux_base + ["new-window", "-P", "-F", "#{pane_id}", "-t", session, "-c", directory] + env_args + [wrapped_command]
            else:
                cmd = tmux_base + ["new-session", "-d", "-P", "-F", "#{pane_id}", "-s", session, "-c", directory] + env_args + [wrapped_command]
            logging.info("spin_agent tmux_cmd=%s", cmd)
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=run_env)
            pane_id = result.stdout.strip() or None
            logging.info("spin_agent tmux_result pane_id=%s has_session=%s", pane_id, has_session)
            subprocess.run(tmux_base + ["switch-client", "-t", session], check=False, capture_output=True, env=run_env)
            return pane_id

        tmux_cmd = tmux_base[:]
        if target_pane:
            tmux_cmd.extend(["split-window", "-P", "-F", "#{pane_id}", "-t", target_pane])
        else:
            tmux_cmd.extend(["split-window", "-P", "-F", "#{pane_id}"])
        tmux_cmd.extend(env_args)
        tmux_cmd.append(wrapped_command)
        logging.info("spin_agent tmux_cmd=%s", tmux_cmd)
        result = subprocess.run(tmux_cmd, check=True, capture_output=True, text=True, env=run_env)
        pane_id = result.stdout.strip() or None
        logging.info("spin_agent tmux_result pane_id=%s", pane_id)
        return pane_id
    except subprocess.CalledProcessError as e:
        logging.error("Tmux spin failed cmd=%s stderr=%s", cmd if 'cmd' in locals() else tmux_cmd, e.stderr.decode())
        raise

def send_keys_reliable(pane_id, keys, socket_path=None, timeout=10):
    """Sends keys to a pane reliably, verifying they appeared on screen."""
    return tmux_reliability.send_keys_reliable(pane_id, keys, socket_path, timeout)

def execute_command_reliable(pane_id, command, socket_path=None, timeout=30):
    """Executes a command in a pane reliably, waiting for execution and returning the exit code."""
    return tmux_reliability.execute_command_reliable(pane_id, command, socket_path, timeout)

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def capture_pane_visible_text(pane_id, last_lines=200, socket_path=None, include_ansi=False) -> str:
    """Captures the visible text of a pane and its scrollback history.
    
    Args:
        pane_id: The tmux pane ID (e.g., %0).
        last_lines: The number of scrollback/history lines to retrieve.
        socket_path: Optional path to tmux socket.
        include_ansi: If False, strips ANSI color and formatting escape sequences.
    """
    cmd = []
    if socket_path:
        cmd.extend(["-S", socket_path])
    
    cmd.extend(["capture-pane", "-p", "-J", "-t", pane_id])
    if last_lines is not None and last_lines > 0:
        cmd.extend(["-S", f"-{last_lines}"])
    
    try:
        out = run_tmux_cmd(cmd)
        if not include_ansi:
            out = ANSI_ESCAPE.sub('', out)
        return out
    except Exception as e:
        logging.error(f"Failed to capture visible text for pane {pane_id}: {e}")
        raise

def is_pane_in_copy_mode(pane_id, socket_path=None) -> bool:
    """Queries tmux to see if the pane is currently in copy-mode."""
    cmd = []
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["display-message", "-p", "-t", pane_id, "#{pane_in_mode}"])
    try:
        out = run_tmux_cmd(cmd)
        return out.strip() == "1"
    except Exception as e:
        logging.error(f"Failed to check copy mode for {pane_id}: {e}")
        return False
