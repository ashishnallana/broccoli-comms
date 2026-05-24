from .common import call_rpc


def register(subparsers):
    parser = subparsers.add_parser("unregister", help="Unregister agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name", help="Agent name to unregister")
    group.add_argument("--id", dest="agent_id", help="Agent ID to unregister")
    group.add_argument("--pane", help="Tmux pane ID to unregister")
    parser.set_defaults(handler=handle)


def handle(args):
    params = {}
    if args.name:
        params["agent_name"] = args.name
    if args.agent_id:
        params["agent_id"] = args.agent_id
    if args.pane:
        params["tmux_pane"] = args.pane
    call_rpc("unregister", params)
    print("Agent unregistered.")
