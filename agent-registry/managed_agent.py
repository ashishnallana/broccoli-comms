import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time


def default_tmux_socket() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(runtime_dir, f"tmux-{os.getuid()}", "default")


def ensure_env(home: str, tracker_socket: str | None = None, tmux_socket: str | None = None) -> None:
    os.environ.setdefault("HOME", home)
    os.environ.setdefault("USER", os.path.basename(home))
    os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    path_parts = [
        os.path.join(home, ".nix-profile", "bin"),
        f"/etc/profiles/per-user/{os.environ.get('USER', '')}/bin",
        "/nix/var/nix/profiles/default/bin",
        "/run/current-system/sw/bin",
        os.environ.get("PATH", ""),
    ]
    os.environ["PATH"] = ":".join(part for part in path_parts if part)
    if tracker_socket:
        os.environ.setdefault("AGENT_TRACKER_SOCKET", tracker_socket)
    tmux_socket = tmux_socket or default_tmux_socket()
    os.makedirs(os.path.dirname(tmux_socket), exist_ok=True)
    os.environ.setdefault("AGENT_REGISTRY_TMUX_SOCKET", tmux_socket)


def tmux_cmd(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["tmux"]
    if os.environ.get("AGENT_REGISTRY_TMUX_SOCKET"):
        cmd.extend(["-S", os.environ["AGENT_REGISTRY_TMUX_SOCKET"]])
    cmd.extend(args)
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=check,
        env=os.environ,
    )


def session_exists(session: str) -> bool:
    return tmux_cmd(["has-session", "-t", session], check=False).returncode == 0


def list_panes(session: str) -> list[dict]:
    out = tmux_cmd([
        "list-panes",
        "-t",
        session,
        "-F",
        "#{pane_id}\t#{pane_dead}\t#{pane_current_command}\t#{@agent_name}",
    ]).stdout.strip()
    if not out:
        return []
    panes = []
    for line in out.splitlines():
        pane_id, pane_dead, pane_cmd, agent_name = (line.split("\t") + ["", "", "", ""])[:4]
        panes.append({
            "pane_id": pane_id,
            "pane_dead": pane_dead == "1",
            "pane_current_command": pane_cmd,
            "agent_name": agent_name,
        })
    return panes


def build_launch_command(agent_name: str, command: str, wrapper_path: str, tracker_socket: str | None = None) -> str:
    command_parts = shlex.split(command)
    if not command_parts:
        raise ValueError("command must not be empty")
    env_parts = ["env", f"SUGGESTED_AGENT_NAME={agent_name}"]
    if tracker_socket:
        env_parts.append(f"AGENT_TRACKER_SOCKET={tracker_socket}")
    if os.environ.get("AGENT_REGISTRY_TMUX_SOCKET"):
        env_parts.append(f"AGENT_REGISTRY_TMUX_SOCKET={os.environ['AGENT_REGISTRY_TMUX_SOCKET']}")
    return shlex.join(env_parts + [wrapper_path, *command_parts])


def ensure_requirements(command: str, wrapper_path: str) -> None:
    missing = []
    if shutil.which("tmux") is None:
        missing.append("tmux")
    if shutil.which(wrapper_path) is None and not os.path.exists(wrapper_path):
        missing.append(wrapper_path)
    command_parts = shlex.split(command)
    if not command_parts:
        missing.append("command")
    elif shutil.which(command_parts[0]) is None and not os.path.exists(command_parts[0]):
        missing.append(command_parts[0])
    if missing:
        raise RuntimeError(f"missing required executables: {', '.join(missing)}")


def _find_named_pane(session: str, agent_name: str) -> dict | None:
    for pane in list_panes(session):
        if pane["agent_name"] == agent_name:
            return pane
    return None


def _mark_pane(pane_id: str, agent_name: str) -> None:
    tmux_cmd(["set-option", "-p", "-t", pane_id, "@agent_name", agent_name])
    tmux_cmd(["select-pane", "-t", pane_id, "-T", agent_name])


