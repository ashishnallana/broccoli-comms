import os
import shlex
import sys


def register(subparsers):
    parser = subparsers.add_parser("daemon", help="Run the tracker daemon in the foreground")
    parser.set_defaults(handler=handle, skip_ensure=True)


def handle(_args):
    daemon_cmd = os.environ.get("AGENT_TRACKER_DAEMON")
    if not daemon_cmd:
        print("Error: AGENT_TRACKER_DAEMON is not configured.", file=sys.stderr)
        sys.exit(1)
    os.execvp(shlex.split(daemon_cmd)[0], shlex.split(daemon_cmd))
