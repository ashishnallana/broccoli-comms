import sys

from .common import call_rpc, parse_target_params


def register(subparsers):
    parser = subparsers.add_parser(
        "send-key",
        help="Send symbolic key presses directly to a registered agent pane",
        description=(
            "Send symbolic tmux-style key tokens directly to a local agent pane.\n"
            "This bypasses inbox messages and controls the target pane explicitly.\n"
            "Examples:\n"
            "  agent-tracker-ctl send-key alice C-c\n"
            "  agent-tracker-ctl send-key alice Enter\n"
            "  agent-tracker-ctl send-key 123e4567-e89b-12d3-a456-426614174000 C-c Enter\n"
            "  agent-tracker-ctl send-key host-a/alice C-c  # currently rejected while remote direct input is disabled\n"
            "\n"
            "Bare names/UUIDs are local-only. HOST/TARGET is delegated to the tracker backend."
        ),
    )
    parser.add_argument("target", metavar="TARGET", help="Local agent name/UUID or remote HOST/NAME_OR_UUID")
    parser.add_argument("keys", metavar="KEY", nargs="+", help="Symbolic key token(s), e.g. C-c Enter")
    parser.set_defaults(handler=handle)


def handle(args):
    if not args.keys:
        print("Error: send-key requires at least one KEY", file=sys.stderr)
        sys.exit(1)
    params = {
        **parse_target_params(args.target),
        "input_type": "keys",
        "keys": args.keys,
    }
    res = call_rpc("send_input", params)
    if isinstance(res, dict) and not res.get("success", True):
        print(f"Error: {res.get('error', 'Direct pane input failed')}", file=sys.stderr)
        sys.exit(1)
    print("Key(s) sent.")
