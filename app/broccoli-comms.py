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
import signal
import socket
import subprocess
import sys
import time

APP = "broccoli-comms"
SESSION = "broccoli-comms"


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


def load_config() -> dict:
    p = paths()["config_json"]
    if not p.exists():
        p.write_text(json.dumps({"agents": {}}, indent=2) + "\n")
    return json.loads(p.read_text())


def window_exists(name: str) -> bool:
    result = tmux("list-windows", "-t", SESSION, "-F", "#{window_name}", check=False)
    return result.returncode == 0 and name in result.stdout.splitlines()


def reconcile_agents() -> None:
    cfg = load_config()
    agents = cfg.get("agents") or {}
    for name, spec in agents.items():
        if window_exists(name):
            continue
        cwd = spec.get("cwd") or str(Path.home())
        command = spec.get("command") or "bash"
        launch = " ".join([
            f"SUGGESTED_AGENT_NAME={shlex.quote(name)}",
            f"AGENT_TRACKER_SOCKET={shlex.quote(str(paths()['tracker_socket']))}",
            shlex.quote(wrapper_path()),
            command,
        ])
        tmux("new-window", "-d", "-t", SESSION, "-n", name, "-c", cwd, launch)


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


def status(_args: argparse.Namespace) -> None:
    print(json.dumps({
        "tracker_socket": str(paths()["tracker_socket"]),
        "tracker_up": can_connect(paths()["tracker_socket"]),
        "tmux_socket": str(paths()["tmux_socket"]),
        "tmux_up": tmux("has-session", "-t", SESSION, check=False).returncode == 0,
        "config": str(paths()["config_json"]),
    }, indent=2))


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
    for exe in ["tmux", sys.executable]:
        print(f"{exe}: ok")
    print(f"tracker script: {tracker_script()}")
    print(f"wrapper: {wrapper_path()}")
    print(f"tui: {tui_path()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Broccoli Comms runtime")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("start").set_defaults(func=start)
    sub.add_parser("ui").set_defaults(func=ui)
    sub.add_parser("open").set_defaults(func=ui)
    sub.add_parser("attach").set_defaults(func=attach)
    sub.add_parser("status").set_defaults(func=status)
    sub.add_parser("stop").set_defaults(func=stop)
    sub.add_parser("doctor").set_defaults(func=doctor)
    args = parser.parse_args()
    if not hasattr(args, "func"):
        args.func = ui
    args.func(args)


if __name__ == "__main__":
    main()
