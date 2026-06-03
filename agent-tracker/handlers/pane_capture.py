import os
import logging
import state
import tmux_util
import config

DEFAULT_CAPTURE_PANE_LINES = 20

def _default_capture_pane_lines() -> int:
    raw = os.environ.get("AGENT_TRACKER_CAPTURE_PANE_DEFAULT_LINES") or config.get("ui", "capture_pane_default_lines", str(DEFAULT_CAPTURE_PANE_LINES))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CAPTURE_PANE_LINES
    return value if value > 0 else DEFAULT_CAPTURE_PANE_LINES

def handle_capture_pane(
    params: dict,
    caller_pid: int = None,
    resolve_agent_name=None,
    identify_agent=None,
    utc_now=None
) -> dict:
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
    resolved_agent_name = resolve_agent_name(params) if resolve_agent_name else None
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
        caller_name = identify_agent(params, caller_pid) if identify_agent else None
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

    # Resize to a stable width before capture so wrapped pane output is predictable.
    capture_width = params.get("capture_width", 80)
    if capture_width is not None:
        try:
            capture_width = int(capture_width)
        except ValueError:
            raise ValueError("capture_width must be an integer")
        if capture_width > 0:
            try:
                tmux_util.resize_pane_width(tmux_pane, capture_width, tmux_socket)
            except Exception as e:
                raise RuntimeError(f"Failed to resize pane before capture: {e}")

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

    captured_at = utc_now() if utc_now else None

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
