import json
import os

from .common import call_rpc, fetch_registry_agents, merge_registry_agents


def register(subparsers):
    parser = subparsers.add_parser("list", help="List agents in JSON format")
    parser.set_defaults(handler=handle)


def handle(_args):
    params = {}
    if "AGENT_ID" in os.environ:
        params["agent_id"] = os.environ["AGENT_ID"]
    elif "AGENT_NAME" in os.environ:
        params["agent_name"] = os.environ["AGENT_NAME"]
    agents = call_rpc("list", params)
    agents = merge_registry_agents(agents, fetch_registry_agents())
    print(json.dumps(agents))
