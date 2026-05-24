import subprocess
import sys

from .common import call_rpc, tmux_command, tmux_env


def register(subparsers):
    parser = subparsers.add_parser("focus", help="Focus agent pane")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("agent_name", nargs="?", help="Agent name to focus")
    group.add_argument("--id", dest="agent_id", help="Agent ID to focus")
    group.add_argument("--next", action="store_true", help="Focus next agent")
    group.add_argument("--prev", action="store_true", help="Focus previous agent")
    parser.set_defaults(handler=handle)


def handle(args):
    agents = call_rpc("list")
    if not agents:
        print("No active agents.", file=sys.stderr)
        sys.exit(1)
    agent_names = list(agents.keys())
    if args.next or args.prev:
        try:
            current_pane = subprocess.check_output(
                tmux_command(["display-message", "-p", "#{pane_id}"]),
                env=tmux_env(),
            ).decode().strip()
        except subprocess.CalledProcessError:
            current_pane = ""
        current_agent = next((name for name, info in agents.items() if info.get("tmux_pane") == current_pane), None)
        if not current_agent:
            target_agent = agent_names[0]
        else:
            idx = agent_names.index(current_agent)
            target_agent = agent_names[(idx + (1 if args.next else -1)) % len(agent_names)]
    else:
        target_agent = args.agent_name
        if args.agent_id and not target_agent:
            target_agent = next((name for name, info in agents.items() if info.get("agent_id") == args.agent_id or info.get("uuid") == args.agent_id), None)
    if target_agent not in agents:
        print(f"Agent {target_agent} not found.", file=sys.stderr)
        sys.exit(1)
    info = agents[target_agent]
    tmux_socket = info.get("tmux_socket")
    run_env = tmux_env(strip_inherited=bool(tmux_socket))
    subprocess.run(tmux_command(["switch-client", "-t", info.get("session")], tmux_socket), env=run_env)
    subprocess.run(tmux_command(["select-window", "-t", info.get("tmux_pane")], tmux_socket), env=run_env)
    subprocess.run(tmux_command(["select-pane", "-t", info.get("tmux_pane")], tmux_socket), env=run_env)
