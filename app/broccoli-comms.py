#!/usr/bin/env python3
"""Standalone launcher for the Broccoli Comms agent runtime.

This launcher owns a private agent-tracker socket and a managed tmux session.
By default the tmux session lives in the user's default tmux server; private tmux
compatibility mode is available with BROCCOLI_COMMS_TMUX_MODE=private.
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
import urllib.error
import urllib.parse
import urllib.request

APP = "broccoli-comms"
VERSION = os.environ.get("BROCCOLI_COMMS_VERSION", "0.1.0")
SESSION = "broccoli-comms-agents"
MANAGED_AGENT_OPTION = "@broccoli_managed_agent"
SHELL_WINDOW_OPTION = "@broccoli_shell_window"
UI_WINDOW_OPTION = "@broccoli_ui_window"
UI_WINDOW_NAME = "ui"
UI_AGENT_NAME = "agent-communicator"
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
        "registry_pid": runtime / "agent-registry.pid",
        "registry_log": cache / "agent-registry.log",
        "registry_state": cache / "agent-registry" / "state.json",
        "registry_config": config / "registry.json",
        "registries_json": config / "registries.json",
        "tmux_conf": config / "tmux.conf",
        "config_json": config / "config.json",
    }


def ensure_dirs() -> None:
    for key in ("runtime", "cache", "config"):
        paths()[key].mkdir(parents=True, exist_ok=True)


def tmux_mode() -> str:
    mode = os.environ.get("BROCCOLI_COMMS_TMUX_MODE", "default").lower()
    if mode not in {"default", "private"}:
        raise SystemExit("BROCCOLI_COMMS_TMUX_MODE must be 'default' or 'private'")
    return mode


def use_private_tmux() -> bool:
    return tmux_mode() == "private"


def tmux_socket_label() -> str | None:
    return str(paths()["tmux_socket"]) if use_private_tmux() else None


def base_env(preserve_agent_identity: bool = False) -> dict[str, str]:
    p = paths()
    env = os.environ.copy()
    strip_keys = ["TMUX", "TMUX_PANE", "SUGGESTED_AGENT_NAME"]
    if not preserve_agent_identity:
        strip_keys.extend(["AGENT_ID", "AGENT_NAME", "AGENT_UUID"])
    for key in strip_keys:
        env.pop(key, None)
    env.update({
        "BROCCOLI_COMMS_APP_RUNTIME": "1",
        "BROCCOLI_COMMS_RUNTIME_DIR": str(p["runtime"]),
        "BROCCOLI_COMMS_CACHE_DIR": str(p["cache"]),
        "BROCCOLI_COMMS_CONFIG_DIR": str(p["config"]),
        "AGENT_TRACKER_SOCKET": str(p["tracker_socket"]),
        "XDG_CACHE_HOME": str(p["cache"]),
        "AGENT_TRACKER_HTTP_PORT": env.get("AGENT_TRACKER_HTTP_PORT", "19876"),
    })
    if use_private_tmux():
        env["BROCCOLI_COMMS_TMUX_SOCKET"] = str(p["tmux_socket"])
        env["AGENT_TRACKER_TMUX_SOCKET"] = str(p["tmux_socket"])
    else:
        env.pop("BROCCOLI_COMMS_TMUX_SOCKET", None)
        env.pop("AGENT_TRACKER_TMUX_SOCKET", None)
    apply_configured_registries(env)
    launcher = broccoli_comms_launcher_argv()
    if len(launcher) == 1:
        env["BROCCOLI_COMMS_CLI"] = launcher[0]
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


def tracker_ctl_script() -> str:
    return os.environ.get("BROCCOLI_COMMS_AGENT_TRACKER_CTL") or str(repo_root() / "agent-tracker" / "agent-tracker-ctl.py")


def wrapper_path() -> str:
    return os.environ.get("BROCCOLI_COMMS_AGENT_WRAPPER") or str(repo_root() / "wrapper" / "agent-wrapper.sh")


def registry_script() -> str:
    return os.environ.get("BROCCOLI_COMMS_AGENT_REGISTRY") or str(repo_root() / "agent-registry" / "server.py")


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


def tmux_command(*args: str) -> list[str]:
    if use_private_tmux():
        return ["tmux", "-S", str(paths()["tmux_socket"]), *args]
    return ["tmux", *args]


def tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(tmux_command(*args), env=base_env(), check=check, text=True, capture_output=True)


def in_tmux_client() -> bool:
    return bool(os.environ.get("TMUX"))


def exec_tmux_interactive(target: str) -> None:
    if in_tmux_client():
        if use_private_tmux():
            raise SystemExit(
                "Broccoli Comms is using a private tmux socket. Run this command outside tmux, or attach manually:\n"
                f"  tmux -S {paths()['tmux_socket']} attach -t {target}"
            )
        result = subprocess.run(["tmux", "switch-client", "-t", target], env=os.environ.copy(), text=True, capture_output=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise SystemExit(f"failed to switch current tmux client to {target}{suffix}")
        return
    os.execvpe("tmux", tmux_command("attach", "-t", target), base_env())


def ensure_tmux() -> None:
    ensure_dirs()
    if tmux("has-session", "-t", SESSION, check=False).returncode == 0:
        return
    if use_private_tmux():
        write_tmux_conf()
        result = tmux("-f", str(paths()["tmux_conf"]), "new-session", "-d", "-P", "-F", "#{window_id}", "-s", SESSION, "-c", str(Path.home()), "bash")
    else:
        result = tmux("new-session", "-d", "-P", "-F", "#{window_id}", "-s", SESSION, "-c", str(Path.home()), "bash")
    window_id = result.stdout.strip()
    if window_id:
        tmux("set-option", "-w", "-t", window_id, SHELL_WINDOW_OPTION, "1", check=False)


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
        if "autostart" in spec and not isinstance(spec.get("autostart"), bool):
            raise ValueError(f"agent {name!r} autostart must be a boolean")
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


def agent_autostart(spec: dict) -> bool:
    return bool(spec.get("autostart", False))


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


def session_windows() -> list[dict[str, str]]:
    if not tmux_up():
        return []
    fmt = f"#{{window_id}}\t#{{window_name}}\t#{{pane_id}}\t#{{{MANAGED_AGENT_OPTION}}}\t#{{{UI_WINDOW_OPTION}}}\t#{{{SHELL_WINDOW_OPTION}}}"
    result = tmux("list-windows", "-t", SESSION, "-F", fmt, check=False)
    if result.returncode != 0:
        return []
    windows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 5)
        if len(parts) != 6:
            continue
        window_id, window_name, pane_id, managed_agent, ui_marker, shell_marker = parts
        windows.append({
            "window_id": window_id,
            "window_name": window_name,
            "pane_id": pane_id,
            "managed_agent": managed_agent,
            "ui_marker": ui_marker,
            "shell_marker": shell_marker,
        })
    return windows


def ui_tracker_pane() -> str | None:
    if not can_connect(paths()["tracker_socket"]):
        return None
    ui_info = tracker_agents().get(UI_AGENT_NAME) or {}
    return ui_info.get("tmux_pane")


def is_broccoli_tmux_window(window: dict[str, str], ui_pane: str | None = None) -> bool:
    pane_id = window.get("pane_id")
    return (
        bool(window.get("managed_agent"))
        or window.get("ui_marker") == "1"
        or bool(ui_pane and pane_id == ui_pane and window.get("window_name") == UI_WINDOW_NAME)
        or window.get("shell_marker") == "1"
    )


def has_broccoli_tmux_windows() -> bool:
    ui_pane = ui_tracker_pane()
    return any(is_broccoli_tmux_window(window, ui_pane) for window in session_windows())


def kill_broccoli_tmux_windows() -> None:
    ui_pane = ui_tracker_pane()
    for window in session_windows():
        if not is_broccoli_tmux_window(window, ui_pane):
            continue
        pane_id = window.get("pane_id")
        if tmux("kill-window", "-t", window["window_id"], check=False).returncode == 0:
            unregister_agent_pane(pane_id)


def tmux_env_assignments_for_pane() -> list[str]:
    if not use_private_tmux():
        return []
    p = paths()
    return [
        f"AGENT_TRACKER_TMUX_SOCKET={shlex.quote(str(p['tmux_socket']))}",
        f"BROCCOLI_COMMS_TMUX_SOCKET={shlex.quote(str(p['tmux_socket']))}",
    ]


def shell_env_assignment(key: str, value: str) -> str:
    return f"{key}={shlex.quote(str(value))}"


def broccoli_comms_launcher_argv() -> list[str]:
    candidate = sys.argv[0] or ""
    if candidate:
        if os.path.isabs(candidate) or os.sep in candidate:
            path = Path(candidate).expanduser().resolve()
            if path.exists():
                if os.access(path, os.X_OK):
                    return [str(path)]
                return [sys.executable, str(path)]
        resolved = shutil.which(candidate, path=f"{repo_root() / 'bin'}:{os.environ.get('PATH', '')}")
        if resolved:
            return [resolved]
    local_launcher = repo_root() / "bin" / "broccoli-comms"
    if local_launcher.exists():
        if os.access(local_launcher, os.X_OK):
            return [str(local_launcher)]
        return [sys.executable, str(local_launcher)]
    return [sys.executable, str(Path(__file__).resolve())]


def managed_track_env_assignments() -> list[str]:
    env = base_env()
    if use_private_tmux():
        env["BROCCOLI_COMMS_TMUX_MODE"] = "private"
    elif "BROCCOLI_COMMS_TMUX_MODE" in os.environ:
        env["BROCCOLI_COMMS_TMUX_MODE"] = tmux_mode()
    keys = [
        "PATH",
        "BROCCOLI_COMMS_APP_RUNTIME",
        "BROCCOLI_COMMS_RUNTIME_DIR",
        "BROCCOLI_COMMS_CACHE_DIR",
        "BROCCOLI_COMMS_CONFIG_DIR",
        "BROCCOLI_COMMS_TMUX_MODE",
        "BROCCOLI_COMMS_AGENT_TRACKER",
        "BROCCOLI_COMMS_AGENT_TRACKER_CTL",
        "BROCCOLI_COMMS_AGENT_WRAPPER",
        "BROCCOLI_COMMS_AGENT_REGISTRY",
        "BROCCOLI_COMMS_AGENT_COMMUNICATOR_TUI",
        "AGENT_TRACKER_SOCKET",
        "XDG_CACHE_HOME",
        "AGENT_TRACKER_HOSTNAME",
        "AGENT_TRACKER_HTTP_PORT",
        "AGENT_REGISTRIES_JSON",
        "AGENT_REGISTRY_TOKEN",
        "AGENT_REGISTRY_AUTH",
        "AGENT_REGISTRY_HEARTBEAT_SECONDS",
        "BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED",
        "BROCCOLI_COMMS_REMOTE_PANE_INPUT_SEND_ENABLED",
        "BROCCOLI_COMMS_REMOTE_PANE_INPUT_RECEIVE_ENABLED",
        "BROCCOLI_COMMS_REMOTE_PANE_INPUT_REGISTRY_ENABLED",
    ]
    return [shell_env_assignment(key, env[key]) for key in keys if env.get(key)]


def managed_agent_launch_command(name: str, cwd: str, command: str) -> str:
    track_prefix = [*broccoli_comms_launcher_argv(), "track", "--name", name, "--cwd", cwd, "--"]
    return " ".join([
        *managed_track_env_assignments(),
        *(shlex.quote(part) for part in track_prefix),
        command,
    ])


def reconcile_agents(names: set[str] | None = None, *, autostart_only: bool = False) -> list[str]:
    cfg = load_config()
    agents = cfg.get("agents") or {}
    launched = []
    for name, spec in agents.items():
        if names is not None and name not in names:
            continue
        if autostart_only and not agent_autostart(spec):
            continue
        if window_exists(name):
            continue
        cwd = os.path.abspath(os.path.expanduser(spec.get("cwd") or str(Path.home())))
        if not os.path.isdir(cwd):
            raise SystemExit(f"configured cwd for agent {name!r} does not exist: {cwd}")
        command = spec.get("command") or "bash"
        launch = managed_agent_launch_command(name, cwd, command)
        result = tmux("new-window", "-d", "-P", "-F", "#{window_id}", "-t", SESSION, "-n", name, "-c", cwd, launch)
        window_id = result.stdout.strip()
        if window_id:
            tmux("set-option", "-w", "-t", window_id, MANAGED_AGENT_OPTION, name)
        launched.append(name)
    return launched


def start(_args: argparse.Namespace) -> None:
    ensure_tracker()
    ensure_tmux()
    reconcile_agents(autostart_only=True)
    print(f"{APP} runtime started")
    print(f"tracker socket: {paths()['tracker_socket']}")
    print(f"tmux mode:      {tmux_mode()}")
    print(f"tmux socket:    {tmux_socket_label() or 'default'}")


def ui_window() -> dict[str, str] | None:
    if not tmux_up():
        return None
    fmt = f"#{{window_id}}\t#{{window_name}}\t#{{pane_id}}\t#{{{UI_WINDOW_OPTION}}}"
    result = tmux("list-windows", "-t", SESSION, "-F", fmt, check=False)
    if result.returncode != 0:
        return None
    named_candidates = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        window_id, window_name, pane_id, ui_marker = parts
        window = {"window_id": window_id, "window_name": window_name, "pane_id": pane_id}
        if ui_marker == "1":
            return window
        if window_name == UI_WINDOW_NAME:
            named_candidates.append(window)
    for window in named_candidates:
        if ui_window_registered(window):
            return window
    return None


def ui_window_registered(window: dict[str, str] | None) -> bool:
    if not window:
        return False
    info = tracker_agents().get(UI_AGENT_NAME) or {}
    if info.get("tmux_pane") != window.get("pane_id"):
        return False
    if use_private_tmux():
        return info.get("tmux_socket") == str(paths()["tmux_socket"])
    return True


def ensure_ui_mailbox() -> dict:
    result = tracker_rpc("ensure_mailbox", {"agent_name": UI_AGENT_NAME, "preserve_pane": True})
    return result if isinstance(result, dict) else {}


def ui_launch_command() -> str:
    p = paths()
    mailbox = ensure_ui_mailbox()
    ui_agent_id = mailbox.get("agent_id") or mailbox.get("uuid")
    assignments = []
    if ui_agent_id:
        assignments.append(f"AGENT_ID={shlex.quote(str(ui_agent_id))}")
    return " ".join([
        *assignments,
        f"SUGGESTED_AGENT_NAME={shlex.quote(UI_AGENT_NAME)}",
        f"AGENT_TRACKER_SOCKET={shlex.quote(str(p['tracker_socket']))}",
        f"BROCCOLI_COMMS_APP_RUNTIME=1",
        f"BROCCOLI_COMMS_RUNTIME_DIR={shlex.quote(str(p['runtime']))}",
        *tmux_env_assignments_for_pane(),
        shlex.quote(wrapper_path()),
        shlex.quote(tui_path()),
        "--no-notify-with-send-keys",
    ])


def ensure_ui_window() -> dict[str, str]:
    window = ui_window()
    if window and ui_window_registered(window):
        return window
    if window:
        tmux("kill-window", "-t", window["window_id"], check=False)
        unregister_agent_pane(window.get("pane_id"))
    result = tmux(
        "new-window",
        "-d",
        "-P",
        "-F",
        "#{window_id}\t#{pane_id}",
        "-t",
        SESSION,
        "-n",
        UI_WINDOW_NAME,
        "-c",
        str(Path.cwd()),
        ui_launch_command(),
    )
    window_id, pane_id = result.stdout.strip().split("\t", 1)
    if window_id:
        tmux("set-option", "-w", "-t", window_id, UI_WINDOW_OPTION, "1", check=False)
    return {"window_id": window_id, "window_name": UI_WINDOW_NAME, "pane_id": pane_id}


def ui_env_for_current_shell() -> dict[str, str]:
    env = base_env()
    for key in ("TMUX", "TMUX_PANE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def ui(_args: argparse.Namespace) -> None:
    if not can_connect(paths()["tracker_socket"]):
        raise SystemExit(f"broccoli-comms ui requires a running tracker at {paths()['tracker_socket']}. Run `broccoli-comms start` first.")
    tui = tui_path()
    os.execvpe(tui, [tui], ui_env_for_current_shell())


def attach(_args: argparse.Namespace) -> None:
    ensure_tracker()
    ensure_tmux()
    exec_tmux_interactive(SESSION)


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
            "tmux_mode": tmux_mode(),
            "tmux_socket": tmux_socket_label(),
        },
        "agents": {
            name: {
                "name": name,
                "configured": {
                    "cwd": spec.get("cwd"),
                    "command": spec.get("command"),
                    "autostart": agent_autostart(spec),
                },
                # Backward-compatible direct fields for simple JSON consumers.
                "cwd": spec.get("cwd"),
                "command": spec.get("command"),
                "autostart": agent_autostart(spec),
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
            "mode": tmux_mode(),
            "socket": tmux_socket_label(),
            "up": session_up,
            "session": SESSION,
        },
        "config": {
            "path": str(p["config_json"]),
        },
        "agents": {
            "configured_count": len(configured_agents),
            "autostart_count": sum(1 for spec in configured_agents.values() if agent_autostart(spec)),
            "managed_running_count": len(managed),
            "managed_windows": managed,
        },
        # Backward-compatible aliases used by existing smoke checks.
        "tracker_socket": str(p["tracker_socket"]),
        "tracker_up": tracker_up,
        "tmux_socket": tmux_socket_label(),
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
    existing = agents.get(args.name)
    if args.name in agents and not args.force:
        raise SystemExit(f"agent {args.name!r} already exists; use --force to update")
    autostart = bool(args.autostart) if args.autostart is not None else bool((existing or {}).get("autostart", False))
    agents[args.name] = {"cwd": cwd, "command": command, "autostart": autostart}
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
    if in_tmux_client() and not use_private_tmux():
        subprocess.run(["tmux", "switch-client", "-t", window_id], env=os.environ.copy(), check=False, text=True, capture_output=True)
    else:
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
    exec_tmux_interactive(window["window_id"])


def _derive_track_name(command: list[str], cwd: str | None = None) -> str:
    basename = Path(command[0]).name if command else ""
    candidate = re.sub(r"[^A-Za-z0-9_.-]", "-", basename).strip("-._")
    if candidate:
        return candidate
    if cwd:
        cwd_name = re.sub(r"[^A-Za-z0-9_.-]", "-", Path(cwd).resolve().name).strip("-._")
        if cwd_name:
            return cwd_name
    return "agent"


def _resolve_command(command: str, env: dict[str, str]) -> str | None:
    if not command:
        return None
    if os.path.isabs(command) or os.sep in command:
        path = os.path.abspath(os.path.expanduser(command))
        return path if os.path.exists(path) else None
    return shutil.which(command, path=env.get("PATH"))


def unwrap_track_wrapper_command(command: list[str], env: dict[str, str]) -> list[str]:
    """Avoid nested Broccoli tracking for commands already wrapped with `broccoli-comms track`.

    Some installed agent commands, such as the local `pi` launcher, are shell
    wrappers that already exec `broccoli-comms track --name ... -- REAL_CMD`.
    Running `broccoli-comms track -- pi` would otherwise stack two wrappers in
    one pane and can create name collisions such as `pi` and `pi-1`.
    """
    if not command:
        return command
    resolved = _resolve_command(command[0], env)
    if not resolved or not os.path.isfile(resolved):
        return command
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.read(8192).splitlines()
    except (OSError, UnicodeDecodeError):
        return command
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("exec ") or "broccoli-comms" not in stripped or " track " not in stripped:
            continue
        try:
            parts = shlex.split(stripped)
        except ValueError:
            continue
        track_index = None
        for idx in range(1, len(parts)):
            if parts[idx] == "track" and Path(parts[idx - 1]).name == "broccoli-comms":
                track_index = idx
                break
        if track_index is None:
            continue
        try:
            separator_index = parts.index("--", track_index + 1)
        except ValueError:
            continue
        inner = parts[separator_index + 1:]
        if not inner:
            continue
        inner = [part for part in inner if part not in {"$@", "${@}", "$*", "${*}"}]
        if not inner or inner[0].startswith("$"):
            continue
        return [*inner, *command[1:]]
    return command


def track(args: argparse.Namespace) -> None:
    command = list(getattr(args, "command", None) or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("track requires a command after --")

    if os.environ.get("BROCCOLI_COMMS_TRACK_ACTIVE") == "1" or os.environ.get("AGENT_WRAPPER_DEPTH", "0") != "0":
        if args.cwd:
            cwd = os.path.abspath(os.path.expanduser(args.cwd))
            if not os.path.isdir(cwd):
                raise SystemExit(f"track cwd does not exist or is not a directory: {cwd}")
            os.chdir(cwd)
        os.execvpe(command[0], command, os.environ.copy())

    if not os.environ.get("TMUX") or not os.environ.get("TMUX_PANE"):
        raise SystemExit("broccoli-comms track must be run from within a tmux pane so the agent can be registered. Start or attach to tmux, then run the command again.")

    original_command = list(command)
    track_env = base_env()
    command = unwrap_track_wrapper_command(command, track_env)

    cwd = None
    if args.cwd:
        cwd = os.path.abspath(os.path.expanduser(args.cwd))
        if not os.path.isdir(cwd):
            raise SystemExit(f"track cwd does not exist or is not a directory: {cwd}")

    name = args.name or _derive_track_name(original_command, cwd)
    try:
        validate_agent_name(name)
    except ValueError as e:
        raise SystemExit(str(e))

    wrapper = wrapper_path()
    if not os.path.exists(wrapper) or not os.access(wrapper, os.X_OK):
        raise SystemExit(f"agent-wrapper not found or not executable: {wrapper}")

    ensure_tracker()
    env = track_env
    if os.environ.get("TMUX"):
        env.pop("AGENT_TRACKER_TMUX_SOCKET", None)
        env.pop("BROCCOLI_COMMS_TMUX_SOCKET", None)
    for key in ("TMUX", "TMUX_PANE"):
        if key in os.environ:
            env[key] = os.environ[key]
    env["SUGGESTED_AGENT_NAME"] = name
    if cwd:
        os.chdir(cwd)
    os.execvpe(wrapper, [wrapper, *command], env)


def stop(_args: argparse.Namespace) -> None:
    p = paths()
    kill_broccoli_tmux_windows()
    for _ in range(50):
        if tmux("has-session", "-t", SESSION, check=False).returncode != 0 or not has_broccoli_tmux_windows():
            break
        time.sleep(0.1)
    if use_private_tmux() and p["tmux_socket"].exists() and tmux("list-sessions", check=False).returncode != 0:
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


def _resolve_executable(command: str) -> str | None:
    if not command:
        return None
    if os.path.isabs(command) or os.sep in command:
        return command if os.path.exists(command) and os.access(command, os.X_OK) else None
    return shutil.which(command, path=base_env().get("PATH"))


def _command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, check=False, text=True, capture_output=True, timeout=3, env=base_env())
    except Exception:
        return None
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else None


def _doctor_check(checks: list[dict], name: str, status: str, message: str, **extra) -> None:
    checks.append({"name": name, "status": status, "message": message, **{k: v for k, v in extra.items() if v is not None}})


def _check_writable_dir(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path, delete=True) as f:
            f.write("ok")
        return True, "writable"
    except Exception as e:
        return False, str(e)


SHELL_BUILTINS = {
    "alias", "bg", "cd", "command", "echo", "eval", "exec", "exit", "export", "fg", "hash", "jobs", "pwd", "read", "set", "shift", "test", "trap", "type", "ulimit", "umask", "unalias", "unset", "wait",
}
SHELL_COMPLEX_TOKENS = ("|", "&", ";", "<", ">", "(", ")", "$", "`", "\\", "\n")


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


def remote_pane_input_doctor_checks() -> list[dict]:
    checks = []
    send_enabled = _env_enabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED") or _env_enabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_SEND_ENABLED") or _env_enabled("AGENT_TRACKER_REMOTE_PANE_INPUT_SEND_ENABLED")
    receive_enabled = _env_enabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED") or _env_enabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_RECEIVE_ENABLED") or _env_enabled("AGENT_TRACKER_REMOTE_PANE_INPUT_RECEIVE_ENABLED")
    registry_enabled = _env_enabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_REGISTRY_ENABLED") or _env_enabled("AGENT_REGISTRY_REMOTE_PANE_INPUT_ENABLED")
    any_enabled = send_enabled or receive_enabled or registry_enabled
    if not any_enabled:
        _doctor_check(checks, "remote pane input", "ok", "remote direct pane input is disabled by default")
        return checks

    enabled_roles = ",".join(role for role, enabled in (("send", send_enabled), ("receive", receive_enabled), ("registry", registry_enabled)) if enabled)
    _doctor_check(checks, "remote pane input", "warning", "remote direct pane input is enabled; this bypasses inboxes and controls panes directly", enabled_roles=enabled_roles)

    registry_auth_disabled = os.environ.get("AGENT_REGISTRY_AUTH", "true").lower() in {"0", "false", "no"}
    registry_token = os.environ.get("AGENT_REGISTRY_TOKEN")
    if registry_auth_disabled:
        _doctor_check(checks, "remote pane input auth", "warning", "remote direct pane input is enabled while registry auth is disabled")
    elif not registry_token:
        _doctor_check(checks, "remote pane input auth", "warning", "remote direct pane input is enabled but AGENT_REGISTRY_TOKEN is not set in this environment")
    else:
        _doctor_check(checks, "remote pane input auth", "ok", "registry token is present for remote direct pane input")
    return checks


def configured_agent_command_checks() -> list[dict]:
    checks = []
    cfg = load_config()
    for name, spec in sorted((cfg.get("agents") or {}).items()):
        command = str(spec.get("command") or "").strip()
        check_name = f"agent command:{name}"
        if not command:
            _doctor_check(checks, check_name, "error", "configured command is empty")
            continue
        if any(token in command for token in SHELL_COMPLEX_TOKENS):
            _doctor_check(checks, check_name, "warning", "command is shell-complex; skipping executable lookup", command=command)
            continue
        try:
            parts = shlex.split(command)
        except ValueError as e:
            _doctor_check(checks, check_name, "warning", f"could not parse command: {e}", command=command)
            continue
        while parts and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", parts[0]):
            parts = parts[1:]
        executable = parts[0] if parts else ""
        if not executable:
            _doctor_check(checks, check_name, "warning", "command has no executable after env assignments", command=command)
        elif executable in SHELL_BUILTINS:
            _doctor_check(checks, check_name, "warning", "command starts with a shell builtin; skipping executable lookup", command=command, executable=executable)
        else:
            resolved = _resolve_executable(executable)
            if resolved:
                _doctor_check(checks, check_name, "ok", "configured command executable found", command=command, executable=executable, path=resolved)
            else:
                _doctor_check(checks, check_name, "error", "configured command executable not found on PATH", command=command, executable=executable)
    if not checks:
        _doctor_check(checks, "agent commands", "ok", "no configured agents")
    return checks


def doctor_payload() -> dict:
    p = paths()
    checks: list[dict] = []

    tmux_path = _resolve_executable("tmux")
    _doctor_check(checks, "tmux", "ok" if tmux_path else "error", "tmux executable found" if tmux_path else "tmux executable not found; Nix packages include tmux, manual installs must provide system tmux", path=tmux_path, version=_command_version([tmux_path, "-V"]) if tmux_path else None)

    python_path = sys.executable if os.path.exists(sys.executable) else _resolve_executable("python3")
    _doctor_check(checks, "python", "ok" if python_path else "error", "Python executable found" if python_path else "python3 executable not found", path=python_path, version=_command_version([python_path, "--version"]) if python_path else None)

    tracker = tracker_script()
    _doctor_check(checks, "tracker script", "ok" if os.path.exists(tracker) else "error", "tracker script found" if os.path.exists(tracker) else "tracker script missing", path=tracker)

    wrapper = wrapper_path()
    wrapper_ok = os.path.exists(wrapper) and os.access(wrapper, os.X_OK)
    _doctor_check(checks, "agent-wrapper", "ok" if wrapper_ok else "error", "agent-wrapper executable found" if wrapper_ok else "agent-wrapper missing or not executable", path=wrapper)

    tui = tui_path()
    tui_resolved = _resolve_executable(tui)
    _doctor_check(checks, "agent-communicator", "ok" if tui_resolved else "error", "agent-communicator executable found" if tui_resolved else "agent-communicator executable not found", path=tui_resolved or tui)

    for label, path in (("runtime dir", p["runtime"]), ("cache dir", p["cache"]), ("config dir", p["config"])):
        ok, message = _check_writable_dir(path)
        _doctor_check(checks, label, "ok" if ok else "error", message, path=str(path))

    checks.extend(configured_agent_command_checks())
    checks.extend(remote_pane_input_doctor_checks())

    tracker_socket_exists = p["tracker_socket"].exists()
    tracker_reachable = can_connect(p["tracker_socket"])
    if tracker_reachable:
        _doctor_check(checks, "tracker socket", "ok", "private tracker socket is reachable", path=str(p["tracker_socket"]))
    elif tracker_socket_exists:
        _doctor_check(checks, "tracker socket", "warning", "tracker socket exists but is not reachable", path=str(p["tracker_socket"]))
    else:
        _doctor_check(checks, "tracker socket", "ok", "runtime is not running; tracker socket not present", path=str(p["tracker_socket"]))

    tmux_reachable = bool(tmux_path) and tmux_up()
    if use_private_tmux():
        tmux_socket_exists = p["tmux_socket"].exists()
        if tmux_reachable:
            _doctor_check(checks, "tmux session", "ok", "private tmux session is reachable", mode=tmux_mode(), path=str(p["tmux_socket"]), session=SESSION)
        elif tmux_socket_exists:
            _doctor_check(checks, "tmux session", "warning", "tmux socket exists but private session is not reachable", mode=tmux_mode(), path=str(p["tmux_socket"]), session=SESSION)
        else:
            _doctor_check(checks, "tmux session", "ok", "runtime is not running; private tmux socket not present", mode=tmux_mode(), path=str(p["tmux_socket"]), session=SESSION)
    else:
        if tmux_reachable:
            _doctor_check(checks, "tmux session", "ok", "default tmux server has Broccoli Comms session", mode=tmux_mode(), session=SESSION)
        else:
            _doctor_check(checks, "tmux session", "ok", "runtime is not running; default tmux session not present", mode=tmux_mode(), session=SESSION)

    return {
        "app": APP,
        "version": VERSION,
        "ok": not any(check["status"] == "error" for check in checks),
        "paths": {"runtime_dir": str(p["runtime"]), "cache_dir": str(p["cache"]), "config_dir": str(p["config"])},
        "runtime": {"tracker_up": tracker_reachable, "tmux_up": tmux_reachable, "tmux_session": SESSION, "tmux_mode": tmux_mode(), "tmux_socket": tmux_socket_label()},
        "checks": checks,
    }


def _default_registries_config() -> dict:
    return {"version": 1, "registries": []}


def _normalize_registry_urls_config(data: object) -> dict:
    if data is None:
        return _default_registries_config()
    if not isinstance(data, dict):
        raise ValueError("registries config must be a JSON object")
    version = data.get("version", 1)
    if version != 1:
        raise ValueError(f"unsupported registries config version: {version}")
    registries = data.get("registries", [])
    if not isinstance(registries, list):
        raise ValueError("registries config field 'registries' must be a list")
    normalized = []
    for entry in registries:
        if not isinstance(entry, dict):
            raise ValueError("registry entries must be objects")
        name = entry.get("name")
        url = entry.get("url")
        if not isinstance(name, str) or not AGENT_NAME_RE.match(name):
            raise ValueError(f"invalid registry name in config: {name!r}")
        if not isinstance(url, str):
            raise ValueError(f"registry {name} has invalid url")
        item = {"name": name, "url": _normalize_registry_url(url), "enabled": bool(entry.get("enabled", True))}
        if "auth" in entry:
            item["auth"] = bool(entry.get("auth"))
        token_file = entry.get("token-file")
        if token_file:
            if not isinstance(token_file, str):
                raise ValueError(f"registry {name} has invalid token-file")
            item["token-file"] = str(Path(token_file).expanduser())
        normalized.append(item)
    return {"version": 1, "registries": normalized}


def load_registry_urls_config() -> dict:
    path = paths()["registries_json"]
    if not path.exists():
        return _default_registries_config()
    try:
        return _normalize_registry_urls_config(json.loads(path.read_text()))
    except json.JSONDecodeError as e:
        raise SystemExit(f"failed to parse {path}: {e}")
    except ValueError as e:
        raise SystemExit(f"invalid {path}: {e}")


def save_registry_urls_config(config: dict) -> None:
    normalized = _normalize_registry_urls_config(config)
    path = paths()["registries_json"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(normalized, f, indent=2, sort_keys=True)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _normalize_registry_url(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("registry URL must be a string")
    url = url.strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("registry URL must start with http:// or https:// and include a host")
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def _registry_entry_for_tracker(entry: dict) -> dict[str, str]:
    result = {"name": entry["name"], "url": entry["url"]}
    token_file = entry.get("token-file")
    if token_file:
        result["token-file"] = token_file
    return result


def configured_registries_for_tracker() -> list[dict[str, str]]:
    config = load_registry_urls_config()
    return [_registry_entry_for_tracker(entry) for entry in config.get("registries", []) if entry.get("enabled", True)]


def apply_configured_registries(env: dict[str, str]) -> dict[str, str]:
    if "AGENT_REGISTRIES_JSON" in env:
        return env
    if os.environ.get("BROCCOLI_COMMS_DISABLE_CONFIG_REGISTRIES", "").lower() in {"1", "true", "yes"}:
        return env
    registries = configured_registries_for_tracker()
    if registries:
        env["AGENT_REGISTRIES_JSON"] = json.dumps(registries, separators=(",", ":"))
    return env


def _redact_registry_entry(entry: dict) -> dict:
    redacted = {k: v for k, v in entry.items() if k != "token"}
    if "token" in entry:
        redacted["token"] = "<redacted>"
    return redacted


def _redacted_registry_urls_config(config: dict) -> dict:
    normalized = _normalize_registry_urls_config(config)
    return {"version": 1, "registries": [_redact_registry_entry(entry) for entry in normalized.get("registries", [])]}


def registry_add(args: argparse.Namespace) -> None:
    if not AGENT_NAME_RE.match(args.name):
        raise SystemExit("registry add: NAME may contain only letters, digits, underscore, dot, or dash")
    if args.auth and not args.token_file:
        raise SystemExit("registry add: --auth requires --token-file")
    if args.noauth and args.token_file:
        raise SystemExit("registry add: --noauth cannot be combined with --token-file")
    url = _normalize_registry_url(args.url)
    token_file = str(Path(args.token_file).expanduser()) if args.token_file else None
    if token_file and not Path(token_file).exists():
        raise SystemExit(f"registry add: token file does not exist: {token_file}")
    config = load_registry_urls_config()
    registries = config.get("registries", [])
    existing = next((i for i, entry in enumerate(registries) if entry.get("name") == args.name), None)
    if existing is not None and not args.replace:
        raise SystemExit(f"registry add: registry {args.name!r} already exists; use --replace")
    entry = {"name": args.name, "url": url, "enabled": True}
    if args.noauth:
        entry["auth"] = False
    elif args.auth or token_file:
        entry["auth"] = True
    if token_file:
        entry["token-file"] = token_file
    if existing is None:
        registries.append(entry)
    else:
        registries[existing] = entry
    config["registries"] = registries
    save_registry_urls_config(config)
    print(f"registry {args.name} configured. Restart Broccoli Comms for changes to affect the running tracker.")


def registry_list(args: argparse.Namespace) -> None:
    config = load_registry_urls_config()
    redacted = _redacted_registry_urls_config(config)
    if args.json:
        print(json.dumps(redacted, indent=2, sort_keys=True))
        return
    registries = redacted.get("registries", [])
    if not registries:
        print("no registries configured")
        return
    rows = [("NAME", "URL", "AUTH", "ENABLED")]
    for entry in registries:
        if entry.get("token-file"):
            auth = "token-file"
        elif entry.get("auth") is False:
            auth = "noauth"
        else:
            auth = "none"
        rows.append((entry["name"], entry["url"], auth, "yes" if entry.get("enabled", True) else "no"))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for row in rows:
        print("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)))


def registry_remove(args: argparse.Namespace) -> None:
    config = load_registry_urls_config()
    registries = config.get("registries", [])
    kept = [entry for entry in registries if entry.get("name") != args.name]
    if len(kept) == len(registries) and not args.missing_ok:
        raise SystemExit(f"registry remove: registry {args.name!r} not found")
    config["registries"] = kept
    save_registry_urls_config(config)
    print(f"registry {args.name} removed. Restart Broccoli Comms for changes to affect the running tracker.")


def _set_registry_enabled(args: argparse.Namespace, enabled: bool) -> None:
    config = load_registry_urls_config()
    for entry in config.get("registries", []):
        if entry.get("name") == args.name:
            entry["enabled"] = enabled
            save_registry_urls_config(config)
            state = "enabled" if enabled else "disabled"
            print(f"registry {args.name} {state}. Restart Broccoli Comms for changes to affect the running tracker.")
            return
    raise SystemExit(f"registry {args.name!r} not found")


def registry_enable(args: argparse.Namespace) -> None:
    _set_registry_enabled(args, True)


def registry_disable(args: argparse.Namespace) -> None:
    _set_registry_enabled(args, False)


def registry_env(args: argparse.Namespace) -> None:
    registries = configured_registries_for_tracker()
    value = json.dumps(registries, separators=(",", ":"))
    if args.json:
        print(json.dumps({"AGENT_REGISTRIES_JSON": value, "registries": registries}, indent=2, sort_keys=True))
    else:
        print(f"AGENT_REGISTRIES_JSON={shlex.quote(value)}")


def _is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _read_token_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return Path(path).expanduser().read_text().strip()
    except OSError as e:
        raise SystemExit(f"failed to read token file {path}: {e}")


def _registry_auth_enabled(args: argparse.Namespace) -> bool:
    if args.auth and args.noauth:
        raise SystemExit("registry start: choose only one of --auth or --noauth")
    if args.auth:
        return True
    if args.noauth:
        if not _is_loopback_host(args.host):
            raise SystemExit("registry start: refusing unauthenticated non-loopback bind; use --auth --token-file for public/LAN hosts")
        return False
    if _is_loopback_host(args.host):
        return False
    raise SystemExit("registry start: non-loopback binds require explicit --auth (recommended) or --noauth is refused for safety")


def _registry_state_path(args: argparse.Namespace) -> Path:
    if getattr(args, "state_path", None):
        return Path(args.state_path).expanduser()
    return paths()["registry_state"]


def _registry_url(host: str, port: int) -> str:
    url_host = "127.0.0.1" if host == "0.0.0.0" else host
    if ":" in url_host and not url_host.startswith("["):
        url_host = f"[{url_host}]"
    return f"http://{url_host}:{port}"


def _registry_config_from_args(args: argparse.Namespace, auth_enabled: bool, state_path: Path) -> dict:
    return {
        "name": args.name,
        "host": args.host,
        "port": int(args.port),
        "auth": auth_enabled,
        "token_file": str(Path(args.token_file).expanduser()) if getattr(args, "token_file", None) else None,
        "state_path": str(state_path),
        "url": _registry_url(args.host, int(args.port)),
    }


def _load_registry_config() -> dict:
    path = paths()["registry_config"]
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {
        "name": "local",
        "host": "127.0.0.1",
        "port": 8080,
        "auth": False,
        "token_file": None,
        "state_path": str(paths()["registry_state"]),
        "url": "http://127.0.0.1:8080",
    }


def _save_registry_config(config: dict) -> None:
    path = paths()["registry_config"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")


def _registry_env(args: argparse.Namespace, auth_enabled: bool, state_path: Path) -> dict[str, str]:
    token = getattr(args, "token", None) or _read_token_file(getattr(args, "token_file", None))
    if auth_enabled and not token:
        raise SystemExit("registry start: --auth requires --token-file or --token")
    env = base_env()
    env.update({
        "AGENT_REGISTRY_HOST": args.host,
        "AGENT_REGISTRY_PORT": str(args.port),
        "AGENT_REGISTRY_AUTH": "true" if auth_enabled else "false",
        "AGENT_REGISTRY_STATE_PATH": str(state_path),
        "TRACKER_STALE_SECONDS": str(args.stale_seconds),
        "TRACKER_GONE_SECONDS": str(args.gone_seconds),
    })
    if token:
        env["AGENT_REGISTRY_TOKEN"] = token
    return env


def _registry_auth_header(config: dict) -> dict[str, str]:
    if not config.get("auth"):
        return {}
    token = _read_token_file(config.get("token_file"))
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _registry_request(path: str, config: dict | None = None, timeout: float = 3.0) -> tuple[int | None, dict | None, str | None]:
    config = config or _load_registry_config()
    url = (config.get("url") or _registry_url(config.get("host", "127.0.0.1"), int(config.get("port", 8080)))).rstrip("/") + path
    req = urllib.request.Request(url, headers={"Accept": "application/json", **_registry_auth_header(config)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}, None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = None
        return e.code, body, None
    except Exception as e:
        return None, None, str(e)


def _wait_registry_ready(config: dict, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _, _ = _registry_request("/healthz", config, timeout=0.5)
        if status == 200:
            return True
        time.sleep(0.1)
    return False


def registry_start(args: argparse.Namespace) -> None:
    ensure_dirs()
    auth_enabled = _registry_auth_enabled(args)
    state_path = _registry_state_path(args)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    config = _registry_config_from_args(args, auth_enabled, state_path)
    env = _registry_env(args, auth_enabled, state_path)
    _save_registry_config(config)
    pid_file = paths()["registry_pid"]
    existing_pid = _read_pid(pid_file)
    if existing_pid and _pid_running(existing_pid):
        if not args.force:
            print(f"registry already running pid={existing_pid} url={config['url']}")
            return
        try:
            os.kill(existing_pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(50):
            if not _pid_running(existing_pid):
                break
            time.sleep(0.1)

    if args.foreground:
        pid_file.write_text(str(os.getpid()))
        os.execvpe(sys.executable, [sys.executable, registry_script()], env)

    log = open(paths()["registry_log"], "ab", buffering=0)
    proc = subprocess.Popen([sys.executable, registry_script()], env=env, stdout=log, stderr=log, start_new_session=True)
    pid_file.write_text(str(proc.pid))
    if not _wait_registry_ready(config):
        if proc.poll() is not None:
            raise SystemExit(f"agent-registry exited early; see {paths()['registry_log']}")
        raise SystemExit(f"agent-registry did not become healthy; see {paths()['registry_log']}")
    print(f"registry started name={config['name']} url={config['url']} pid={proc.pid} auth={'on' if auth_enabled else 'off'}")


def registry_stop(args: argparse.Namespace) -> None:
    pid_file = paths()["registry_pid"]
    pid = _read_pid(pid_file)
    if not pid:
        print("registry not running")
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pid_file.unlink(missing_ok=True)
        print("registry not running")
        return
    for _ in range(50):
        if not _pid_running(pid):
            break
        time.sleep(0.1)
    if _pid_running(pid) and args.force:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        for _ in range(20):
            if not _pid_running(pid):
                break
            time.sleep(0.1)
    pid_file.unlink(missing_ok=True)
    print("registry stopped")


def _registry_status_payload() -> dict:
    config = _load_registry_config()
    pid = _read_pid(paths()["registry_pid"])
    running = bool(pid and _pid_running(pid))
    health_status, health_body, health_error = _registry_request("/healthz", config)
    agents_status, agents_body, _ = _registry_request("/agents", config)
    return {
        "name": config.get("name"),
        "url": config.get("url"),
        "host": config.get("host"),
        "port": config.get("port"),
        "auth": bool(config.get("auth")),
        "pid": pid,
        "running": running,
        "state_path": config.get("state_path"),
        "log_path": str(paths()["registry_log"]),
        "health": {"status": health_status, "body": health_body, "error": health_error},
        "agent_count": len((agents_body or {}).get("agents") or []) if agents_status == 200 else None,
    }


def registry_status(args: argparse.Namespace) -> None:
    payload = _registry_status_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    health = payload["health"]
    health_text = "ok" if health.get("status") == 200 else (health.get("error") or f"http {health.get('status')}")
    print(f"registry {payload['name']} {payload['url']} pid={payload['pid']} running={payload['running']} auth={'on' if payload['auth'] else 'off'} health={health_text} agents={payload['agent_count']}")


def registry_health(_args: argparse.Namespace) -> None:
    status, body, error = _registry_request("/healthz")
    if status == 200:
        print(json.dumps(body or {"ok": True}, indent=2, sort_keys=True))
        return
    raise SystemExit(error or json.dumps(body or {"status": status}))


def registry_agents(args: argparse.Namespace) -> None:
    status, body, error = _registry_request("/agents")
    if status != 200:
        raise SystemExit(error or json.dumps(body or {"status": status}))
    agents = (body or {}).get("agents") or []
    if args.json:
        print(json.dumps(body, indent=2, sort_keys=True))
    else:
        for agent in agents:
            print(f"{agent.get('hostname', '?')}/{agent.get('name', '?')} {agent.get('status', 'unknown')} {agent.get('agent_id', '')}")
        if not agents:
            print("no agents")


def registry_trackers(args: argparse.Namespace) -> None:
    status, body, error = _registry_request("/trackers")
    if status != 200:
        raise SystemExit(error or json.dumps(body or {"status": status}))
    if args.json:
        print(json.dumps(body, indent=2, sort_keys=True))
    else:
        trackers = (body or {}).get("trackers") or []
        for tracker in trackers:
            print(f"{tracker.get('hostname', '?')} {tracker.get('status', 'unknown')} {tracker.get('tracker_id', '')}")
        if not trackers:
            print("no trackers")


def agent_tracker(args: argparse.Namespace) -> None:
    """Run the in-repo agent-tracker-ctl against Broccoli Comms private sockets."""
    ensure_tracker()
    ensure_tmux()
    ctl = tracker_ctl_script()
    tracker_args = list(getattr(args, "tracker_args", None) or ["--help"])
<<<<<<< HEAD
    env = base_env()
    for key in ("AGENT_ID", "AGENT_NAME", "AGENT_UUID"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    os.execvpe(sys.executable, [sys.executable, ctl, *tracker_args], env)
=======
    os.execvpe(sys.executable, [sys.executable, ctl, *tracker_args], base_env(preserve_agent_identity=True))
>>>>>>> e056ce4 (Fix send-message sender attribution)


def doctor(args: argparse.Namespace) -> None:
    payload = doctor_payload()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in payload["checks"]:
            marker = {"ok": "OK", "warning": "WARN", "error": "FAIL"}.get(check["status"], check["status"].upper())
            detail = check.get("path") or check.get("command") or ""
            suffix = f" ({detail})" if detail else ""
            version = f" [{check['version']}]" if check.get("version") else ""
            print(f"{marker}: {check['name']}: {check['message']}{suffix}{version}")
        if not payload["ok"]:
            print("doctor failed: fix FAIL checks. Nix packages include runtime dependencies such as tmux; manual/non-Nix installs must provide required executables on PATH.", file=sys.stderr)
    if not payload["ok"]:
        raise SystemExit(1)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "agent-tracker":
        agent_tracker(argparse.Namespace(tracker_args=sys.argv[2:]))
        return

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
    doctor_parser = sub.add_parser("doctor", help="Check new-machine/runtime readiness")
    doctor_parser.add_argument("--json", action="store_true", help="Emit JSON doctor results")
    doctor_parser.set_defaults(func=doctor)

    track_parser = sub.add_parser("track", help="Run a command through agent-wrapper so it appears in Agent Communicator")
    track_parser.add_argument("--name", help="Suggested registered agent name; defaults to command basename")
    track_parser.add_argument("--cwd", help="Working directory for the command")
    track_parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --")
    track_parser.set_defaults(func=track)

    agent_tracker_parser = sub.add_parser("agent-tracker", help="Run agent-tracker-ctl against the Broccoli Comms private runtime", add_help=False)
    agent_tracker_parser.add_argument("tracker_args", nargs=argparse.REMAINDER)
    agent_tracker_parser.set_defaults(func=agent_tracker)

    registry = sub.add_parser("registry", help="Manage a Broccoli Comms agent-registry process")
    registry_sub = registry.add_subparsers(dest="registry_command", required=True)
    registry_start_parser = registry_sub.add_parser("start", help="Start a managed local agent-registry")
    registry_start_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    registry_start_parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    registry_start_parser.add_argument("--name", default="local", help="Logical registry name")
    auth_group = registry_start_parser.add_mutually_exclusive_group()
    auth_group.add_argument("--auth", action="store_true", help="Require bearer auth")
    auth_group.add_argument("--noauth", action="store_true", help="Disable auth for loopback local/dev use")
    registry_start_parser.add_argument("--token", help="Bearer token value (prefer --token-file)")
    registry_start_parser.add_argument("--token-file", help="File containing bearer token")
    registry_start_parser.add_argument("--state-path", help="Registry state path")
    registry_start_parser.add_argument("--stale-seconds", type=int, default=60, help="Tracker stale threshold")
    registry_start_parser.add_argument("--gone-seconds", type=int, default=180, help="Tracker gone threshold")
    registry_start_parser.add_argument("--foreground", action="store_true", help="Run in foreground")
    registry_start_parser.add_argument("--force", action="store_true", help="Replace stale/running pid file")
    registry_start_parser.set_defaults(func=registry_start)
    registry_stop_parser = registry_sub.add_parser("stop", help="Stop the managed registry")
    registry_stop_parser.add_argument("--force", action="store_true", help="SIGKILL if graceful stop fails")
    registry_stop_parser.set_defaults(func=registry_stop)
    registry_status_parser = registry_sub.add_parser("status", help="Show managed registry status")
    registry_status_parser.add_argument("--json", action="store_true", help="Emit JSON")
    registry_status_parser.set_defaults(func=registry_status)
    registry_sub.add_parser("health", help="GET /healthz").set_defaults(func=registry_health)
    registry_agents_parser = registry_sub.add_parser("agents", help="GET /agents")
    registry_agents_parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    registry_agents_parser.set_defaults(func=registry_agents)
    registry_trackers_parser = registry_sub.add_parser("trackers", help="GET /trackers")
    registry_trackers_parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    registry_trackers_parser.set_defaults(func=registry_trackers)
    registry_add_parser = registry_sub.add_parser("add", help="Configure a registry URL for the private tracker")
    registry_add_parser.add_argument("--name", required=True, help="Registry name")
    registry_add_parser.add_argument("--url", required=True, help="Registry URL")
    add_auth_group = registry_add_parser.add_mutually_exclusive_group()
    add_auth_group.add_argument("--auth", action="store_true", help="Require token-file auth for this URL")
    add_auth_group.add_argument("--noauth", action="store_true", help="Save without auth token metadata")
    registry_add_parser.add_argument("--token-file", help="Token file path; token contents are not stored")
    registry_add_parser.add_argument("--replace", action="store_true", help="Replace existing registry with same name")
    registry_add_parser.set_defaults(func=registry_add)
    registry_list_parser = registry_sub.add_parser("list", help="List configured tracker registry URLs")
    registry_list_parser.add_argument("--json", action="store_true", help="Emit JSON")
    registry_list_parser.set_defaults(func=registry_list)
    registry_remove_parser = registry_sub.add_parser("remove", help="Remove a configured tracker registry URL")
    registry_remove_parser.add_argument("name")
    registry_remove_parser.add_argument("--missing-ok", action="store_true", help="Do not fail if missing")
    registry_remove_parser.set_defaults(func=registry_remove)
    registry_enable_parser = registry_sub.add_parser("enable", help="Enable a configured tracker registry URL")
    registry_enable_parser.add_argument("name")
    registry_enable_parser.set_defaults(func=registry_enable)
    registry_disable_parser = registry_sub.add_parser("disable", help="Disable a configured tracker registry URL")
    registry_disable_parser.add_argument("name")
    registry_disable_parser.set_defaults(func=registry_disable)
    registry_env_parser = registry_sub.add_parser("env", help="Show AGENT_REGISTRIES_JSON generated from saved registry URLs")
    registry_env_parser.add_argument("--json", action="store_true", help="Emit JSON")
    registry_env_parser.set_defaults(func=registry_env)

    agent = sub.add_parser("agent", help="Manage configured agents")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_list_parser = agent_sub.add_parser("list", help="List configured agents")
    agent_list_parser.add_argument("--json", action="store_true", help="Include config/runtime metadata in JSON output")
    agent_list_parser.set_defaults(func=agent_list)
    agent_add_parser = agent_sub.add_parser("add", help="Add or update a configured agent")
    agent_add_parser.add_argument("name", help="Agent/window name")
    agent_add_parser.add_argument("--cwd", required=True, help="Working directory")
    agent_add_parser.add_argument("--command", required=True, help="Command to run through broccoli-comms track")
    autostart_group = agent_add_parser.add_mutually_exclusive_group()
    autostart_group.add_argument("--autostart", dest="autostart", action="store_true", default=None, help="Launch this agent during broccoli-comms start/ui")
    autostart_group.add_argument("--no-autostart", dest="autostart", action="store_false", help="Keep this agent configured but do not launch it during start/ui")
    agent_add_parser.add_argument("--force", action="store_true", help="Update an existing agent")
    agent_add_parser.set_defaults(func=agent_add)
    agent_remove_parser = agent_sub.add_parser("remove", help="Remove a configured agent and stop its managed window if running")
    agent_remove_parser.add_argument("name", help="Agent/window name")
    agent_remove_parser.set_defaults(func=agent_remove)
    agent_restart_parser = agent_sub.add_parser("restart", help="Restart a configured agent window")
    agent_restart_parser.add_argument("name", help="Agent/window name")
    agent_restart_parser.set_defaults(func=agent_restart)
    agent_focus_parser = agent_sub.add_parser("focus", help="Focus a running managed agent window in the Broccoli tmux session")
    agent_focus_parser.add_argument("name", help="Agent/window name")
    agent_focus_parser.set_defaults(func=agent_focus)
    agent_attach_parser = agent_sub.add_parser("attach", help="Attach/switch to a running managed agent window in the Broccoli tmux session")
    agent_attach_parser.add_argument("name", help="Agent/window name")
    agent_attach_parser.set_defaults(func=agent_attach)
    args = parser.parse_args()
    if not hasattr(args, "func"):
        args.func = ui
    args.func(args)


if __name__ == "__main__":
    main()
