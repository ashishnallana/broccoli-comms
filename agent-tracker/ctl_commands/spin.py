import argparse
import os
import shlex
import sys

from .common import call_rpc, spin_session_name


def register(subparsers):
    parser = subparsers.add_parser("spin", help="Spin a new agent in a tmux session for a directory")
    parser.add_argument("--no-fallback", "-n", action="store_true", help="Disable automatic bash shell wrapper and zsh fallback")
    parser.add_argument("directory", help="Working directory; leaf name becomes the tmux session/agent base name")
    parser.add_argument("agent_command", help="Agent command to run")
    parser.add_argument("agent_args", nargs=argparse.REMAINDER, help="Arguments for the agent command")
    parser.set_defaults(handler=handle)


def handle(args):
    directory = os.path.abspath(os.path.expanduser(args.directory))
    if not os.path.isdir(directory):
        print(f"Error: directory does not exist: {directory}", file=sys.stderr)
        sys.exit(1)
    session = spin_session_name(directory)
    
    inner_command = shlex.join([args.agent_command] + args.agent_args)
    if args.no_fallback:
        command = inner_command
    else:
        caller_path = os.environ.get("PATH", "")
        command = f"bash -c {shlex.quote(f'export PATH={shlex.quote(caller_path)}; {inner_command}; zsh')}"

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
