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
            subprocess.run(cmd, check=True, capture_output=True, timeout=5, env=tmux_env(strip_inherited=(cmd[0] == "tmux" and ("-S" in cmd or bool(default_tmux_socket())))))
        except Exception as e:
            logging.error(f"Tmux worker error: {e}")
        finally:
            task_queue.task_done()

# Start tmux worker
threading.Thread(target=tmux_worker, daemon=True).start()

def enqueue_tmux_cmd(cmd):
    """Enqueues a tmux command for background execution."""
    task_queue.put({'cmd': cmd})


def default_tmux_socket():
    """Returns the app-private tmux socket configured for this tracker, if any."""
    return os.environ.get("AGENT_TRACKER_TMUX_SOCKET") or os.environ.get("BROCCOLI_COMMS_TMUX_SOCKET") or None


def tmux_base(socket_path=None):
    """Builds a tmux command prefix, defaulting to the configured private socket."""
    socket_path = socket_path if socket_path is not None else default_tmux_socket()
    cmd = ["tmux"]
    if socket_path:
        cmd.extend(["-S", socket_path])
    return cmd


def tmux_env(strip_inherited: bool | None = None) -> dict[str, str]:
    """Returns an environment that cannot leak inherited tmux context in app mode."""
    if strip_inherited is None:
        strip_inherited = bool(default_tmux_socket())
    env = os.environ.copy()
    if strip_inherited:
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
    return env


def tmux_command(args=None, socket_path=None):
    """Builds a full tmux command without double-prefixing explicit tmux options."""
    args = list(args or [])
    if args and args[0] in ("-S", "-L"):
        return ["tmux"] + args
    return tmux_base(socket_path) + args


def run_tmux_cmd(cmd, timeout=5):
    """Helper to run tmux commands synchronously."""
    try:
        args = list(cmd or [])
        result = subprocess.run(
            tmux_command(args),
            check=True,
            capture_output=True,
            timeout=timeout,
            env=tmux_env(strip_inherited=bool(default_tmux_socket()) or (bool(args) and args[0] in ("-S", "-L"))),
        )
        return result.stdout.decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Tmux command failed: {e} - {e.stderr.decode('utf-8')}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error running tmux command: {e}")
        raise

