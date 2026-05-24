import os

from .common import call_rpc


def register(subparsers):
    parser = subparsers.add_parser("read-inbox", help="Read agent inbox")
    parser.add_argument("--clear", action="store_true", help="Clear inbox after reading")
    parser.add_argument("--name", help="Agent name to read inbox for (defaults to current agent)")
    parser.add_argument("--id", dest="agent_id", help="Agent ID to read inbox for")
    parser.add_argument("--last", "-l", type=int, help="Read last N messages")
    parser.set_defaults(handler=handle)


def handle(args):
    params = {"clear": args.clear}
    if args.agent_id:
        params["agent_id"] = args.agent_id
    elif args.name:
        params["agent_name"] = args.name
    elif "AGENT_ID" in os.environ:
        params["agent_id"] = os.environ["AGENT_ID"]
    elif "AGENT_NAME" in os.environ:
        params["agent_name"] = os.environ["AGENT_NAME"]
    if args.last is not None:
        params["last_n"] = args.last
    inbox_data = call_rpc("get_inbox", params)
    if not inbox_data:
        print("No messages found.")
        return
    mode = inbox_data.get("mode")
    messages = inbox_data.get("messages", [])
    if mode == "history" and not args.last:
        if not messages:
            print("No unread messages.")
        else:
            for msg in messages:
                read_str = "Read" if msg.get("read", False) else "Unread"
                msg_text = msg.get("message", "")
                truncated = msg_text[:50] + "..." if len(msg_text) > 50 else msg_text
                print(f"{msg.get('timestamp')}, {read_str}, {msg.get('sender')}, {truncated}")
            print("use agent-tracker-ctl read-inbox --last n to print last n messages.")
        return
    if not messages:
        print("No messages found." if mode == "last_n" else "No unread messages.")
        return
    for msg in messages:
        print(f"[{msg.get('timestamp')}] From {msg.get('sender')}: {msg.get('message')}")
