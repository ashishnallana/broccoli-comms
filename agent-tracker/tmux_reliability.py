"""tmux_reliability.py: Reusable library for safe, verified tmux input delivery."""

import logging
import os
import random
import string
import subprocess
import time

logger = logging.getLogger(__name__)

def default_tmux_socket() -> str | None:
    """Returns the app-private tmux socket configured for this tracker, if any."""
    return os.environ.get("AGENT_TRACKER_TMUX_SOCKET") or os.environ.get("BROCCOLI_COMMS_TMUX_SOCKET") or None


def tmux_command(args: list[str], socket_path: str = None) -> list[str]:
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
    """Returns an environment that cannot accidentally use inherited tmux context."""
    if strip_inherited is None:
        strip_inherited = bool(default_tmux_socket())
    env = os.environ.copy()
    if strip_inherited:
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
    return env


def run_tmux(args: list[str], socket_path: str = None, timeout: float = 5.0) -> str | None:
    """Executes a tmux command and returns stdout string. Returns None on failure."""
    cmd = tmux_command(args, socket_path)
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
            env=tmux_env(strip_inherited=bool(socket_path or default_tmux_socket())),
        )
        return res.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.debug("Tmux command failed: %s. Error: %s", cmd, e)
        return None

def get_pane_format(pane_id: str, fmt: str, socket_path: str = None) -> str | None:
    """Retrieves a tmux formatting variable from the target pane."""
    return run_tmux(["display-message", "-p", "-t", pane_id, fmt], socket_path)

def is_pane_alive(pane_id: str, socket_path: str = None) -> bool:
    """Verifies if the target pane exists and is not dead."""
    pane_dead = get_pane_format(pane_id, "#{pane_dead}", socket_path)
    if pane_dead is None:
        return False
    return pane_dead == "0"

def exit_copy_mode_if_needed(pane_id: str, socket_path: str = None) -> bool:
    """Checks pane_in_mode and sends 'cancel' to exit tmux copy mode if active."""
    in_mode = get_pane_format(pane_id, "#{pane_in_mode}", socket_path)
    if in_mode == "1":
        logger.info("Pane %s is in copy mode. Exiting copy mode.", pane_id)
        run_tmux(["send-keys", "-t", pane_id, "q"], socket_path)
        time.sleep(0.1)
        return True
    return False

def send_keys_reliable(
    pane_id: str,
    text: str,
    socket_path: str = None,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
    submit_key: str = "Enter",
) -> bool:
    """Sends a string of keys (e.g., a text notification) to a pane and verifies it appeared on screen.
    
    Uses copy-mode checks and screen capture comparisons to verify delivery.
    """
    if not is_pane_alive(pane_id, socket_path):
        logger.warning("Cannot send keys to pane %s: pane is dead or invalid.", pane_id)
        return False

    exit_copy_mode_if_needed(pane_id, socket_path)

    # Send the keys followed by provider submit key (tmux literal key name)
    run_tmux(["send-keys", "-t", pane_id, text, submit_key or "Enter"], socket_path)

    start_time = time.time()
    while time.time() - start_time < timeout:
        pane_text = run_tmux(["capture-pane", "-p", "-t", pane_id], socket_path)
        if pane_text and text in pane_text:
            return True
        time.sleep(poll_interval)

    logger.warning("Timeout waiting for keys to appear in pane %s", pane_id)
    return False

def execute_command_reliable(
    pane_id: str,
    command: str,
    socket_path: str = None,
    timeout: float = 30.0,
    poll_interval: float = 0.5
) -> int | None:
    """Executes a shell command, verifies execution completion, and returns its exit status code.
    
    Wraps the command in a concatenated sentinel string to prevent command input matching race conditions.
    """
    if not is_pane_alive(pane_id, socket_path):
        logger.warning("Cannot execute command in pane %s: pane is dead or invalid.", pane_id)
        return None

    exit_copy_mode_if_needed(pane_id, socket_path)

    # Generate unique sentinel string
    sentinel_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    sentinel_marker = f"__SAFE_SEND_SENTINEL_{sentinel_id}__"
    
    # Use string concatenation in shell (RESULT_""SENTINEL""_EXIT) to prevent input matching
    wrapped_command = f"{command}; echo RESULT_\"\"{sentinel_marker}\"\"_EXIT=$?"

    run_tmux(["send-keys", "-t", pane_id, wrapped_command, "Enter"], socket_path)

    expected_output_prefix = f"RESULT_{sentinel_marker}_EXIT="
    start_time = time.time()
    while time.time() - start_time < timeout:
        pane_text = run_tmux(["capture-pane", "-p", "-t", pane_id], socket_path)
        if pane_text:
            for line in pane_text.splitlines():
                if expected_output_prefix in line:
                    parts = line.split(expected_output_prefix)
                    if len(parts) == 2:
                        try:
                            return int(parts[1].strip())
                        except ValueError:
                            pass
                    return 0
        time.sleep(poll_interval)

    logger.warning("Timeout waiting for command completion in pane %s (sentinel %s)", pane_id, sentinel_marker)
    return None
