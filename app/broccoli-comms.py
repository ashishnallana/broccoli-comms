#!/usr/bin/env python3
"""Standalone launcher for the Broccoli Comms agent runtime.

This launcher owns a private tmux server and a private agent-tracker socket so it
can run independently of a user's tmux/Home Manager setup.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time

APP = "broccoli-comms"
VERSION = os.environ.get("BROCCOLI_COMMS_VERSION", "0.1.0")
SESSION = "broccoli-comms"
MANAGED_AGENT_OPTION = "@broccoli_managed_agent"
AGENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def xdg_runtime() -> Path:
    override = os.environ.get("BROCCOLI_COMMS_RUNTIME_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{os.getuid()}") / APP


def xdg_cache() -> Path:
    return Path(os.environ.get("BROCCOLI_COMMS_CACHE_DIR") or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP)


def xdg_config() -> Path:
    return Path(os.environ.get("BROCCOLI_COMMS_CONFIG_DIR") or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def paths() -> dict[str, Path]:
    runtime = xdg_runtime()
    cache = xdg_cache()
    config = xdg_config()
    return {
        "runtime": runtime,
        "cache": cache,
        "config": config,
        "tmux_socket": runtime / "tmux.sock",
        "tracker_socket": runtime / "agent-tracker.sock",
        "tracker_pid": runtime / "agent-tracker.pid",
        "tracker_log": cache / "agent-tracker.log",
        "tmux_conf": config / "tmux.conf",
        "config_json": config / "config.json",
    }


def ensure_dirs() -> None:
    for key in ("runtime", "cache", "config"):
        paths()[key].mkdir(parents=True, exist_ok=True)


def base_env() -> dict[str, str]:
    p = paths()
    env = os.environ.copy()
    env.pop("TMUX", None)
    env.pop("TMUX_PANE", None)
    env.update({
        "BROCCOLI_COMMS_APP_RUNTIME": "1",
        "BROCCOLI_COMMS_RUNTIME_DIR": str(p["runtime"]),
        "BROCCOLI_COMMS_CACHE_DIR": str(p["cache"]),
        "BROCCOLI_COMMS_CONFIG_DIR": str(p["config"]),
        "BROCCOLI_COMMS_TMUX_SOCKET": str(p["tmux_socket"]),
        "AGENT_TRACKER_SOCKET": str(p["tracker_socket"]),
        "AGENT_TRACKER_TMUX_SOCKET": str(p["tmux_socket"]),
        "XDG_CACHE_HOME": str(p["cache"]),
        "AGENT_TRACKER_HTTP_PORT": env.get("AGENT_TRACKER_HTTP_PORT", "19876"),
    })
    bin_dir = repo_root() / "bin"
    env["PATH"] = f"{bin_dir}:{repo_root() / 'wrapper'}:{env.get('PATH', '')}"
    return env


def can_connect(sock: Path) -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.3)
        s.connect(str(sock))
        s.close()
        return True
    except OSError:
        return False


def tracker_rpc(method: str, params: dict | None = None) -> object | None:
    sock_path = paths()["tracker_socket"]
    s = None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(str(sock_path))
        s.sendall(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}).encode())
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        data = json.loads(b"".join(chunks).decode())
        if data.get("error"):
            raise RuntimeError(data["error"].get("message", "tracker RPC error"))
        return data.get("result")
    except OSError:
        return None
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def tracker_script() -> str:
    return os.environ.get("BROCCOLI_COMMS_AGENT_TRACKER") or str(repo_root() / "agent-tracker" / "agent-tracker.py")


def wrapper_path() -> str:
    return os.environ.get("BROCCOLI_COMMS_AGENT_WRAPPER") or str(repo_root() / "wrapper" / "agent-wrapper.sh")


def tui_path() -> str:
    return os.environ.get("BROCCOLI_COMMS_AGENT_COMMUNICATOR_TUI") or "agent-communicator"


def ensure_tracker() -> None:
    ensure_dirs()
    p = paths()
    if can_connect(p["tracker_socket"]):
        return
    if p["tracker_socket"].exists():
        p["tracker_socket"].unlink()
    log = open(p["tracker_log"], "ab", buffering=0)
    proc = subprocess.Popen([sys.executable, tracker_script()], env=base_env(), stdout=log, stderr=log, start_new_session=True)
    p["tracker_pid"].write_text(str(proc.pid))
    for _ in range(50):
        if can_connect(p["tracker_socket"]):
            return
        if proc.poll() is not None:
            raise SystemExit(f"agent-tracker exited early; see {p['tracker_log']}")
        time.sleep(0.1)
    raise SystemExit(f"agent-tracker did not become ready; see {p['tracker_log']}")


def write_tmux_conf() -> None:
    p = paths()
    if p["tmux_conf"].exists():
        return
    p["tmux_conf"].write_text(
        "\n".join([
            "set -g mouse on",
            "set -g status off",
            "set -g pane-border-status bottom",
            'set -g pane-border-format "#[fg=green]#{?@agent_name,#{@agent_name},pane} #[fg=colour8]#T"',
            "set -g history-limit 10000",
            "set-window-option -g allow-rename off",
            "set-option -g set-titles off",
            "",
        ])
    )


def tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = paths()
    return subprocess.run(["tmux", "-S", str(p["tmux_socket"]), *args], env=base_env(), check=check, text=True, capture_output=True)


def ensure_tmux() -> None:
    ensure_dirs()
    write_tmux_conf()
    if tmux("has-session", "-t", SESSION, check=False).returncode == 0:
        return
    tmux("-f", str(paths()["tmux_conf"]), "new-session", "-d", "-s", SESSION, "-c", str(Path.home()), "bash")


def default_config() -> dict:
    return {"agents": {}}


def normalize_config(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError("config must be a JSON object")
    agents = cfg.get("agents") or {}
    if not isinstance(agents, dict):
        raise ValueError("config agents must be an object")
    normalized = {**cfg, "agents": agents}
    for name, spec in agents.items():
        validate_agent_name(name)
        if not isinstance(spec, dict):
            raise ValueError(f"agent {name!r} config must be an object")
    return normalized


def load_config() -> dict:
    p = paths()["config_json"]
    if not p.exists():
        save_config(default_config())
    try:
        return normalize_config(json.loads(p.read_text()))
    except json.JSONDecodeError as e:
        raise SystemExit(f"failed to parse config {p}: {e}")
    except ValueError as e:
        raise SystemExit(f"invalid config {p}: {e}")


def save_config(cfg: dict) -> None:
    ensure_dirs()
    cfg = normalize_config(cfg)
    p = paths()["config_json"]
    with tempfile.NamedTemporaryFile("w", dir=p.parent, delete=False) as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
        f.write("\n")
        tmp = Path(f.name)
    tmp.replace(p)


def validate_agent_name(name: str) -> None:
    if not name or not AGENT_NAME_RE.match(name):
        raise ValueError("agent name must contain only letters, numbers, dot, underscore, and dash")


def agent_spec(cfg: dict, name: str) -> dict:
    agents = cfg.get("agents") or {}
    if name not in agents:
        raise SystemExit(f"agent {name!r} is not configured")
    return agents[name]


def tmux_up() -> bool:
    return tmux("has-session", "-t", SESSION, check=False).returncode == 0


def managed_windows(name: str | None = None) -> list[dict[str, str]]:
    if not tmux_up():
        return []
    fmt = f"#{{window_id}}\t#{{window_name}}\t#{{{MANAGED_AGENT_OPTION}}}\t#{{pane_id}}\t#{{pane_current_path}}"
    result = tmux("list-windows", "-t", SESSION, "-F", fmt, check=False)
    if result.returncode != 0:
        return []
    windows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 4)
        if len(parts) != 5:
            continue
        window_id, window_name, managed_agent, pane_id, pane_current_path = parts
        if not managed_agent:
            continue
        if name is not None and managed_agent != name:
            continue
        windows.append({
            "window_id": window_id,
            "window_name": window_name,
            "managed_agent": managed_agent,
            "pane_id": pane_id,
            "cwd": pane_current_path or None,
        })
    return windows


def window_exists(name: str) -> bool:
    return bool(managed_windows(name))


def agent_window_pane(name: str) -> str | None:
    windows = managed_windows(name)
    if not windows:
        return None
    return windows[0].get("pane_id") or None


def unregister_agent_pane(pane_id: str | None) -> None:
    if pane_id and can_connect(paths()["tracker_socket"]):
        try:
            tracker_rpc("unregister", {"tmux_pane": pane_id})
        except Exception:
            pass


def kill_agent_window(name: str) -> bool:
    killed_any = False
    for window in managed_windows(name):
        window_id = window["window_id"]
        pane_id = window.get("pane_id")
        killed = tmux("kill-window", "-t", window_id, check=False).returncode == 0
        if killed:
            killed_any = True
            unregister_agent_pane(pane_id)
    return killed_any


def managed_agent_launch_command(name: str, command: str) -> str:
    p = paths()
    return " ".join([
        f"SUGGESTED_AGENT_NAME={shlex.quote(name)}",
        f"AGENT_TRACKER_SOCKET={shlex.quote(str(p['tracker_socket']))}",
        f"AGENT_TRACKER_TMUX_SOCKET={shlex.quote(str(p['tmux_socket']))}",
        f"BROCCOLI_COMMS_TMUX_SOCKET={shlex.quote(str(p['tmux_socket']))}",
        shlex.quote(wrapper_path()),
        command,
    ])


def reconcile_agents(names: set[str] | None = None) -> list[str]:
    cfg = load_config()
    agents = cfg.get("agents") or {}
    launched = []
    for name, spec in agents.items():
        if names is not None and name not in names:
            continue
        if window_exists(name):
            continue
        cwd = os.path.abspath(os.path.expanduser(spec.get("cwd") or str(Path.home())))
        if not os.path.isdir(cwd):
            raise SystemExit(f"configured cwd for agent {name!r} does not exist: {cwd}")
        command = spec.get("command") or "bash"
        launch = managed_agent_launch_command(name, command)
        result = tmux("new-window", "-d", "-P", "-F", "#{window_id}", "-t", SESSION, "-n", name, "-c", cwd, launch)
        window_id = result.stdout.strip()
        if window_id:
            tmux("set-option", "-w", "-t", window_id, MANAGED_AGENT_OPTION, name)
        launched.append(name)
    return launched


def start(_args: argparse.Namespace) -> None:
    ensure_tracker()
    ensure_tmux()
    reconcile_agents()
    print(f"{APP} runtime started")
    print(f"tracker socket: {paths()['tracker_socket']}")
    print(f"tmux socket:    {paths()['tmux_socket']}")


def ui(args: argparse.Namespace) -> None:
    start(args)
    os.execvpe(tui_path(), [tui_path()], base_env())


def attach(_args: argparse.Namespace) -> None:
    ensure_tracker()
    ensure_tmux()
    os.execvpe("tmux", ["tmux", "-S", str(paths()["tmux_socket"]), "attach", "-t", SESSION], base_env())


def tracker_agents() -> dict:
    if not can_connect(paths()["tracker_socket"]):
        return {}
    try:
        agents = tracker_rpc("list", {})
        return agents if isinstance(agents, dict) else {}
    except Exception:
        return {}


def agent_list_payload() -> dict:
    cfg = load_config()
    agents = cfg.get("agents") or {}
    runtime_up = tmux_up()
    tracker_up = can_connect(paths()["tracker_socket"])
    windows_by_name: dict[str, list[dict[str, str]]] = {}
    for window in managed_windows():
        windows_by_name.setdefault(window["managed_agent"], []).append(window)
    tracker_by_name = tracker_agents()
    return {
        "app": APP,
        "version": VERSION,
        "config": str(paths()["config_json"]),
        "runtime": {
            "tracker_up": tracker_up,
            "tmux_up": runtime_up,
            "tmux_session": SESSION,
        },
        "agents": {
            name: {
                "name": name,
                "configured": {
                    "cwd": spec.get("cwd"),
                    "command": spec.get("command"),
                },
                # Backward-compatible direct fields for simple JSON consumers.
                "cwd": spec.get("cwd"),
                "command": spec.get("command"),
                "running": bool(windows_by_name.get(name)),
                "window_exists": bool(windows_by_name.get(name)),
                "managed_windows": windows_by_name.get(name, []),
                "tracker": tracker_by_name.get(name),
            }
            for name, spec in sorted(agents.items())
        },
    }


def status_payload() -> dict:
    p = paths()
    cfg = load_config()
    configured_agents = cfg.get("agents") or {}
    tracker_up = can_connect(p["tracker_socket"])
    session_up = tmux_up()
    managed = managed_windows() if session_up else []
    return {
        "app": APP,
        "version": VERSION,
        "paths": {
            "runtime_dir": str(p["runtime"]),
            "cache_dir": str(p["cache"]),
            "config_dir": str(p["config"]),
        },
        "tracker": {
            "socket": str(p["tracker_socket"]),
            "up": tracker_up,
        },
        "tmux": {
            "socket": str(p["tmux_socket"]),
            "up": session_up,
            "session": SESSION,
        },
        "config": {
            "path": str(p["config_json"]),
        },
        "agents": {
            "configured_count": len(configured_agents),
            "managed_running_count": len(managed),
            "managed_windows": managed,
        },
        # Backward-compatible aliases used by existing smoke checks.
        "tracker_socket": str(p["tracker_socket"]),
        "tracker_up": tracker_up,
        "tmux_socket": str(p["tmux_socket"]),
        "tmux_up": session_up,
    }


def status(args: argparse.Namespace) -> None:
    print(json.dumps(status_payload(), indent=2, sort_keys=bool(getattr(args, "json", False))))


def agent_list(args: argparse.Namespace) -> None:
    payload = agent_list_payload()
    print(json.dumps(payload if args.json else payload["agents"], indent=2, sort_keys=True))


def agent_add(args: argparse.Namespace) -> None:
    try:
        validate_agent_name(args.name)
    except ValueError as e:
        raise SystemExit(str(e))
    cwd = os.path.abspath(os.path.expanduser(args.cwd))
    if not os.path.isdir(cwd):
        raise SystemExit(f"cwd does not exist: {cwd}")
    command = args.command.strip()
    if not command:
        raise SystemExit("--command must not be empty")
    cfg = load_config()
    agents = cfg.setdefault("agents", {})
    if args.name in agents and not args.force:
        raise SystemExit(f"agent {args.name!r} already exists; use --force to update")
    agents[args.name] = {"cwd": cwd, "command": command}
    save_config(cfg)
    print(json.dumps({"added": args.name, "config": str(paths()["config_json"]), "agent": agents[args.name]}, indent=2, sort_keys=True))


def agent_remove(args: argparse.Namespace) -> None:
    try:
        validate_agent_name(args.name)
    except ValueError as e:
        raise SystemExit(str(e))
    cfg = load_config()
    agents = cfg.get("agents") or {}
    if args.name not in agents:
        raise SystemExit(f"agent {args.name!r} is not configured")
    removed = agents.pop(args.name)
    save_config(cfg)
    window_killed = kill_agent_window(args.name)
    print(json.dumps({"removed": args.name, "window_killed": window_killed, "agent": removed}, indent=2, sort_keys=True))


def agent_restart(args: argparse.Namespace) -> None:
    try:
        validate_agent_name(args.name)
    except ValueError as e:
        raise SystemExit(str(e))
    cfg = load_config()
    agent_spec(cfg, args.name)
    ensure_tracker()
    ensure_tmux()
    window_killed = kill_agent_window(args.name)
    launched = reconcile_agents({args.name})
    print(json.dumps({"restarted": args.name, "window_killed": window_killed, "launched": args.name in launched}, indent=2, sort_keys=True))


def managed_window_for_agent(name: str) -> dict[str, str]:
    cfg = load_config()
    agent_spec(cfg, name)
    ensure_tracker()
    ensure_tmux()
    windows = managed_windows(name)
    if not windows:
        raise SystemExit(f"agent {name!r} is configured but has no running managed window; run `broccoli-comms start` or `broccoli-comms agent restart {name}`")
    return windows[0]


def focus_managed_window(name: str) -> dict[str, str]:
    window = managed_window_for_agent(name)
    window_id = window["window_id"]
    tmux("select-window", "-t", window_id)
    tmux("switch-client", "-t", window_id, check=False)
    return window


def agent_focus(args: argparse.Namespace) -> None:
    try:
        validate_agent_name(args.name)
    except ValueError as e:
        raise SystemExit(str(e))
    window = focus_managed_window(args.name)
    print(json.dumps({"focused": args.name, "window": window}, indent=2, sort_keys=True))


def agent_attach(args: argparse.Namespace) -> None:
    try:
        validate_agent_name(args.name)
    except ValueError as e:
        raise SystemExit(str(e))
    window = focus_managed_window(args.name)
    os.execvpe("tmux", ["tmux", "-S", str(paths()["tmux_socket"]), "attach", "-t", window["window_id"]], base_env())


def stop(_args: argparse.Namespace) -> None:
    p = paths()
    tmux("kill-server", check=False)
    for _ in range(50):
        if tmux("has-session", "-t", SESSION, check=False).returncode != 0:
            break
        time.sleep(0.1)
    if p["tmux_socket"].exists() and tmux("has-session", "-t", SESSION, check=False).returncode != 0:
        p["tmux_socket"].unlink(missing_ok=True)

    pid_file = p["tracker_pid"]
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
        except Exception:
            pass
        for _ in range(50):
            if not can_connect(p["tracker_socket"]):
                break
            time.sleep(0.1)
        if can_connect(p["tracker_socket"]):
            try:
                os.kill(int(pid_file.read_text().strip()), signal.SIGKILL)
            except Exception:
                pass
            for _ in range(20):
                if not can_connect(p["tracker_socket"]):
                    break
                time.sleep(0.1)
        pid_file.unlink(missing_ok=True)
    if p["tracker_socket"].exists() and not can_connect(p["tracker_socket"]):
        p["tracker_socket"].unlink(missing_ok=True)
    print(f"{APP} stopped")


def doctor(_args: argparse.Namespace) -> None:
    failures = []
    for exe in ["tmux", sys.executable]:
        resolved = exe if os.path.isabs(exe) and os.access(exe, os.X_OK) else shutil.which(exe)
        if resolved:
            print(f"{exe}: ok ({resolved})")
        else:
            print(f"{exe}: missing")
            failures.append(exe)

    for label, value in [("tracker script", tracker_script()), ("wrapper", wrapper_path())]:
        if os.path.exists(value):
            print(f"{label}: ok ({value})")
        else:
            print(f"{label}: missing ({value})")
            failures.append(label)
    print(f"tui: {tui_path()}")

    if failures:
        print("doctor failed: install missing dependencies/files. Nix packages include tmux; manual/non-Nix installs require system tmux and python3 on PATH.", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Broccoli Comms runtime")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("start").set_defaults(func=start)
    sub.add_parser("ui").set_defaults(func=ui)
    sub.add_parser("open").set_defaults(func=ui)
    sub.add_parser("attach").set_defaults(func=attach)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--json", action="store_true", help="Emit stable JSON runtime status")
    status_parser.set_defaults(func=status)
    sub.add_parser("stop").set_defaults(func=stop)
    sub.add_parser("doctor").set_defaults(func=doctor)

    agent = sub.add_parser("agent", help="Manage configured agents")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_list_parser = agent_sub.add_parser("list", help="List configured agents")
    agent_list_parser.add_argument("--json", action="store_true", help="Include config/runtime metadata in JSON output")
    agent_list_parser.set_defaults(func=agent_list)
    agent_add_parser = agent_sub.add_parser("add", help="Add or update a configured agent")
    agent_add_parser.add_argument("name", help="Agent/window name")
    agent_add_parser.add_argument("--cwd", required=True, help="Working directory")
    agent_add_parser.add_argument("--command", required=True, help="Command to run through agent-wrapper")
    agent_add_parser.add_argument("--force", action="store_true", help="Update an existing agent")
    agent_add_parser.set_defaults(func=agent_add)
    agent_remove_parser = agent_sub.add_parser("remove", help="Remove a configured agent and stop its managed window if running")
    agent_remove_parser.add_argument("name", help="Agent/window name")
    agent_remove_parser.set_defaults(func=agent_remove)
    agent_restart_parser = agent_sub.add_parser("restart", help="Restart a configured agent window")
    agent_restart_parser.add_argument("name", help="Agent/window name")
    agent_restart_parser.set_defaults(func=agent_restart)
    agent_focus_parser = agent_sub.add_parser("focus", help="Focus a running managed agent window in the private tmux session")
    agent_focus_parser.add_argument("name", help="Agent/window name")
    agent_focus_parser.set_defaults(func=agent_focus)
    agent_attach_parser = agent_sub.add_parser("attach", help="Attach to a running managed agent window in the private tmux session")
    agent_attach_parser.add_argument("name", help="Agent/window name")
    agent_attach_parser.set_defaults(func=agent_attach)
    args = parser.parse_args()
    if not hasattr(args, "func"):
        args.func = ui
    args.func(args)


if __name__ == "__main__":
    main()