def set_agent_id(pane_id, agent_id, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-t", pane_id, "@agent_id", agent_id], socket_path)
    enqueue_tmux_cmd(cmd)


def set_agent_uuid(pane_id, uuid, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-t", pane_id, "@agent_uuid", uuid], socket_path)
    enqueue_tmux_cmd(cmd)


def set_agent_type(pane_id, agent_type, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-t", pane_id, "@agent_type", agent_type], socket_path)
    enqueue_tmux_cmd(cmd)


def set_agent_cmd(pane_id, agent_cmd, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-t", pane_id, "@agent_cmd", agent_cmd], socket_path)
    enqueue_tmux_cmd(cmd)


def set_agent_no_notify_with_send_keys(pane_id, value, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-t", pane_id, "@agent_no_notify_with_send_keys", "on" if value else "off"], socket_path)
    enqueue_tmux_cmd(cmd)


def set_agent_no_registry(pane_id, value, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-t", pane_id, "@agent_no_registry", "on" if value else "off"], socket_path)
    enqueue_tmux_cmd(cmd)


def list_panes():
    """Lists panes with ID, agent identity, type, cmd, and active state.

    Returns None when tmux itself cannot be queried. This lets the monitor
    distinguish "no panes" from "tmux unavailable" and avoid deleting every
    tracked agent during transient PATH/launchd issues on macOS.
    """
    try:
        out = run_tmux_cmd(["list-panes", "-a", "-F", "#{pane_id}|#{@agent_name}|#{@agent_id}|#{@agent_uuid}|#{@agent_type}|#{@agent_cmd}|#{@agent_no_notify_with_send_keys}|#{@agent_no_registry}|#{pane_active}|#{pane_current_path}|#{socket_path}"])
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
                    "cwd": parts[9] if len(parts) > 9 and parts[9] else None,
                    "tmux_socket": parts[10] if len(parts) > 10 and parts[10] else None
                }
                panes.append(pane_info)
        return panes
    except Exception as e:
        logging.error(f"Failed to list panes: {e}")
        return None

def get_pane_info(pane_id, socket_path=None):
    """Gets tty, session, and shell pid for a pane."""
    try:
        out = run_tmux_cmd(tmux_command(["display-message", "-p", "-t", pane_id, "#{pane_tty} #S #{pane_pid}"], socket_path)[1:])
        parts = out.split()
        if len(parts) >= 3:
            return {"tty": parts[0], "session": parts[1], "pid": int(parts[2])}
    except Exception as e:
        logging.error(f"Failed to get pane info for {pane_id}: {e}")
    return None

def set_agent_name(pane_id, name, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-t", pane_id, "@agent_name", name], socket_path)
    enqueue_tmux_cmd(cmd)

def set_agent_name_sync(pane_id, name, socket_path=None):
    run_tmux_cmd(tmux_command(["set-option", "-p", "-t", pane_id, "@agent_name", name], socket_path)[1:])

def unset_agent_name(pane_id, socket_path=None):
    cmd = tmux_command(["set-option", "-p", "-u", "-t", pane_id, "@agent_name"], socket_path)
    enqueue_tmux_cmd(cmd)

def set_pane_title(pane_id, title, socket_path=None):
    cmd = tmux_command(["select-pane", "-t", pane_id, "-T", title], socket_path)
    enqueue_tmux_cmd(cmd)

def set_pane_title_sync(pane_id, title, socket_path=None):
    run_tmux_cmd(tmux_command(["select-pane", "-t", pane_id, "-T", title], socket_path)[1:])


def get_pane_title(pane_id, socket_path=None):
    """Returns the current tmux pane title, including title updates set by terminal apps."""
    cmd = []
    if socket_path:
        cmd.extend(["-S", socket_path])
    cmd.extend(["display-message", "-p", "-t", pane_id, "#{pane_title}"])
    return run_tmux_cmd(cmd)


def unset_pane_title(pane_id, socket_path=None):
    cmd = tmux_command(["select-pane", "-t", pane_id, "-T", ""], socket_path)
    enqueue_tmux_cmd(cmd)

def send_keys(pane_id, keys, socket_path=None):
    """Sends keys followed by a short delay and Enter to ensure submission."""
    global last_send_keys_time
    cmd_base = tmux_base(socket_path)
    
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


_SIMPLE_KEY_ALIASES = {
    "esc": "Escape",
    "escape": "Escape",
    "enter": "Enter",
    "return": "Enter",
    "ret": "Enter",
    "space": "Space",
    "spc": "Space",
    "tab": "Tab",
    "btab": "BTab",
    "backtab": "BTab",
    "bs": "Backspace",
    "backspace": "Backspace",
    "del": "Delete",
    "delete": "Delete",
    "ins": "Insert",
    "insert": "Insert",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pgup": "PageUp",
    "pageup": "PageUp",
    "ppage": "PageUp",
    "pgdn": "PageDown",
    "pagedown": "PageDown",
    "npage": "PageDown",
}

_SIMPLE_KEYS = set(_SIMPLE_KEY_ALIASES.values()) | {f"F{i}" for i in range(1, 25)}
_MODIFIER_ALIASES = {
    "c": "C",
    "ctrl": "C",
    "control": "C",
    "m": "M",
    "meta": "M",
    "alt": "M",
    "s": "S",
    "shift": "S",
}
_SHELL_LIKE_KEY_CHARS = set("|&;<>$`(){}[]*?~!#\"'\\\n\r")


def _run_tmux_input(cmd, socket_path=None):
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        timeout=5,
        env=tmux_env(strip_inherited=bool(socket_path) or bool(default_tmux_socket())),
    )


def send_literal_text(pane_id, text, submit=True, socket_path=None):
    """Type literal text into a pane, optionally pressing Enter afterwards."""
    if not pane_id:
        raise ValueError("pane_id is required")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if text == "":
        raise ValueError("text must not be empty")
    _run_tmux_input(tmux_base(socket_path) + ["send-keys", "-t", pane_id, "-l", "--", text], socket_path)
    if submit:
        _run_tmux_input(tmux_base(socket_path) + ["send-keys", "-t", pane_id, "Enter"], socket_path)
    return True


def normalize_key_token(key):
    """Normalize a whitelisted symbolic tmux key token."""
    if not isinstance(key, str):
        raise ValueError("key must be a string")
    token = key.strip()
    if not token:
        raise ValueError("key must not be empty")
    if token != key or any(ch.isspace() for ch in token):
        raise ValueError("key must not contain whitespace")
    if any(ch in _SHELL_LIKE_KEY_CHARS for ch in token):
        raise ValueError("key contains unsupported characters")
    if token.endswith("-"):
        raise ValueError("key has trailing modifier")

    lower = token.lower()
    if lower in _SIMPLE_KEY_ALIASES:
        return _SIMPLE_KEY_ALIASES[lower]
    if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", lower):
        return "F" + lower[1:]

    parts = token.split("-")
    if len(parts) == 1:
        if token in _SIMPLE_KEYS:
            return token
        raise ValueError(f"unknown key: {key}")
    if len(parts) > 3:
        raise ValueError("too many key modifiers")

    modifiers = []
    for raw_modifier in parts[:-1]:
        modifier = _MODIFIER_ALIASES.get(raw_modifier.lower())
        if not modifier:
            raise ValueError(f"unknown key modifier: {raw_modifier}")
        if modifier in modifiers:
            raise ValueError(f"duplicate key modifier: {raw_modifier}")
        modifiers.append(modifier)

    base_raw = parts[-1]
    if not base_raw:
        raise ValueError("key has empty base")
    base_lower = base_raw.lower()
    if base_lower in _SIMPLE_KEY_ALIASES:
        base = _SIMPLE_KEY_ALIASES[base_lower]
    elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", base_lower):
        base = "F" + base_lower[1:]
    elif len(base_raw) == 1 and base_raw.isalnum():
        base = base_raw.lower() if "C" in modifiers else base_raw
    else:
        raise ValueError(f"unknown key: {key}")
    return "-".join(modifiers + [base])


def normalize_key_tokens(keys):
    if isinstance(keys, str):
        keys = [keys]
    if not isinstance(keys, (list, tuple)) or not keys:
        raise ValueError("keys must be a non-empty list")
    return [normalize_key_token(key) for key in keys]


def send_symbolic_keys(pane_id, keys, socket_path=None):
    """Send whitelisted symbolic tmux key tokens to a pane."""
    if not pane_id:
        raise ValueError("pane_id is required")
    normalized = normalize_key_tokens(keys)
    _run_tmux_input(tmux_base(socket_path) + ["send-keys", "-t", pane_id, *normalized], socket_path)
    return True


def focus_pane(pane_id, session=None, socket_path=None):
    """Best-effort focus of a pane using only an explicit/private tmux socket.

    Returns False instead of falling back to the user's default tmux server when
    no registered/private socket is available.
    """
    if not pane_id:
        raise ValueError("pane_id is required")
    socket_path = socket_path or default_tmux_socket()
    if not socket_path:
        logging.warning("Refusing to focus pane %s without an explicit/private tmux socket", pane_id)
        return False

    env = tmux_env(strip_inherited=True)
    base = tmux_base(socket_path)
    focused = False
    if session:
        try:
            subprocess.run(base + ["switch-client", "-t", session], check=True, capture_output=True, timeout=5, env=env)
            focused = True
        except Exception as e:
            logging.warning("Failed to switch tmux client to session %s for pane %s: %s", session, pane_id, e)
    try:
        subprocess.run(base + ["select-window", "-t", pane_id], check=True, capture_output=True, timeout=5, env=env)
        focused = True
    except Exception as e:
        logging.warning("Failed to select tmux window for pane %s: %s", pane_id, e)
    try:
        subprocess.run(base + ["select-pane", "-t", pane_id], check=True, capture_output=True, timeout=5, env=env)
        focused = True
    except Exception as e:
        logging.warning("Failed to select tmux pane %s: %s", pane_id, e)
    return focused


def spin_agent(agent_name, command, target_pane=None, session=None, directory=None, env=None, tmux_socket=None):
    import os
    import shlex

    identity_keys = ("AGENT_ID", "AGENT_NAME", "AGENT_UUID")
    tmux_cmd_prefix = tmux_base(tmux_socket)

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
    run_env.pop("TMUX", None)
    run_env.pop("TMUX_PANE", None)
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
            has_session = subprocess.run(tmux_cmd_prefix + ["has-session", "-t", session], capture_output=True, env=run_env).returncode == 0
            if has_session:
                cmd = tmux_cmd_prefix + ["new-window", "-P", "-F", "#{pane_id}", "-t", session, "-c", directory] + env_args + [wrapped_command]
            else:
                cmd = tmux_cmd_prefix + ["new-session", "-d", "-P", "-F", "#{pane_id}", "-s", session, "-c", directory] + env_args + [wrapped_command]
            logging.info("spin_agent tmux_cmd=%s", cmd)
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=run_env)
            pane_id = result.stdout.strip() or None
            logging.info("spin_agent tmux_result pane_id=%s has_session=%s", pane_id, has_session)
            subprocess.run(tmux_cmd_prefix + ["switch-client", "-t", session], check=False, capture_output=True, env=run_env)
            return pane_id

        tmux_cmd = tmux_cmd_prefix[:]
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
    return tmux_reliability.send_keys_reliable(pane_id, keys, socket_path if socket_path is not None else default_tmux_socket(), timeout)

def execute_command_reliable(pane_id, command, socket_path=None, timeout=30):
    """Executes a command in a pane reliably, waiting for execution and returning the exit code."""
    return tmux_reliability.execute_command_reliable(pane_id, command, socket_path if socket_path is not None else default_tmux_socket(), timeout)

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
