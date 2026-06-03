import os
import sys
import json
import socket
import uuid
from .common import call_rpc, default_capture_pane_lines


def _local_tracker_hostname():
    try:
        info = call_rpc("tracker_info", {}) or {}
        if info.get("hostname"):
            return info["hostname"]
    except Exception:
        pass
    import config
    return config.get("tracker", "hostname", socket.gethostname())

def register(subparsers):
    parser = subparsers.add_parser("send-pane", help="Send a tmux pane snapshot to a target agent")
    parser.add_argument("target_address", help="Target agent address (e.g., 'alice', 'host-a/alice')")
    parser.add_argument("--source", help="Display name of the source agent to capture (defaults to self)")
    parser.add_argument("--id", help="ID of the source agent to capture")
    parser.add_argument("--pane", help="tmux pane ID of the source to capture (e.g., %%0)")
    parser.add_argument("--last", type=int, default=default_capture_pane_lines(), help="Number of history/scrollback lines to capture")
    parser.add_argument("--note", help="Optional custom note to attach to the snapshot")
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Message encapsulation format (markdown or json)"
    )
    parser.set_defaults(handler=handle)


def handle(args):
    # 1. Prepare capture payload parameter dictionary for source
    capture_params = {
        "last_lines": args.last,
        "include_ansi": False # We do not want ANSI codes in snapshots delivered to other agents
    }
    
    if args.source:
        capture_params["agent_name"] = args.source
    if args.id:
        capture_params["agent_id"] = args.id
    if args.pane:
        capture_params["tmux_pane"] = args.pane

    # If the source agent is remote (contains /), publish a pane_capture_request tracker event instead of capturing locally
    source_agent = args.source
    if source_agent and "/" in source_agent:
        remote_host, remote_name = source_agent.split("/", 1)
        try:
            # Retrieve all agents to look up the remote tracker ID
            agents = call_rpc("list", {"include_remote": True})
            if not agents:
                print("Error: Failed to retrieve agent list from agent-tracker.", file=sys.stderr)
                sys.exit(1)
                
            remote_info = agents.get(source_agent)
            if not remote_info:
                print(f"Error: Remote source agent '{source_agent}' not found in tracker registries.", file=sys.stderr)
                sys.exit(1)
                
            target_tracker_id = remote_info.get("tracker_id")
            if not target_tracker_id:
                print(f"Error: Could not determine tracker ID for remote host '{remote_host}'.", file=sys.stderr)
                sys.exit(1)
                
            local_hostname = _local_tracker_hostname()
            target_delivery_address = args.target_address
            if "/" not in target_delivery_address:
                target_delivery_address = f"{local_hostname}/{target_delivery_address}"

            requester = os.environ.get("AGENT_ID") or os.environ.get("AGENT_NAME") or "cli-user"
            request_id = str(uuid.uuid4())
            
            event_payload = {
                "request_id": request_id,
                "source": remote_name,
                "target": target_delivery_address,
                "requester": requester,
                "format": args.format,
                "last": args.last,
                "include_ansi": False,
                "note": args.note
            }
            
            publish_params = {
                "target_tracker_id": target_tracker_id,
                "event_type": "pane_capture_request",
                "payload": event_payload
            }
            
            res = call_rpc("publish_tracker_event", publish_params)
            if res:
                print(f"Remote capture request successfully dispatched to host '{remote_host}' (Request ID: {request_id}).")
                return
            else:
                print(f"Error: Failed to dispatch remote capture request to host '{remote_host}'.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error dispatching remote capture request: {e}", file=sys.stderr)
            sys.exit(1)

    # If no source parameters are specified, capture_pane RPC will default to self-capture (caller_pid lookup)
    
    try:
        # 2. Fetch the source pane snapshot locally
        snapshot = call_rpc("capture_pane", capture_params)
        if not snapshot:
            print("Error: Failed to extract pane snapshot from agent-tracker.", file=sys.stderr)
            sys.exit(1)

        # 3. Format snapshot based on requested layout format
        if args.format == "json":
            payload = {
                "type": "pane_snapshot",
                "source_agent_name": snapshot.get("agent_name"),
                "source_agent_id": snapshot.get("agent_id"),
                "tmux_pane": snapshot.get("tmux_pane"),
                "session": snapshot.get("session"),
                "copy_mode": snapshot.get("copy_mode"),
                "captured_at": snapshot.get("captured_at"),
                "lines_requested": snapshot.get("lines_requested"),
                "note": args.note,
                "content": snapshot.get("content", "")
            }
            message_text = json.dumps(payload)
        else: # markdown
            note_block = ""
            if args.note:
                note_block = f"- **User Note:** {args.note}\n"
                
            source_display = snapshot.get("agent_name") or "Unnamed Agent"
            if snapshot.get("agent_id"):
                source_display += f" ({snapshot.get('agent_id')})"
                
            message_text = (
                f"### Pane Capture Snapshot from {source_display}\n"
                f"- **Pane:** {snapshot.get('tmux_pane') or 'unknown'}\n"
                f"- **Session:** {snapshot.get('session') or 'unknown'}\n"
                f"- **Copy Mode:** {'Active' if snapshot.get('copy_mode') else 'Inactive'}\n"
                f"- **Captured At:** {snapshot.get('captured_at')}\n"
                f"{note_block}"
                f"\n```\n"
                f"{snapshot.get('content', '')}\n"
                f"```\n"
            )

        # 4. Prepare send_message params
        send_params = {
            "message": message_text
        }
        if "/" in args.target_address:
            send_params["target_address"] = args.target_address
        elif len(args.target_address) == 36 and args.target_address.replace("-", "").isalnum():
            send_params["agent_id"] = args.target_address
        else:
            send_params["agent_name"] = args.target_address
        
        # Make the snapshot appear in the conversation with the captured source
        # agent.  Remote pane captures already deliver with the remote source as
        # sender; local captures should do the same instead of sending the
        # message as agent-communicator/cli-user.
        if snapshot.get("agent_id"):
            send_params["sender_id"] = snapshot.get("agent_id")
        if snapshot.get("agent_name"):
            send_params["sender_name"] = snapshot.get("agent_name")
        if "sender_id" not in send_params and "sender_name" not in send_params:
            if "AGENT_ID" in os.environ:
                send_params["sender_id"] = os.environ["AGENT_ID"]
            elif "AGENT_NAME" in os.environ:
                send_params["sender_name"] = os.environ["AGENT_NAME"]

        # 5. Deliver the message via send_message RPC
        res = call_rpc("send_message", send_params)
        if res:
            print(f"Snapshot successfully sent to '{args.target_address}'.")
        else:
            print(f"Error: Failed to send snapshot to '{args.target_address}'.", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error executing send-pane: {e}", file=sys.stderr)
        sys.exit(1)
