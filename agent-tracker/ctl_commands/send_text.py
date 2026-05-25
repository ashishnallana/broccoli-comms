import sys

from .common import call_rpc, parse_target_params


def register(subparsers):
    parser = subparsers.add_parser(
        "send-text",
        help="Send literal text directly to a registered agent pane",
        description=(
            "Send literal text directly to a local agent pane via tmux.\n"
            "This bypasses inbox messages and controls the target pane explicitly.\n"
            "Examples:\n"
            "  agent-tracker-ctl send-text alice \"hello\"\n"
            "  agent-tracker-ctl send-text --no-submit alice \"draft only\"\n"
            "  agent-tracker-ctl send-text 123e4567-e89b-12d3-a456-426614174000 \"hello\"\n"
            "  agent-tracker-ctl send-text host-a/alice \"hello\"  # currently rejected while remote direct input is disabled\n"
            "\n"
            "Bare names/UUIDs are local-only. HOST/TARGET is delegated to the tracker backend."
        ),
    )
    parser.add_argument("--no-submit", action="store_true", help="Type text without pressing Enter")
    parser.add_argument("target", metavar="TARGET", help="Local agent name/UUID or remote HOST/NAME_OR_UUID")
    parser.add_argument("text", metavar="TEXT", nargs="...", help="Literal text to type; quote as needed")
    parser.set_defaults(handler=handle)


def _coerce_text(parts):
    parts = list(parts or [])
    if parts and parts[0] == "--":
        parts = parts[1:]
    if not parts:
        print("Error: send-text requires TEXT", file=sys.stderr)
        sys.exit(1)
    return " ".join(parts)


def handle(args):
    text = _coerce_text(args.text)
    params = {
        **parse_target_params(args.target),
        "input_type": "text",
        "text": text,
        "submit": not args.no_submit,
    }
    res = call_rpc("send_input", params)
    if isinstance(res, dict) and not res.get("success", True):
        print(f"Error: {res.get('error', 'Direct pane input failed')}", file=sys.stderr)
        sys.exit(1)
    print("Text sent.")
