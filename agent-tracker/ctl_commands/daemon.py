import os
import shlex
import sys


def register(subparsers):
    parser = subparsers.add_parser("daemon", help="Run the tracker daemon in the foreground")
    parser.set_defaults(handler=handle, skip_ensure=True)


def handle(_args):
    import config
    daemon_cmd = config.get("executables", "agent_tracker")
    if not daemon_cmd:
        print("Error: executables.agent_tracker is not configured.", file=sys.stderr)
        sys.exit(1)
    os.execvp(shlex.split(daemon_cmd)[0], shlex.split(daemon_cmd))
