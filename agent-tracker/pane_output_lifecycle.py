"""Lifecycle helpers for safe local tmux pipe-pane output capture."""

from __future__ import annotations

import logging
import os
import secrets
import shlex
import sys
import time
import uuid
from pathlib import Path

import config
import state
import tmux_util

BROCCOLI_PIPE_MARKER_OPTION = "@broccoli_pipe_instance_id"
BROCCOLI_PIPE_DESIRED_OPTION = "@broccoli_pipe_output_enabled"


def _env_bool(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def pane_output_support_enabled() -> bool:
    """Returns whether operator config allows pane-output pipe controls."""
    env_value = _env_bool("AGENT_TRACKER_PANE_OUTPUT_ENABLED")
    if env_value is None:
        env_value = _env_bool("BROCCOLI_COMMS_PANE_OUTPUT_ENABLED")
    if env_value is not None:
        return env_value
    return bool(config.get("pane_output", "enabled", False))


def _configured_agent_types() -> set[str]:
    raw = os.environ.get("AGENT_TRACKER_PANE_OUTPUT_AGENT_TYPES")
    if raw is None:
        raw = config.get("pane_output", "agent_types", [])
    if isinstance(raw, str):
        values = raw.split(",")
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    return {str(value).strip().lower() for value in values if str(value).strip()}


def pane_output_allowed_for_agent(info: dict) -> bool:
    """Returns whether pane-output may be enabled for this local agent."""
    if not pane_output_support_enabled():
        return False
    allowed_types = _configured_agent_types()
    if not allowed_types:
        return True
    agent_type = str(info.get("agent_type") or info.get("agent_cmd") or info.get("model_type") or "unknown").lower()
    agent_cmd = str(info.get("agent_cmd") or "").lower()
    model_type = str(info.get("model_type") or "").lower()
    return agent_type in allowed_types or agent_cmd in allowed_types or model_type in allowed_types


def _pipe_reader_path() -> str:
    return str(Path(__file__).resolve().with_name("pipe_reader.py"))


def _pipe_reader_command(*, agent_id: str, tmux_pane: str, pipe_instance_id: str, pipe_token: str, socket_path: str) -> str:
    return shlex.join([
        sys.executable,
        _pipe_reader_path(),
        "--socket", socket_path,
        "--agent-id", agent_id,
        "--tmux-pane", tmux_pane,
        "--pipe-instance-id", pipe_instance_id,
        "--pipe-token", pipe_token,
    ])


def _tmux_args(args: list[str], tmux_socket: str | None = None) -> list[str]:
    """Builds args for tmux_util.run_tmux_cmd(cmd, timeout=5)."""
    return tmux_util.tmux_command(args, tmux_socket)[1:]


def _run_tmux(args: list[str], tmux_socket: str | None = None):
    return tmux_util.run_tmux_cmd(_tmux_args(args, tmux_socket))


def _pane_pipe_status(tmux_pane: str, tmux_socket: str | None = None) -> tuple[bool, str | None]:
    out = _run_tmux([
        "display-message",
        "-p",
        "-t",
        tmux_pane,
        f"#{{pane_pipe}}|#{{{BROCCOLI_PIPE_MARKER_OPTION}}}",
    ], tmux_socket)
    pipe_flag, _, marker = out.partition("|")
    return pipe_flag == "1", (marker or None)


def _set_pipe_marker(tmux_pane: str, pipe_instance_id: str, tmux_socket: str | None = None) -> None:
    _run_tmux(["set-option", "-p", "-t", tmux_pane, BROCCOLI_PIPE_MARKER_OPTION, pipe_instance_id], tmux_socket)


def _set_pipe_desired(tmux_pane: str, enabled: bool, tmux_socket: str | None = None) -> None:
    _run_tmux(["set-option", "-p", "-t", tmux_pane, BROCCOLI_PIPE_DESIRED_OPTION, "1" if enabled else "0"], tmux_socket)


def _clear_pipe_desired(tmux_pane: str, tmux_socket: str | None = None) -> None:
    try:
        _run_tmux(["set-option", "-p", "-u", "-t", tmux_pane, BROCCOLI_PIPE_DESIRED_OPTION], tmux_socket)
    except Exception as exc:
        logging.debug("failed to clear broccoli pipe desired flag pane=%s: %s", tmux_pane, exc)


def _pane_pipe_desired(tmux_pane: str, tmux_socket: str | None = None) -> bool:
    out = _run_tmux(["display-message", "-p", "-t", tmux_pane, f"#{{{BROCCOLI_PIPE_DESIRED_OPTION}}}"], tmux_socket)
    return str(out).strip().lower() in {"1", "true", "yes", "on"}


def _clear_pipe_marker(tmux_pane: str, tmux_socket: str | None = None) -> None:
    try:
        _run_tmux(["set-option", "-p", "-u", "-t", tmux_pane, BROCCOLI_PIPE_MARKER_OPTION], tmux_socket)
    except Exception as exc:
        logging.debug("failed to clear broccoli pipe marker pane=%s: %s", tmux_pane, exc)


def _detach_pipe(tmux_pane: str, tmux_socket: str | None = None) -> None:
    _run_tmux(["pipe-pane", "-t", tmux_pane], tmux_socket)


def _attach_pipe(tmux_pane: str, command: str, tmux_socket: str | None = None) -> None:
    _run_tmux(["pipe-pane", "-o", "-t", tmux_pane, command], tmux_socket)


def _require_local_pane_agent(name_or_id: str) -> tuple[str, str, dict]:
    if not isinstance(name_or_id, str) or not name_or_id or "/" in name_or_id or name_or_id.startswith("registry:"):
        raise ValueError("agent must be a local agent name or id")
    info = state.get_agent(name_or_id)
    if not info:
        raise ValueError("local agent not found")
    agent_id = info.get("agent_id") or info.get("uuid")
    agent_name = state.get_agent_name_by_id(agent_id) if agent_id else None
    if not agent_id or not agent_name:
        raise ValueError("local agent not found")
    if info.get("scope") == "remote":
        raise ValueError("remote agents cannot be piped locally")
    if not info.get("tmux_pane"):
        raise ValueError("agent has no local tmux pane")
    return agent_id, agent_name, info


def enable_pane_output(name_or_id: str, *, rotate: bool = True, recovery: bool = False) -> dict:
    """Enables a broccoli-owned tmux pipe for one local pane.

    Existing non-broccoli pipes are not clobbered. Existing broccoli-owned pipes
    are detached before a fresh pipe instance is attached, so duplicate enables
    rotate credentials rather than creating duplicate pipes.
    """
    agent_id, agent_name, info = _require_local_pane_agent(name_or_id)
    if not pane_output_support_enabled():
        raise RuntimeError("pane output support is disabled by configuration")
    if not pane_output_allowed_for_agent(info):
        raise RuntimeError("pane output support is disabled for this agent type")
    tmux_pane = info.get("tmux_pane")
    tmux_socket = info.get("tmux_socket")

    pane_has_pipe, marker = _pane_pipe_status(tmux_pane, tmux_socket)
    current_instance = info.get("pipe_instance_id")
    if pane_has_pipe and not marker:
        raise RuntimeError("refusing to clobber existing non-broccoli pane pipe")
    if pane_has_pipe and marker:
        if marker != current_instance and not recovery:
            raise RuntimeError("refusing to clobber pane pipe with mismatched broccoli marker")
        if not rotate and info.get("pipe_output_enabled") and marker == current_instance:
            return {
                "enabled": True,
                "attached": False,
                "already_attached": True,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "tmux_pane": tmux_pane,
                "pipe_instance_id": marker,
            }
        _detach_pipe(tmux_pane, tmux_socket)
        _clear_pipe_marker(tmux_pane, tmux_socket)

    pipe_instance_id = str(uuid.uuid4())
    pipe_token = secrets.token_urlsafe(32)
    command = _pipe_reader_command(
        agent_id=agent_id,
        tmux_pane=tmux_pane,
        pipe_instance_id=pipe_instance_id,
        pipe_token=pipe_token,
        socket_path=state.SOCKET_PATH,
    )

    if not state.configure_pane_output(
        agent_id,
        pipe_instance_id=pipe_instance_id,
        pipe_token=pipe_token,
        tmux_pane=tmux_pane,
        enabled=True,
    ):
        raise ValueError("local agent not found")

    try:
        _set_pipe_desired(tmux_pane, True, tmux_socket)
        _set_pipe_marker(tmux_pane, pipe_instance_id, tmux_socket)
        _attach_pipe(tmux_pane, command, tmux_socket)
        state.update_agent(agent_id, pipe_attached_at=time.time(), pipe_broccoli_owned=True)
    except Exception:
        state.clear_pane_output(agent_id)
        _clear_pipe_marker(tmux_pane, tmux_socket)
        _clear_pipe_desired(tmux_pane, tmux_socket)
        raise

    return {
        "enabled": True,
        "attached": True,
        "already_attached": False,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "tmux_pane": tmux_pane,
        "pipe_instance_id": pipe_instance_id,
    }


def disable_pane_output(name_or_id: str) -> dict:
    """Disables broccoli-owned pane output and detaches only owned pipes."""
    agent_id, agent_name, info = _require_local_pane_agent(name_or_id)
    tmux_pane = info.get("tmux_pane")
    tmux_socket = info.get("tmux_socket")
    pipe_instance_id = info.get("pipe_instance_id")
    detached = False

    try:
        pane_has_pipe, marker = _pane_pipe_status(tmux_pane, tmux_socket)
        if pane_has_pipe and marker and marker == pipe_instance_id:
            _detach_pipe(tmux_pane, tmux_socket)
            detached = True
        if marker and (not pipe_instance_id or marker == pipe_instance_id):
            _clear_pipe_marker(tmux_pane, tmux_socket)
        _clear_pipe_desired(tmux_pane, tmux_socket)
    finally:
        state.clear_pane_output(agent_id)

    return {
        "enabled": False,
        "detached": detached,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "tmux_pane": tmux_pane,
        "pipe_instance_id": pipe_instance_id,
    }


def pane_output_status(name_or_id: str) -> dict:
    """Returns non-secret local pane-output control status for one agent."""
    agent_id, agent_name, info = _require_local_pane_agent(name_or_id)
    return {
        "enabled": bool(info.get("pipe_output_enabled")),
        "configured": pane_output_allowed_for_agent(info),
        "agent_id": agent_id,
        "agent_name": agent_name,
        "tmux_pane": info.get("tmux_pane"),
        "pipe_instance_id": info.get("pipe_instance_id"),
        "attached_at": info.get("pipe_attached_at"),
    }


def recover_enabled_pane_outputs() -> dict:
    """Reattaches explicitly opted-in broccoli-owned pane pipes after tracker recovery.

    Recovery rotates credentials, never reuses stale pipe tokens, and refuses to
    clobber panes that have a non-broccoli pipe with no broccoli marker.
    """
    results = {"attempted": 0, "reattached": 0, "skipped": 0, "errors": 0}
    if not pane_output_support_enabled():
        return results
    agents = state.get_all_agents()
    for agent_name, info in agents.items():
        tmux_pane = info.get("tmux_pane")
        if not tmux_pane or not pane_output_allowed_for_agent(info):
            results["skipped"] += 1
            continue
        try:
            if not _pane_pipe_desired(tmux_pane, info.get("tmux_socket")):
                results["skipped"] += 1
                continue
            results["attempted"] += 1
            enable_pane_output(info.get("agent_id") or agent_name, rotate=True, recovery=True)
            results["reattached"] += 1
        except Exception as exc:
            results["errors"] += 1
            logging.debug("best-effort pane output recovery failed for %s: %s", agent_name, exc)
    return results


def cleanup_pane_output_best_effort(name_or_id: str) -> None:
    info = state.get_agent(name_or_id)
    if not info or not (info.get("pipe_output_enabled") or info.get("pipe_instance_id") or info.get("pipe_broccoli_owned")):
        return
    try:
        disable_pane_output(name_or_id)
    except Exception as exc:
        logging.debug("best-effort pane output cleanup failed for %s: %s", name_or_id, exc)
