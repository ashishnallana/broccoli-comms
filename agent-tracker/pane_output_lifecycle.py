"""Lifecycle helpers for safe local tmux pipe-pane output capture."""

from __future__ import annotations

import logging
import secrets
import shlex
import sys
import time
import uuid
from pathlib import Path

import state
import tmux_util

BROCCOLI_PIPE_MARKER_OPTION = "@broccoli_pipe_instance_id"


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


def enable_pane_output(name_or_id: str, *, rotate: bool = True) -> dict:
    """Enables a broccoli-owned tmux pipe for one local pane.

    Existing non-broccoli pipes are not clobbered. Existing broccoli-owned pipes
    are detached before a fresh pipe instance is attached, so duplicate enables
    rotate credentials rather than creating duplicate pipes.
    """
    agent_id, agent_name, info = _require_local_pane_agent(name_or_id)
    tmux_pane = info.get("tmux_pane")
    tmux_socket = info.get("tmux_socket")

    pane_has_pipe, marker = _pane_pipe_status(tmux_pane, tmux_socket)
    current_instance = info.get("pipe_instance_id")
    if pane_has_pipe and not marker:
        raise RuntimeError("refusing to clobber existing non-broccoli pane pipe")
    if pane_has_pipe and marker:
        if marker != current_instance:
            raise RuntimeError("refusing to clobber pane pipe with mismatched broccoli marker")
        if not rotate and info.get("pipe_output_enabled"):
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
        _set_pipe_marker(tmux_pane, pipe_instance_id, tmux_socket)
        _attach_pipe(tmux_pane, command, tmux_socket)
        state.update_agent(agent_id, pipe_attached_at=time.time(), pipe_broccoli_owned=True)
    except Exception:
        state.clear_pane_output(agent_id)
        _clear_pipe_marker(tmux_pane, tmux_socket)
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


def cleanup_pane_output_best_effort(name_or_id: str) -> None:
    try:
        disable_pane_output(name_or_id)
    except Exception as exc:
        logging.debug("best-effort pane output cleanup failed for %s: %s", name_or_id, exc)
