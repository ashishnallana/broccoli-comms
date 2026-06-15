import json

from .common import call_rpc


def register(subparsers):
    parser = subparsers.add_parser("assign-swarm", help="Assign a swarm to live local agents without restarting them")
    parser.add_argument("swarm", help="Swarm name")
    parser.add_argument("--main", required=True, help="Live local main agent name")
    parser.add_argument("--subagent", action="append", default=[], help="Live local subagent name; repeatable")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    parser.set_defaults(handler=handle)


def handle(args):
    result = call_rpc("assign_live_swarm", {"swarm": args.swarm, "main": args.main, "subagents": args.subagent})
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        members = ", ".join(f"{m['agent']}:{m['role']}" for m in result.get("members", []))
        print(f"Assigned swarm {result.get('swarm')}: {members}")
