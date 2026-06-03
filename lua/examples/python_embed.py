#!/usr/bin/env python3
"""Demo-only Python host embedding for the Broccoli Lua tracker client.

This script is intentionally not wired into Broccoli runtime. It demonstrates how a
Python host can inject JSON and Unix-socket transport adapters into
lua/broccoli/tracker.lua.

Requires the optional `lupa` package when actually executed.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def lua_table_to_python(value: Any) -> Any:
    """Best-effort conversion from Lupa Lua tables to Python values."""
    if not hasattr(value, "items"):
        return value
    items = list(value.items())
    numeric_keys = [key for key, _ in items if isinstance(key, (int, float)) and int(key) == key]
    if numeric_keys and len(numeric_keys) == len(items):
        ordered = sorted((int(key), item) for key, item in items)
        if [key for key, _ in ordered] == list(range(1, len(ordered) + 1)):
            return [lua_table_to_python(item) for _, item in ordered]
    return {str(key): lua_table_to_python(item) for key, item in items}


def python_to_lua(lua: Any, value: Any) -> Any:
    """Convert JSON-like Python values to Lua tables."""
    if isinstance(value, dict):
        table = lua.table()
        for key, item in value.items():
            table[key] = python_to_lua(lua, item)
        return table
    if isinstance(value, list):
        table = lua.table()
        for index, item in enumerate(value, start=1):
            table[index] = python_to_lua(lua, item)
        return table
    return value


def request_unix_socket(socket_path: str, payload: str, timeout_ms: int) -> str:
    timeout = max(float(timeout_ms or 5000) / 1000.0, 0.001)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(socket_path)
        conn.sendall(payload.encode("utf-8"))
        conn.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8")


def request_fake(_socket_path: str, payload: str, _timeout_ms: int) -> str:
    request = json.loads(payload)
    method = request.get("method")
    params = request.get("params") or {}
    if method == "list":
        result = {
            "demo-agent": {
                "name": "demo-agent",
                "status": "idle",
                "scope": "local",
                "include_remote_seen": bool(params.get("include_remote")),
            }
        }
    elif method == "send_message":
        result = True
    elif method == "get_inbox":
        result = {"mode": "last_n", "messages": []}
    else:
        return json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": "Method not found"}})
    return json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result})


def first_return(value: Any) -> Any:
    """Return the first value from Lua calls that may produce multiple results."""
    if isinstance(value, tuple):
        return value[0]
    return value


def make_client(args: argparse.Namespace) -> tuple[Any, Any]:
    try:
        from lupa import LuaRuntime
    except ImportError as exc:
        raise SystemExit("This demo requires optional Python package `lupa`.") from exc

    lua = LuaRuntime(unpack_returned_tuples=True)
    package = lua.eval("package")
    lua_dir = str(args.lua_dir)
    package.path = f"{lua_dir}/?.lua;{lua_dir}/?/init.lua;" + package.path

    json_adapter = lua.table_from({
        "encode": lambda value: json.dumps(lua_table_to_python(value)),
        "decode": lambda payload: python_to_lua(lua, json.loads(payload)),
    })
    transport_adapter = lua.table_from({
        "request": request_fake if args.fake else request_unix_socket,
    })

    tracker = first_return(lua.require("broccoli.tracker"))
    client_opts = lua.table_from({
        "socket_path": args.socket,
        "timeout_ms": args.timeout_ms,
        "transport": transport_adapter,
        "json": json_adapter,
    })
    return lua, tracker.new(client_opts)


def call_client(lua: Any, client: Any, method: str, opts: dict[str, Any]) -> tuple[Any, Any]:
    fn = client[method]
    return fn(client, python_to_lua(lua, opts))


def print_json(value: Any) -> None:
    print(json.dumps(lua_table_to_python(value), indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo Python embedding for Broccoli Lua tracker client")
    parser.add_argument("command", choices=["list", "send-message", "read-inbox"])
    parser.add_argument("--socket", default="/tmp/agent-tracker.sock", help="agent-tracker Unix socket path")
    parser.add_argument("--lua-dir", type=Path, default=REPO_ROOT / "lua", help="path containing broccoli Lua modules")
    parser.add_argument("--timeout-ms", type=int, default=5000)
    parser.add_argument("--fake", action="store_true", help="use an in-process fake tracker response")
    parser.add_argument("--target", default="demo-agent", help="target for send-message")
    parser.add_argument("--message", default="hello from Python Lua demo")
    parser.add_argument("--agent-name", default="agent-communicator", help="agent name for read-inbox")
    parser.add_argument("--last", type=int, default=5)
    args = parser.parse_args()

    lua, client = make_client(args)
    if args.command == "list":
        result, err = call_client(lua, client, "list", {"include_remote": True})
    elif args.command == "send-message":
        result, err = call_client(lua, client, "send_message", {"target": args.target, "message": args.message})
    else:
        result, err = call_client(lua, client, "read_inbox", {"agent_name": args.agent_name, "last": args.last})

    if err is not None:
        print_json(err)
        return 1
    print_json(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
