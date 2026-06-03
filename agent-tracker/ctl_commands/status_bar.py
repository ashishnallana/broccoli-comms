from .common import call_rpc, format_status_bar, get_current_tmux_pane, is_registry_connected, registry_connection_states


def register(subparsers):
    parser = subparsers.add_parser("status-bar", help="List agents for status bar")
    parser.add_argument("current_pane", nargs="?", help="Current tmux pane ID")
    parser.set_defaults(handler=handle, skip_ensure=True)


def handle(args):
    try:
        agents = call_rpc("list")
    except SystemExit:
        return
    current_pane = get_current_tmux_pane(args.current_pane)
    status_bar = format_status_bar(
        agents,
        current_pane,
        registry_connected=is_registry_connected(),
        registry_states=registry_connection_states(),
    )
    if status_bar:
        print(status_bar, end="")
