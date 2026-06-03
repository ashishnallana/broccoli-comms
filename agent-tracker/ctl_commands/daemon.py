import os
import shlex
import sys

from .common import tracker_daemon_command


def register(subparsers):
    parser = subparsers.add_parser("daemon", help="Run the tracker daemon in the foreground")
    parser.set_defaults(handler=handle, skip_ensure=True)


def handle(_args):
    daemon_cmd = tracker_daemon_command()
    if not daemon_cmd:
        print("Error: could not resolve agent-tracker daemon command.", file=sys.stderr)
        sys.exit(1)
    os.execvp(shlex.split(daemon_cmd)[0], shlex.split(daemon_cmd))
