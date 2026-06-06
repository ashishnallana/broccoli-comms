import json
import os
import sys
from .common import call_rpc


def register(subparsers):
    parser = subparsers.add_parser("pane-output", help="Control local pane-output observation pipes")
    parser.add_argument("action", choices=["enable", "disable", "status"], help="Pane-output action")
    parser.add_argument("target", nargs="?", help="Local target agent display name or ID")
    parser.add_argument("--id", dest="agent_id", help="Local target agent ID")
    parser.add_argument("--name", dest="agent_name", help="Local target agent name")
    parser.add_argument("--no-rotate", action="store_true", help="Do not rotate an already-attached broccoli pipe")
    parser.add_argument("--json", action="store_true", help="Print JSON response")
    parser.set_defaults(handler=handle)


def _target_params(args):
    params = {}
    target = args.target
    if args.agent_id:
        params["agent_id"] = args.agent_id
    elif args.agent_name:
        params["agent_name"] = args.agent_name
    elif target:
        if "/" in target or target.startswith("registry:"):
            raise ValueError("pane-output controls only accept local agent names or IDs")
        if len(target) == 36 and target.replace("-", "").isalnum():
            params["agent_id"] = target
        else:
            params["agent_name"] = target
    elif "AGENT_ID" in os.environ:
        params["agent_id"] = os.environ["AGENT_ID"]
    elif "AGENT_NAME" in os.environ:
        params["agent_name"] = os.environ["AGENT_NAME"]
    else:
        raise ValueError("target agent is required")
    return params


def _print_text(action, result):
    agent = result.get("agent_name") or result.get("agent_id") or "agent"
    enabled = "enabled" if result.get("enabled") else "disabled"
    if action == "enable":
        detail = "attached" if result.get("attached") else "already attached"
        print(f"Pane output {enabled} for {agent} ({detail}).")
    elif action == "disable":
        detail = "detached" if result.get("detached") else "not detached"
        print(f"Pane output {enabled} for {agent} ({detail}).")
    else:
        configured = "configured" if result.get("configured") else "not configured"
        print(f"Pane output is {enabled} for {agent} ({configured}).")


def handle(args):
    try:
        params = _target_params(args)
        if args.action == "enable":
            params["rotate"] = not args.no_rotate
            result = call_rpc("enable_pane_output", params)
        elif args.action == "disable":
            result = call_rpc("disable_pane_output", params)
        else:
            result = call_rpc("pane_output_status", params)

        if args.json:
            print(json.dumps(result))
        else:
            _print_text(args.action, result)
    except Exception as e:
        print(f"Error controlling pane output: {e}", file=sys.stderr)
        sys.exit(1)
