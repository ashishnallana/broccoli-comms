import os
import sys
import json
from .common import call_rpc, default_capture_pane_lines

def register(subparsers):
    parser = subparsers.add_parser("capture-pane", help="Capture visible text of a pane")
    parser.add_argument("target", nargs="?", help="Target agent display name (or ID, or pane)")
    parser.add_argument("--id", help="Target agent ID (UUID)")
    parser.add_argument("--pane", help="Target tmux pane ID (e.g., %%0)")
    parser.add_argument("--last", type=int, default=default_capture_pane_lines(), help="Number of history/scrollback lines to capture")
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output format (text, markdown, or json)"
    )
    parser.add_argument("--include-ansi", action="store_true", help="Do not strip ANSI formatting and color sequences")
    parser.set_defaults(handler=handle)


def handle(args):
    params = {
        "last_lines": args.last,
        "include_ansi": args.include_ansi
    }

    # Resolve target. If positional target is provided, map it.
    if args.target:
        # If it looks like a pane, set pane
        if args.target.startswith("%") and args.target[1:].isdigit():
            params["pane"] = args.target
        # If it is a UUID, set agent_id
        elif len(args.target) == 36 and args.target.replace("-", "").isalnum():
            params["agent_id"] = args.target
        else:
            params["agent_name"] = args.target

    # Explicit flags override positional argument
    if args.id:
        params["agent_id"] = args.id
    if args.pane:
        params["pane"] = args.pane

    # If no target is explicitly provided, default to self by looking up environment
    if not params.get("agent_name") and not params.get("agent_id") and not params.get("pane"):
        if "AGENT_ID" in os.environ:
            params["agent_id"] = os.environ["AGENT_ID"]
        elif "AGENT_NAME" in os.environ:
            params["agent_name"] = os.environ["AGENT_NAME"]

    try:
        res = call_rpc("capture_pane", params)
        if not res:
            print("Error: No response from agent-tracker.", file=sys.stderr)
            sys.exit(1)
            
        if args.format == "json":
            print(json.dumps(res))
        elif args.format == "markdown":
            print(f"# Tmux Pane Capture - {res.get('agent_name') or 'Unnamed Agent'} ({res.get('tmux_pane')})")
            print(f"- **Session:** {res.get('session') or 'unknown'}")
            print(f"- **Copy Mode:** {'Active' if res.get('copy_mode') else 'Inactive'}")
            print(f"- **Captured At:** {res.get('captured_at')}")
            print(f"- **Lines Requested:** {res.get('lines_requested')}")
            print("\n## Screen Content\n")
            print("```")
            print(res.get("content", ""))
            print("```")
        else: # text
            print(res.get("content", ""))
            
    except Exception as e:
        print(f"Error capturing pane: {e}", file=sys.stderr)
        sys.exit(1)
