#!/usr/bin/env python3
"""Deterministic Broccoli Comms E2E test agent.

This is intentionally a test harness agent, not a fix. It is launched through
`broccoli-comms agent add ... --command ...` and uses the Broccoli Comms CLI for
all tracker interactions so routing tests exercise the same surface as users.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from typing import Any

FROM_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] From (?P<sender>.*?): (?P<message>.*)$")
VIA_RE = re.compile(r"^(?P<name>.*?) \(via (?P<host>.*?)\)$")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def agent_name() -> str:
    return os.environ.get("AGENT_NAME") or os.environ.get("SUGGESTED_AGENT_NAME") or "unknown-agent"


def run(cmd: list[str], timeout: float = 20.0) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_seconds": round(time.time() - started, 3),
        }
    except Exception as e:
        return {
            "cmd": cmd,
            "returncode": 124,
            "stdout": "",
            "stderr": repr(e),
            "duration_seconds": round(time.time() - started, 3),
        }


def sender_to_target(sender: str) -> str:
    match = VIA_RE.match(sender.strip())
    if match:
        return f"{match.group('host')}/{match.group('name')}"
    return sender.strip()


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(item, sort_keys=True) + "\n")
        f.flush()


def read_new_commands(path: Path, offset: int) -> tuple[int, list[dict[str, Any]]]:
    if not path.exists():
        return offset, []
    with path.open() as f:
        f.seek(offset)
        lines = f.readlines()
        new_offset = f.tell()
    commands = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            commands.append(json.loads(line))
        except json.JSONDecodeError as e:
            commands.append({"op": "invalid", "raw": line, "error": str(e)})
    return new_offset, commands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command-dir", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--auto-reply", action="store_true")
    args = parser.parse_args()

    name = agent_name()
    broccoli = os.environ.get("BROCCOLI_E2E_BROCCOLI_BIN") or "broccoli-comms"
    command_file = Path(args.command_dir) / f"{name}.jsonl"
    log_path = Path(args.log_dir) / f"{name}.jsonl"
    text_log_path = Path(args.log_dir) / f"{name}.log"

    Path(args.command_dir).mkdir(parents=True, exist_ok=True)
    Path(args.log_dir).mkdir(parents=True, exist_ok=True)

    banner = {
        "event": "agent_started",
        "time": now(),
        "agent_name": name,
        "agent_id": os.environ.get("AGENT_ID"),
        "agent_uuid": os.environ.get("AGENT_UUID"),
        "hostname": os.environ.get("AGENT_TRACKER_HOSTNAME"),
        "tracker_socket": os.environ.get("AGENT_TRACKER_SOCKET"),
        "broccoli": broccoli,
        "pid": os.getpid(),
    }
    append_jsonl(log_path, banner)
    with text_log_path.open("a") as text_log:
        print(f"E2E_AGENT_READY {json.dumps(banner, sort_keys=True)}", flush=True)
        text_log.write(f"E2E_AGENT_READY {json.dumps(banner, sort_keys=True)}\n")
        text_log.flush()

        seen_inbox_lines: set[str] = set()
        offset = 0
        while True:
            offset, commands = read_new_commands(command_file, offset)
            for command in commands:
                event = {"event": "command_received", "time": now(), "agent_name": name, "command": command}
                append_jsonl(log_path, event)
                text_log.write(f"E2E_COMMAND {json.dumps(event, sort_keys=True)}\n")
                text_log.flush()
                if command.get("op") == "send":
                    target = str(command.get("target", ""))
                    message = str(command.get("message", ""))
                    result = run([broccoli, "agent-tracker", "send-message", target, message], timeout=30)
                    append_jsonl(log_path, {"event": "send_result", "time": now(), "agent_name": name, "target": target, "message": message, "result": result})
                    text_log.write(f"E2E_SEND_RESULT {json.dumps({'target': target, 'message': message, 'result': result}, sort_keys=True)}\n")
                    text_log.flush()
                elif command.get("op") == "stop":
                    append_jsonl(log_path, {"event": "agent_stopping", "time": now(), "agent_name": name})
                    return 0

            inbox = run([broccoli, "agent-tracker", "read-inbox", "--last", "50"], timeout=30)
            if inbox["returncode"] == 0:
                for line in inbox["stdout"].splitlines():
                    if not line or line in seen_inbox_lines or line.startswith("No messages"):
                        continue
                    seen_inbox_lines.add(line)
                    parsed = {"raw": line}
                    match = FROM_RE.match(line)
                    if match:
                        parsed.update(match.groupdict())
                    item = {"event": "inbox_observed", "time": now(), "agent_name": name, **parsed}
                    append_jsonl(log_path, item)
                    text_log.write(f"E2E_INBOX {json.dumps(item, sort_keys=True)}\n")
                    text_log.flush()
                    if args.auto_reply and match:
                        reply_target = sender_to_target(match.group("sender"))
                        reply_message = f"E2E_AUTO_REPLY from={name} to={reply_target} observed={shlex.quote(match.group('message'))}"
                        result = run([broccoli, "agent-tracker", "send-message", reply_target, reply_message], timeout=30)
                        append_jsonl(log_path, {"event": "auto_reply_result", "time": now(), "agent_name": name, "target": reply_target, "message": reply_message, "result": result})
                        text_log.write(f"E2E_AUTO_REPLY_RESULT {json.dumps({'target': reply_target, 'result': result}, sort_keys=True)}\n")
                        text_log.flush()
            else:
                append_jsonl(log_path, {"event": "read_inbox_error", "time": now(), "agent_name": name, "result": inbox})
            time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
