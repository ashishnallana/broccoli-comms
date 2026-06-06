"""Pure parser pipeline for authenticated local pane output chunks.

The parser consumes already-authenticated pane-output text and emits normalized,
local-only output events plus strictly validated state patches. It never includes
raw pane chunks in emitted events.
"""

from __future__ import annotations

import json
import re
import time
from copy import deepcopy
from typing import Any

STRUCTURED_PREFIX = "@@BROCCOLI_EVENT@@"
MAX_BUFFER_CHARS = 8192
MAX_EVENT_TYPE_LEN = 64
MAX_PAYLOAD_STRING = 500
MAX_CURRENT_TASK = 200
MAX_PERMISSION_PROMPT = 500
HEURISTIC_DEBOUNCE_SECONDS = 5.0

STATUS_VALUES = {"idle", "working", "waiting", "error", "ready", "unknown", "spawning"}
STATE_PATCH_ALLOWLIST = {"status", "waiting_approval", "last_activity", "last_permission_prompt", "current_task"}
FORBIDDEN_KEY_TOKENS = {"raw", "chunk", "output", "pane", "pipe", "token", "hash", "sha256"}
FORBIDDEN_KEY_NORMALIZED = {
    "raw",
    "rawoutput",
    "rawchunk",
    "chunk",
    "output",
    "paneoutput",
    "panechunk",
    "pipetoken",
    "token",
    "pipetokenhash",
    "tokenhash",
    "pipetokensha256",
}
_EVENT_TYPE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_STATUS_HINT_RE = re.compile(r"(?:^|\b)status\s*[:=]\s*(idle|working|waiting|ready|error|unknown)\b", re.IGNORECASE)


def _normalize_key(key: str) -> str:
    # Convert snake/kebab/camel/mixed case variants to a compact lowercase form.
    return re.sub(r"[^a-z0-9]", "", key).lower()


