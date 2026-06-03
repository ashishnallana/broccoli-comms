"""Integration tests for agent-tracker-ctl send-message --verify."""

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
            return {"error": data["error"]}
        return {"result": data.get("result")}
    except Exception as e:
        print(f"Failed to connect to tracker: {e}", file=sys.stderr)
        return None

def get_current_pane():
    try:
        return subprocess.check_output(["tmux", "display-message", "-p", "#{pane_id}"]).decode().strip()
    except Exception:
        return None

def get_tmux_socket():
    tmux_env = os.environ.get("TMUX")
    if tmux_env:
        return tmux_env.split(",")[0]
    return "default"

def main():
    print("Starting send-message --verify integration tests...")
    
    current_pane = get_current_pane()
    if not current_pane:
        print("Error: Must be run inside a tmux session to test success path", file=sys.stderr)
        sys.exit(1)
        
    tmux_socket = get_tmux_socket()
    print(f"Detected tmux socket: {tmux_socket}")
    
    ctl_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-tracker-ctl.py")

    # Test Case 1: Dead Pane Failure Path
    print("\n--- Test Case 1: Dead Pane (Expect Failure) ---")
    receiver_name = "test-receiver-dead"
    reg_res = call_rpc("register", {
        "session": "test-session",
        "tmux_pane": "%9999", # Non-existent dead pane
        "wrapper_pid": 12345,
        "tmux_socket": tmux_socket,
        "name": receiver_name
    })
    print(f"Register response: {reg_res}")
    if not reg_res or "error" in reg_res:
        print("Error: Failed to register dead pane receiver", file=sys.stderr)
        sys.exit(1)
    
    try:
        print("Sending message with --verify to dead pane...")
        res = subprocess.run(
            ["python3", ctl_script, "send-message", "--verify", receiver_name, "test message"],
            capture_output=True,
            text=True,
            check=False
        )
        print(f"Exit code: {res.returncode}")
        print(f"Stdout: {res.stdout.strip()}")
        print(f"Stderr: {res.stderr.strip()}")
        
        if res.returncode == 0:
            print("Error: Expected exit code non-zero for dead pane, got 0", file=sys.stderr)
            sys.exit(1)
        if "Error:" not in res.stderr and "RPC Error:" not in res.stderr:
            print("Error: Expected error message in stderr", file=sys.stderr)
            sys.exit(1)
        print("Test Case 1 Passed.")
    finally:
        call_rpc("unregister", {"agent_name": receiver_name})

    # Test Case 2: Active Pane Success Path
    print("\n--- Test Case 2: Active Pane (Expect Success) ---")
    receiver_name = "test-receiver-active"
    reg_res = call_rpc("register", {
        "session": "test-session",
        "tmux_pane": current_pane,
        "wrapper_pid": os.getpid(),
        "tmux_socket": tmux_socket,
        "name": receiver_name
    })
    print(f"Register response: {reg_res}")
    if not reg_res or "error" in reg_res:
        print("Error: Failed to register active pane receiver", file=sys.stderr)
        sys.exit(1)
    
    try:
        print(f"Sending message with --verify to active pane {current_pane}...")
        res = subprocess.run(
            ["python3", ctl_script, "send-message", "--verify", receiver_name, "test message success"],
            capture_output=True,
            text=True,
            check=False
        )
        print(f"Exit code: {res.returncode}")
        print(f"Stdout: {res.stdout.strip()}")
        print(f"Stderr: {res.stderr.strip()}")
        
        if res.returncode != 0:
            print(f"Error: Expected exit code 0 for active pane, got {res.returncode}", file=sys.stderr)
            sys.exit(1)
        print("Test Case 2 Passed.")
    finally:
        call_rpc("unregister", {"agent_name": receiver_name})

    print("\nAll integration tests passed successfully!")

if __name__ == "__main__":
    main()