def _start_new_session(session: str, cwd: str, agent_name: str, launch_cmd: str) -> None:
    pane_id = tmux_cmd(["new-session", "-d", "-P", "-F", "#{pane_id}", "-s", session, "-n", agent_name, "-c", cwd, launch_cmd]).stdout.strip()
    if pane_id:
        _mark_pane(pane_id, agent_name)


def _start_new_window(session: str, cwd: str, agent_name: str, launch_cmd: str) -> None:
    pane_id = tmux_cmd(["new-window", "-d", "-P", "-F", "#{pane_id}", "-t", session, "-n", agent_name, "-c", cwd, launch_cmd]).stdout.strip()
    if pane_id:
        _mark_pane(pane_id, agent_name)


def reconcile_agent(agent_name: str, session: str, cwd: str, command: str, wrapper_path: str = "agent-wrapper", tracker_socket: str | None = None) -> str:
    ensure_requirements(command, wrapper_path)
    launch_cmd = build_launch_command(agent_name, command, wrapper_path, tracker_socket)
    if not session_exists(session):
        _start_new_session(session, cwd, agent_name, launch_cmd)
        return "session-created-started"
    pane = _find_named_pane(session, agent_name)
    if pane:
        if not pane["pane_dead"]:
            return "already-running"
        tmux_cmd(["respawn-pane", "-k", "-t", pane["pane_id"], "-c", cwd, launch_cmd])
        _mark_pane(pane["pane_id"], agent_name)
        return "respawned"
    _start_new_window(session, cwd, agent_name, launch_cmd)
    return "started"


def restart_agent(agent_name: str, session: str, cwd: str, command: str, wrapper_path: str = "agent-wrapper", tracker_socket: str | None = None, warning_lead_time_seconds: int = 300, warning_message: str | None = None) -> str:
    ensure_requirements(command, wrapper_path)
    if not session_exists(session):
        return reconcile_agent(agent_name, session, cwd, command, wrapper_path=wrapper_path, tracker_socket=tracker_socket)
    launch_cmd = build_launch_command(agent_name, command, wrapper_path, tracker_socket)
    pane = _find_named_pane(session, agent_name)
    if not pane or pane["pane_dead"]:
        return reconcile_agent(agent_name, session, cwd, command, wrapper_path=wrapper_path, tracker_socket=tracker_socket)
    if warning_lead_time_seconds > 0:
        minutes = warning_lead_time_seconds // 60
        message = warning_message or (f"Restarting in {minutes} minutes" if minutes > 0 else f"Restarting in {warning_lead_time_seconds} seconds")
        tmux_cmd(["send-keys", "-t", pane["pane_id"], message, "Enter"])
        time.sleep(warning_lead_time_seconds)
        pane = _find_named_pane(session, agent_name)
        if not pane or pane["pane_dead"]:
            return reconcile_agent(agent_name, session, cwd, command, wrapper_path=wrapper_path, tracker_socket=tracker_socket)
    tmux_cmd(["respawn-pane", "-k", "-t", pane["pane_id"], "-c", cwd, launch_cmd])
    _mark_pane(pane["pane_id"], agent_name)
    return "restarted"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile a registry-managed agent inside tmux")
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--tracker-socket")
    parser.add_argument("--wrapper-path", default="agent-wrapper")
    parser.add_argument("--tmux-socket")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--warning-lead-time-seconds", type=int, default=300)
    parser.add_argument("--warning-message")
    args = parser.parse_args()

    home = os.path.expanduser(args.home)
    cwd = os.path.expanduser(args.cwd)
    if cwd == "~":
        cwd = home
    ensure_env(home, args.tracker_socket, args.tmux_socket)

    try:
        if args.restart:
            result = restart_agent(
                args.agent_name,
                args.session,
                cwd,
                args.command,
                wrapper_path=args.wrapper_path,
                tracker_socket=args.tracker_socket,
                warning_lead_time_seconds=max(args.warning_lead_time_seconds, 0),
                warning_message=args.warning_message,
            )
        else:
            result = reconcile_agent(
                args.agent_name,
                args.session,
                cwd,
                args.command,
                wrapper_path=args.wrapper_path,
                tracker_socket=args.tracker_socket,
            )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