def _key_tokens(key: str) -> set[str]:
    return {token for token in re.split(r"[^A-Za-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)) if token}


def _is_forbidden_event_key(key: str) -> bool:
    normalized = _normalize_key(key)
    if normalized in FORBIDDEN_KEY_NORMALIZED:
        return True
    tokens = {token.lower() for token in _key_tokens(key)}
    if tokens & {"token"}:
        return True
    if "raw" in tokens and (tokens & {"output", "chunk"}):
        return True
    if "pane" in tokens and (tokens & {"output", "chunk"}):
        return True
    if "pipe" in tokens and "token" in tokens:
        return True
    if "hash" in tokens and (tokens & {"token", "sha256"}):
        return True
    return False


class ParserValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _err(code: str) -> ParserValidationError:
    return ParserValidationError(code)


def safe_error_code(exc: Exception) -> str:
    if isinstance(exc, ParserValidationError):
        return exc.code
    return "parser_error"


def initial_parser_state() -> dict:
    return {"buffer": "", "last_heuristic_at": {}}


def _bounded_string(value: Any, max_len: int, field: str) -> str:
    if not isinstance(value, str):
        raise _err("invalid_string")
    if len(value) > max_len:
        raise _err("string_too_long")
    if any(ord(ch) < 32 and ch not in "\t" for ch in value):
        raise _err("string_contains_control")
    return value


def _sanitize_json_value(value: Any, max_string: int = MAX_PAYLOAD_STRING) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_string(value, max_string, "payload string")
    if isinstance(value, list):
        if len(value) > 20:
            raise _err("payload_list_too_long")
        return [_sanitize_json_value(item, max_string) for item in value]
    if isinstance(value, dict):
        if len(value) > 20:
            raise _err("payload_object_too_large")
        sanitized = {}
        for key, item in value.items():
            key = _bounded_string(key, 80, "payload key")
            if _is_forbidden_event_key(key):
                raise _err("forbidden_event_key")
            sanitized[key] = _sanitize_json_value(item, max_string)
        return sanitized
    raise _err("payload_unsupported_type")


def validate_state_patch(patch: Any, now: float | None = None) -> dict:
    if patch is None:
        return {}
    if not isinstance(patch, dict):
        raise _err("invalid_state_patch")
    now = time.time() if now is None else float(now)
    validated = {}
    for key, value in patch.items():
        if key not in STATE_PATCH_ALLOWLIST:
            raise _err("state_patch_field_not_allowed")
        if key == "status":
            if value not in STATUS_VALUES:
                raise _err("invalid_status")
            validated[key] = value
        elif key == "waiting_approval":
            if not isinstance(value, bool):
                raise _err("invalid_waiting_approval")
            validated[key] = value
        elif key == "last_activity":
            if value not in (True, "now", None):
                raise _err("invalid_last_activity")
            validated[key] = now
        elif key == "last_permission_prompt":
            validated[key] = _bounded_string(value, MAX_PERMISSION_PROMPT, key)
        elif key == "current_task":
            validated[key] = _bounded_string(value, MAX_CURRENT_TASK, key)
    return validated


def validate_output_event(raw: Any, *, agent_id: str, agent_name: str | None, now: float | None = None) -> dict:
    if not isinstance(raw, dict):
        raise _err("invalid_event")
    event_type = raw.get("event_type")
    if not isinstance(event_type, str) or not event_type or len(event_type) > MAX_EVENT_TYPE_LEN or not _EVENT_TYPE_RE.match(event_type):
        raise _err("invalid_event_type")
    confidence = raw.get("confidence", 1.0)
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        raise _err("invalid_confidence")
    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise _err("invalid_payload")
    sanitized_payload = _sanitize_json_value(payload)
    state_patch = validate_state_patch(raw.get("state_patch"), now=now)

    normalized = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "source": "pipe-pane",
        "event_type": event_type,
        "confidence": float(confidence),
        "payload": sanitized_payload,
    }
    if state_patch:
        normalized["state_patch"] = state_patch
    return normalized


def parse_structured_line(line: str, *, agent_id: str, agent_name: str | None, now: float | None = None) -> dict | None:
    if not line.startswith(STRUCTURED_PREFIX):
        return None
    raw_json = line[len(STRUCTURED_PREFIX):].strip()
    try:
        raw_event = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise _err("malformed_structured_json") from exc
    return validate_output_event(raw_event, agent_id=agent_id, agent_name=agent_name, now=now)


def _debounced(parser_state: dict, key: str, now: float) -> bool:
    last = (parser_state.get("last_heuristic_at") or {}).get(key)
    return last is not None and now - float(last) < HEURISTIC_DEBOUNCE_SECONDS


def _mark_heuristic(parser_state: dict, key: str, now: float) -> None:
    parser_state.setdefault("last_heuristic_at", {})[key] = now


def parse_heuristic_line(line: str, *, agent_id: str, agent_name: str | None, parser_state: dict, now: float) -> list[dict]:
    lowered = line.lower()
    events = []

    status_match = _STATUS_HINT_RE.search(line)
    if status_match and not _debounced(parser_state, "status", now):
        status = status_match.group(1).lower()
        _mark_heuristic(parser_state, "status", now)
        events.append(validate_output_event({
            "event_type": "status_hint",
            "confidence": 0.65,
            "payload": {"status": status, "parser": "status_hint"},
            "state_patch": {"status": status, "last_activity": True},
        }, agent_id=agent_id, agent_name=agent_name, now=now))

    permission_hint = "permission" in lowered and any(word in lowered for word in ("approval", "approve", "allow", "denied"))
    if permission_hint and not _debounced(parser_state, "permission", now):
        _mark_heuristic(parser_state, "permission", now)
        events.append(validate_output_event({
            "event_type": "permission_hint",
            "confidence": 0.7,
            "payload": {"hint": "permission_prompt"},
            "state_patch": {
                "status": "waiting",
                "waiting_approval": True,
                "last_activity": True,
                "last_permission_prompt": "permission prompt detected",
            },
        }, agent_id=agent_id, agent_name=agent_name, now=now))
    return events


def parse_chunk(
    parser_state: dict | None,
    chunk: str,
    *,
    agent_id: str,
    agent_name: str | None,
    pipe_instance_id: str,
    now: float | None = None,
) -> tuple[dict, list[dict], list[str]]:
    """Consumes a text chunk and returns (new_state, normalized_events, errors)."""
    if not isinstance(chunk, str):
        raise _err("invalid_chunk")
    now = time.time() if now is None else float(now)
    next_state = deepcopy(parser_state or initial_parser_state())
    if next_state.get("pipe_instance_id") != pipe_instance_id:
        next_state["buffer"] = ""
        next_state["last_heuristic_at"] = {}
        next_state["pipe_instance_id"] = pipe_instance_id

    combined = (next_state.get("buffer") or "") + chunk
    if len(combined) > MAX_BUFFER_CHARS:
        combined = combined[-MAX_BUFFER_CHARS:]
    lines = combined.splitlines(keepends=True)
    complete_lines = []
    buffer = ""
    for item in lines:
        if item.endswith("\n") or item.endswith("\r"):
            complete_lines.append(item.rstrip("\r\n"))
        else:
            buffer = item
    next_state["buffer"] = buffer

    events = []
    errors = []
    for line in complete_lines:
        if not line:
            continue
        try:
            if line.startswith(STRUCTURED_PREFIX):
                event = parse_structured_line(line, agent_id=agent_id, agent_name=agent_name, now=now)
                if event:
                    events.append(event)
                continue
            events.extend(parse_heuristic_line(line, agent_id=agent_id, agent_name=agent_name, parser_state=next_state, now=now))
        except ParserValidationError as exc:
            errors.append(str(exc))
    return next_state, events, errors
