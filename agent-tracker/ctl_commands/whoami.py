import os

from .common import call_rpc


def register(subparsers):
    parser = subparsers.add_parser("whoami", help="Show current agent identity")
    parser.set_defaults(handler=handle, skip_ensure=True)


def handle(_args):
    params = {}
    if "AGENT_ID" in os.environ:
        params["agent_id"] = os.environ["AGENT_ID"]
    elif "AGENT_NAME" in os.environ:
        params["agent_name"] = os.environ["AGENT_NAME"]
    info = call_rpc("whoami", params)
    if info:
        print(f"Name:     {info.get('name')}")
        print(f"Agent ID: {info.get('agent_id') or info.get('uuid')}")
        print(f"UUID:     {info.get('uuid')}")
        print(f"PID:      {info.get('pid')}")
        print(f"Pane ID:  {info.get('pane_id')}")
