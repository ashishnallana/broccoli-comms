import os
import sys

from .common import call_rpc


def register(subparsers):
    parser = subparsers.add_parser("rename", help="Rename agent")
    parser.add_argument("names", nargs="+", help="New name (or old_name new_name with --force)")
    parser.add_argument("--force", action="store_true", help="Force rename of another agent")
    parser.set_defaults(handler=handle)


def handle(args):
    if args.force:
        if len(args.names) != 2:
            print("Error: --force requires <old_name> <new_name>", file=sys.stderr)
            sys.exit(1)
        old_name, new_name = args.names
    else:
        if len(args.names) != 1:
            print("Error: rename requires <new_name> (use --force to rename someone else)", file=sys.stderr)
            sys.exit(1)
        old_name = None
        new_name = args.names[0]
    params = {"old_name": old_name, "new_name": new_name, "force": args.force}
    if "AGENT_ID" in os.environ:
        params["agent_id"] = os.environ["AGENT_ID"]
    elif "AGENT_NAME" in os.environ:
        params["agent_name"] = os.environ["AGENT_NAME"]
    call_rpc("rename", params)
    print("Agent renamed.")
