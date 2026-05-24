import sys

from .common import ensure_tracker_running


def register(subparsers):
    parser = subparsers.add_parser("ensure-running", help="Ensure the tracker daemon is running")
    parser.set_defaults(handler=handle, skip_ensure=True)


def handle(_args):
    if ensure_tracker_running():
        sys.exit(0)
    print("Error: failed to start or connect to agent-tracker.", file=sys.stderr)
    sys.exit(1)
