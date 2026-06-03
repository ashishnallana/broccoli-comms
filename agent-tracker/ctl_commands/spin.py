import argparse
import os
from pathlib import Path
import shlex
import shutil
import sys

from .common import call_rpc, spin_session_name


def register(subparsers):
    parser = subparsers.add_parser("spin", help="Spin a new agent in a tmux session for a directory")
    parser.add_argument("--no-fallback", "-n", action="store_true", help="Disable automatic bash shell wrapper and zsh fallback")
    parser.add_argument("directory", help="Working directory; leaf name becomes the tmux session/agent base name")
    parser.add_argument("agent_command", help="Agent command to run")
    parser.add_argument("agent_args", nargs=argparse.REMAINDER, help="Arguments for the agent command")
    parser.set_defaults(handler=handle)


def resolve_agent_wrapper_path() -> str:
    """Find the standalone agent-wrapper from env, PATH, or source checkout."""
    env_val = os.environ.get("BROCCOLI_COMMS_AGENT_WRAPPER")
    if env_val:
        return env_val

    on_path = shutil.which("agent-wrapper")
    if on_path:
        return on_path

    source_tree_wrapper = Path(__file__).resolve().parents[2] / "wrapper" / "agent-wrapper.sh"
    if source_tree_wrapper.exists():
        return str(source_tree_wrapper)

    return "agent-wrapper"


def _same_executable(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left == right or os.path.realpath(left) == os.path.realpath(right):
        return True
    try:
        return os.path.exists(left) and os.path.exists(right) and os.path.samefile(left, right)
    except OSError:
        return False


def is_agent_wrapper_command(argv: list[str], wrapper_path: str | None = None) -> bool:
    if not argv:
        return False
    command = argv[0]
    if os.path.basename(command) == "agent-wrapper":
        return True
    wrapper_path = wrapper_path or resolve_agent_wrapper_path()
    return _same_executable(command, wrapper_path) or _same_executable(command, shutil.which("agent-wrapper"))


def build_wrapped_agent_argv(agent_command: str, agent_args: list[str]) -> list[str]:
    argv = [agent_command] + list(agent_args or [])
    wrapper_path = resolve_agent_wrapper_path()
    if is_agent_wrapper_command(argv, wrapper_path):
        return argv
    return [wrapper_path] + argv


def build_spin_command(agent_command: str, agent_args: list[str], no_fallback: bool) -> str:
    inner_command = shlex.join(build_wrapped_agent_argv(agent_command, agent_args))
    if no_fallback:
        return inner_command
    caller_path = os.environ.get("PATH", "")
    return f"bash -c {shlex.quote(f'export PATH={shlex.quote(caller_path)}; {inner_command}; zsh')}"


def handle(args):
    directory = os.path.abspath(os.path.expanduser(args.directory))
    if not os.path.isdir(directory):
        print(f"Error: directory does not exist: {directory}", file=sys.stderr)
        sys.exit(1)
    session = spin_session_name(directory)
    
    command = build_spin_command(args.agent_command, args.agent_args, args.no_fallback)

    # Do not forward the caller agent's identity to the spun agent.  The
    # tracker/RPC side assigns a fresh placeholder name and passes it as
    # SUGGESTED_AGENT_NAME after resolving conflicts.
    env = {k: v for k, v in os.environ.items() if k not in {"TMUX", "TMUX_PANE", "AGENT_ID", "AGENT_NAME", "AGENT_UUID"}}
    resolved_name = call_rpc("spin_agent", {
        "session": session,
        "directory": directory,
        "command": command,
        "name": session,
        "env": env,
    })
    if resolved_name:
        print(f"Agent spun successfully as: {resolved_name} in session: {session}")
