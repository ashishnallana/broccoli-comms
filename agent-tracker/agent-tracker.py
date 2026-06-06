import fcntl
import logging
import os
import socket
import sys
import threading
import time
import signal

import state
import monitor
import rpc_handler
import http_sidecar
import registry_client
import permission_detection
import pane_output_lifecycle

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', stream=sys.stderr)

CACHE_DIR = state.CACHE_DIR
SOCKET_PATH = state.SOCKET_PATH
LOCK_PATH = state.LOCK_PATH


def _can_connect() -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(SOCKET_PATH)
        s.close()
        return True
    except OSError:
        return False


def setup_signals():
    def handle_exit(signum, frame):
        logging.info(f"Received signal {signum}, cleaning up socket and exiting...")
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except OSError as e:
                logging.warning(f"Failed to clean up socket on exit: {e}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)


_global_lock_file = None

def main():
    setup_signals()

    # Process Guard using a global lock file in /tmp to prevent duplicate trackers globally for this user.
    # We use /tmp because it is guaranteed to be consistent across divergent environments (unlike XDG dirs).
    global _global_lock_file
    _global_lock_file = open(f"/tmp/broccoli-comms-agent-tracker-{os.getuid()}.lock", "a+")
    try:
        fcntl.flock(_global_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logging.warning("Another instance of agent-tracker is already running globally for this user. Exiting.")
        sys.exit(0)

    os.makedirs(os.path.dirname(SOCKET_PATH), exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    with open(LOCK_PATH, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        if _can_connect():
            logging.error(f"Another instance of agent-tracker is already listening on {SOCKET_PATH}")
            sys.exit(1)

        if os.path.exists(SOCKET_PATH) and not _can_connect():
            logging.info(f"Removing stale socket at {SOCKET_PATH}")
            try:
                os.remove(SOCKET_PATH)
            except FileNotFoundError:
                pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(10)

    state.init_state()
    pane_output_lifecycle.recover_enabled_pane_outputs()
    
    # Start background threads
    threading.Thread(target=monitor.background_monitor, daemon=True).start()
    threading.Thread(target=monitor.background_inbox_reminder, daemon=True).start()
    threading.Thread(target=permission_detection.background_detection_monitor, daemon=True).start()
    threading.Thread(target=http_sidecar.serve_forever, daemon=True).start()
    threading.Thread(target=registry_client.background_sync, daemon=True).start()

    logging.info(f"Agent Tracker listening on {SOCKET_PATH}")

    while True:
        try:
            conn, _ = server.accept()
            # Each connection gets its own thread for parallelism
            threading.Thread(target=rpc_handler.handle_client, args=(conn,), daemon=True).start()
        except socket.error as e:
            logging.error(f"Server accept error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
