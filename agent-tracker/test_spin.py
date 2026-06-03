import json
import os
import socket
import subprocess
import sys
import time

SOCKET_PATH = os.environ.get("AGENT_TRACKER_SOCKET", os.path.join(os.path.expanduser("~/.cache"), "broccoli-comms", "runtime", "agent-tracker.sock"))

def call_rpc(method, params={}):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCKET_PATH)
        s.sendall(json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode())
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        resp = b"".join(chunks)
        data = json.loads(resp.decode())
        if "error" in data:
            print(f"RPC Error: {data['error']['message']}", file=sys.stderr)
            return None
        return data.get("result")
    except Exception as e:
        print(f"Failed to connect to tracker: {e}", file=sys.stderr)
        return None

def main():
    print("Starting spin_agent test...")

    try:
        session = subprocess.check_output(["tmux", "display-message", "-p", "#S"]).decode("utf-8").strip()
    except Exception as e:
        print(f"Failed to get tmux session: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Current session: {session}")

    # Call spin_agent
    command = "sleep 5"
    test_name = f"{session}-test-spin-agent"
    print(f"Calling spin_agent with name: {test_name} and command: {command}...")
    agent_name = call_rpc("spin_agent", {"session": session, "command": command, "name": test_name})

    if not agent_name:
        print("Failed to spin agent", file=sys.stderr)
        sys.exit(1)
    print(f"Spun agent: {agent_name}")

    # Wait a bit for the agent to start and register
    print("Waiting for agent to register...")
    time.sleep(2)

    # Verify it is listed
    agents = call_rpc("list")
    if agent_name not in agents:
        print(f"Error: {agent_name} not found in list after spinning", file=sys.stderr)
        sys.exit(1)
    print("Agent found in list!")

    info = agents[agent_name]
    print(f"Agent info: {info}")

    # Test conflict handling
    print("Testing conflict handling...")
    print(f"Calling spin_agent again with SAME name: {test_name}...")
    agent_name_2 = call_rpc("spin_agent", {"session": session, "command": command, "name": test_name})
    
    if not agent_name_2:
        print("Failed to spin second agent", file=sys.stderr)
        sys.exit(1)
    print(f"Spun second agent: {agent_name_2}")
    
    expected_name = f"{test_name}-1"
    if agent_name_2 != expected_name:
        print(f"Error: Expected name {expected_name}, got {agent_name_2}", file=sys.stderr)
        sys.exit(1)
    print("Conflict resolved successfully!")
    
    # Wait for second agent to register
    print("Waiting for second agent to register...")
    time.sleep(2)
    
    agents = call_rpc("list")
    if agent_name_2 not in agents:
        print(f"Error: {agent_name_2} not found in list after spinning", file=sys.stderr)
        sys.exit(1)
        
    info_2 = agents[agent_name_2]
    pane_2 = info_2.get("tmux_pane")
    
    # Cleanup both panes
    pane = info.get("tmux_pane")
    if pane:
        print(f"Killing first test pane {pane}...")
        subprocess.run(["tmux", "kill-pane", "-t", pane])
        
    if pane_2:
        print(f"Killing second test pane {pane_2}...")
        subprocess.run(["tmux", "kill-pane", "-t", pane_2])

    print("Test passed successfully!")

if __name__ == "__main__":
    main()
