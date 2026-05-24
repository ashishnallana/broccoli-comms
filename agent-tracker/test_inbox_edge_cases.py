import json
import os
import socket
import subprocess
import sys
import time
import uuid

SOCKET_PATH = os.environ.get("AGENT_TRACKER_SOCKET", os.path.join(os.path.expanduser("~/.cache"), "agent-tracker", "agent-tracker.sock"))

def call_rpc(method, params={}):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect(SOCKET_PATH)
        s.sendall(json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode())
        s.shutdown(socket.SHUT_WR)
        
        resp = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            resp += chunk
            
        data = json.loads(resp.decode())
        if "error" in data:
            print(f"RPC Error: {data['error']['message']}", file=sys.stderr)
            return None
        return data.get("result")
    except Exception as e:
        print(f"Failed to connect to tracker: {e}", file=sys.stderr)
        return None

def main():
    print("Starting Inbox Edge Cases Test...")

    # 1. Spin a test agent
    agent_name = "edge-test-agent"
    try:
        session = subprocess.check_output(["tmux", "display-message", "-p", "#S"]).decode("utf-8").strip()
    except Exception as e:
        print(f"Failed to get tmux session: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Spinning agent {agent_name}...")
    resolved_name = call_rpc("spin_agent", {"session": session, "command": "sleep 60", "name": agent_name})
    if not resolved_name:
        print("Failed to spin agent", file=sys.stderr)
        sys.exit(1)
    print(f"Spun agent: {resolved_name}")

    # Simulate agent registration
    time.sleep(2)
    params = {
        "session": session,
        "tmux_pane": "%999",
        "wrapper_pid": os.getpid(),
        "tmux_socket": "default",
        "name": resolved_name
    }
    call_rpc("register", params)

    # 2. Test Long Message (> 4KB)
    print("\n--- Test 1: Long Message ---")
    long_msg = "A" * 5000 # 5KB message
    print(f"Sending 5KB message to {resolved_name}...")
    call_rpc("send_message", {"sender_name": "tester", "agent_name": resolved_name, "message": long_msg})
    
    print("Reading inbox...")
    resp = call_rpc("get_inbox", {"agent_name": resolved_name, "clear": True})
    if not resp:
        print("Failed to get inbox", file=sys.stderr)
        sys.exit(1)
        
    messages = []
    for line in resp.split("\n"):
        if line.strip():
            try:
                msg_obj = json.loads(line)
                messages.append(msg_obj.get("message"))
            except json.JSONDecodeError:
                pass
                
    if long_msg in messages:
        print("Success: Long message received correctly!")
    else:
        print("Error: Long message not found in response", file=sys.stderr)
        sys.exit(1)

    # 3. Test Special Characters
    print("\n--- Test 2: Special Characters ---")
    special_msg = "Message with 'quotes', \"double quotes\", \n newlines, and {json: structures}."
    print(f"Sending special message to {resolved_name}...")
    call_rpc("send_message", {"sender_name": "tester", "agent_name": resolved_name, "message": special_msg})
    
    print("Reading inbox...")
    resp = call_rpc("get_inbox", {"agent_name": resolved_name, "clear": True})
    
    messages = []
    for line in resp.split("\n"):
        if line.strip():
            try:
                msg_obj = json.loads(line)
                messages.append(msg_obj.get("message"))
            except json.JSONDecodeError:
                pass
                
    if special_msg in messages:
        print("Success: Special characters message received correctly!")
    else:
        print("Error: Special characters message not found in response", file=sys.stderr)
        print(f"Messages: {messages}", file=sys.stderr)
        sys.exit(1)

    # 4. Test Renaming and Inbox
    print("\n--- Test 3: Renaming and Inbox ---")
    new_name = f"{resolved_name}-new"
    print(f"Renaming {resolved_name} to {new_name}...")
    call_rpc("rename", {"old_name": resolved_name, "new_name": new_name})
    
    print(f"Sending message to new name {new_name}...")
    test_msg = "Test message after rename"
    call_rpc("send_message", {"sender_name": "tester", "agent_name": new_name, "message": test_msg})
    
    print(f"Reading inbox for {new_name}...")
    resp = call_rpc("get_inbox", {"agent_name": new_name, "clear": True})
    
    messages = []
    for line in resp.split("\n"):
        if line.strip():
            try:
                msg_obj = json.loads(line)
                messages.append(msg_obj.get("message"))
            except json.JSONDecodeError:
                pass
                
    if test_msg in messages:
        print("Success: Message received after rename!")
    else:
        print("Error: Message not found in response after rename", file=sys.stderr)
        sys.exit(1)

    print("\nAll edge case tests passed successfully!")

if __name__ == "__main__":
    main()
