#!/usr/bin/env python3
"""Safe tmux pipe-pane sidecar for local pane output ingestion.

The sidecar reads pane bytes from stdin, decodes UTF-8 safely across read
boundaries, and submits bounded chunks to the tracker's internal pane_output RPC.
It deliberately logs only metadata, never raw pane contents or pipe tokens.
"""

from __future__ import annotations

import argparse
import codecs
import json
import logging
import os
import socket
import sys
import time
from collections.abc import Iterable, Iterator

import config

RUNTIME_DIR = str(config.get_base_runtime_dir())
SOCKET_PATH = os.environ.get("AGENT_TRACKER_SOCKET") or config.get("paths", "agent_tracker_socket") or os.path.join(RUNTIME_DIR, "agent-tracker.sock")
READ_SIZE = int(os.environ.get("AGENT_PIPE_READER_READ_SIZE", "4096"))
MAX_CHUNK_BYTES = int(os.environ.get("AGENT_PIPE_READER_MAX_CHUNK_BYTES", "8192"))
MAX_BUFFER_BYTES = int(os.environ.get("AGENT_PIPE_READER_MAX_BUFFER_BYTES", "65536"))
RPC_TIMEOUT_SECONDS = float(os.environ.get("AGENT_PIPE_READER_RPC_TIMEOUT", "2.0"))
RPC_RETRIES = int(os.environ.get("AGENT_PIPE_READER_RPC_RETRIES", "3"))
RPC_BACKOFF_SECONDS = float(os.environ.get("AGENT_PIPE_READER_RPC_BACKOFF", "0.05"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)


def _take_prefix_by_bytes(text: str, max_bytes: int) -> tuple[str, str]:
    """Splits text without cutting a UTF-8 code point."""
    if len(text.encode("utf-8")) <= max_bytes:
        return text, ""
    total = 0
    cut = 0
    for idx, char in enumerate(text):
        char_len = len(char.encode("utf-8"))
        if total + char_len > max_bytes:
            break
        total += char_len
        cut = idx + 1
    if cut == 0:
        # max_bytes is smaller than one code point; drop that single code point
        # rather than blocking forever on an un-emittable character.
        return "", text[1:]
    return text[:cut], text[cut:]


def iter_utf8_chunks(byte_chunks: Iterable[bytes], max_chunk_bytes: int = MAX_CHUNK_BYTES, max_buffer_bytes: int = MAX_BUFFER_BYTES) -> Iterator[str]:
    """Decodes byte chunks incrementally and yields UTF-8-safe capped strings."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""

    def emit_available(force: bool = False) -> Iterator[str]:
        nonlocal pending
        while pending and (force or len(pending.encode("utf-8")) >= max_chunk_bytes):
            chunk, pending = _take_prefix_by_bytes(pending, max_chunk_bytes)
            if chunk:
                yield chunk
            else:
                logging.warning("dropped oversized single code point from pipe reader buffer")

    for raw in byte_chunks:
        if not raw:
            continue
        pending += decoder.decode(raw, final=False)
        if len(pending.encode("utf-8")) > max_buffer_bytes:
            keep = ""
            for char in reversed(pending):
                if len((char + keep).encode("utf-8")) > max_chunk_bytes:
                    break
                keep = char + keep
            logging.warning("pipe reader buffer exceeded cap; dropping buffered pane output metadata_only bytes=%s", len(pending.encode("utf-8")))
            pending = keep
        yield from emit_available(force=False)

    pending += decoder.decode(b"", final=True)
    yield from emit_available(force=True)


def read_stdin_chunks(stdin_buffer, read_size: int = READ_SIZE) -> Iterator[bytes]:
    while True:
        data = stdin_buffer.read(read_size)
        if not data:
            break
        yield data


def call_rpc(socket_path: str, method: str, params: dict, timeout: float = RPC_TIMEOUT_SECONDS) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(socket_path)
        request = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        sock.sendall(json.dumps(request).encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        response = json.loads(b"".join(chunks).decode("utf-8"))
        if "error" in response:
            raise RuntimeError(response["error"].get("message", "pane_output RPC failed"))
        return response.get("result") or {}
    finally:
        sock.close()


def submit_pane_output(socket_path: str, payload: dict, retries: int = RPC_RETRIES, backoff: float = RPC_BACKOFF_SECONDS) -> bool:
    safe = {k: payload.get(k) for k in ("agent_id", "tmux_pane", "pipe_instance_id", "seq")}
    safe["chunk_bytes"] = len(str(payload.get("chunk", "")).encode("utf-8"))
    for attempt in range(max(1, retries)):
        try:
            call_rpc(socket_path, "pane_output", payload)
            return True
        except Exception as exc:
            if attempt >= max(1, retries) - 1:
                logging.warning("dropping pane_output after RPC retries metadata=%s error=%s", safe, exc)
                return False
            logging.info("pane_output RPC unavailable; retrying metadata=%s attempt=%s", safe, attempt + 1)
            time.sleep(backoff * (2 ** attempt))
    return False


def run_reader(args, stdin_buffer=None) -> int:
    stdin_buffer = stdin_buffer or sys.stdin.buffer
    seq = 0
    for chunk in iter_utf8_chunks(read_stdin_chunks(stdin_buffer, args.read_size), args.max_chunk_bytes, args.max_buffer_bytes):
        seq += 1
        payload = {
            "agent_id": args.agent_id,
            "tmux_pane": args.tmux_pane,
            "pipe_instance_id": args.pipe_instance_id,
            "pipe_token": args.pipe_token,
            "seq": seq,
            "chunk": chunk,
            "timestamp": time.time(),
        }
        submit_pane_output(args.socket, payload, retries=args.retries, backoff=args.backoff)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Broccoli Comms tmux pane output pipe reader")
    parser.add_argument("--socket", default=SOCKET_PATH)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--tmux-pane", required=True)
    parser.add_argument("--pipe-instance-id", required=True)
    parser.add_argument("--pipe-token", required=True)
    parser.add_argument("--read-size", type=int, default=READ_SIZE)
    parser.add_argument("--max-chunk-bytes", type=int, default=MAX_CHUNK_BYTES)
    parser.add_argument("--max-buffer-bytes", type=int, default=MAX_BUFFER_BYTES)
    parser.add_argument("--retries", type=int, default=RPC_RETRIES)
    parser.add_argument("--backoff", type=float, default=RPC_BACKOFF_SECONDS)
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_reader(args)


if __name__ == "__main__":
    raise SystemExit(main())
