import argparse
import json
import os
import shlex
import subprocess
import sys

from .common import call_rpc


def register(subparsers):
    parser = subparsers.add_parser("save", help="Save active or custom agent configurations")
    parser.add_argument("--agent-name", "-a", help="Config name (defaults to active tmux pane's @agent_name)")
    parser.add_argument("--working-dir", "-w", help="Working directory (defaults to current pane path)")
    parser.add_argument("--description", "-d", help="Friendly description")
    parser.add_argument("--command", "-c", help="Command string to run (defaults to active pane's @agent_cmd)")
    parser.set_defaults(handler=handle)


def query_tmux_option(pane, option):
    try:
        res = subprocess.run(["tmux", "show-options", "-p", "-t", pane, option], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout:
            parts = res.stdout.strip().split(maxsplit=1)
            if len(parts) == 2:
                return parts[1].strip('"')
    except Exception:
        pass
    return None


def query_tmux_path(pane):
    try:
        res = subprocess.run(["tmux", "display-message", "-p", "-t", pane, "#{pane_current_path}"], capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def handle(args):
    agent_name = args.agent_name
    working_dir = args.working_dir
    command = args.command
    description = args.description

    # Query running agents from daemon
    running_agents = {}
    try:
        agents = call_rpc("list_agents", {})
        if agents:
            running_agents = agents
    except Exception:
        pass

    matched_agent = None
    if agent_name:
        if agent_name in running_agents:
            matched_agent = running_agents[agent_name]
        else:
            # Check if name matches prefix (e.g., zv2-billing-fix matches zv2-billing-fix-agent-1)
            for k, v in running_agents.items():
                if k.startswith(f"{agent_name}-agent-") or k == agent_name:
                    matched_agent = v
                    break

    if matched_agent:
        print(f"Found active running agent matching name: {agent_name}")
        if not working_dir:
            working_dir = matched_agent.get("cwd")
        if not command:
            command = matched_agent.get("agent_cmd")
        # Strip running agent suffix
        clean_name = agent_name
        if "-agent-" in clean_name:
            clean_name = clean_name.split("-agent-")[0]
        agent_name = clean_name

    # Fallback: Query Tmux pane if run inside tmux
    tmux_pane = os.environ.get("TMUX_PANE")
    if not matched_agent and tmux_pane:
        if not agent_name:
            agent_name = query_tmux_option(tmux_pane, "@agent_name")
        if not working_dir:
            working_dir = query_tmux_path(tmux_pane)
        if not command:
            command = query_tmux_option(tmux_pane, "@agent_cmd")

    if not agent_name:
        print("Error: --agent-name was not provided and could not be autodetected.", file=sys.stderr)
        sys.exit(1)
    if not working_dir:
        print("Error: --working-dir was not provided and could not be autodetected.", file=sys.stderr)
        sys.exit(1)
    if not command:
        print("Error: --command was not provided and could not be autodetected.", file=sys.stderr)
        sys.exit(1)

    working_dir = os.path.abspath(os.path.expanduser(working_dir))

    try:
        parts = shlex.split(command)
        agent_command = parts[0]
        agent_args = parts[1:]
    except Exception as e:
        print(f"Error: failed to parse command string: {e}", file=sys.stderr)
        sys.exit(1)

    if not description:
        description = f"Auto-saved configuration for agent {agent_name} in {working_dir}"

    home = os.path.expanduser("~")
    config_dir = os.path.join(home, ".config", "agent-tracker", "agents", agent_name)
    os.makedirs(config_dir, exist_ok=True)
    config_file = os.path.join(config_dir, "config.json")

    payload = {
        "directory": working_dir,
        "agent-command": agent_command,
        "agent-args": agent_args,
        "description": description,
    }

    try:
        with open(config_file, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"Successfully saved agent configuration: {agent_name}")
        print(f"Path: {config_file}")
    except Exception as e:
        print(f"Error: failed to write configuration file: {e}", file=sys.stderr)
        sys.exit(1)
