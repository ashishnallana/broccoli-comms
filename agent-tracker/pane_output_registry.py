"""Registry-safe pane-output event validation and normalization.

This module accepts only already-normalized parser events. It deliberately rejects
raw output, tokens, pipe metadata, tmux internals, cwd, aliases, swarms, and
arbitrary identity metadata before anything can be sent to or served by a
registry.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import pane_output_parser

SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 300
MAX_TTL_SECONDS = 3600
MAX_PAYLOAD_STRING = pane_output_parser.MAX_PAYLOAD_STRING
MAX_EVENT_TYPE_LEN = pane_output_parser.MAX_EVENT_TYPE_LEN
EVENT_TYPE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

DISALLOWED_TOP_LEVEL = {
    "raw", "raw_output", "rawOutput", "chunk", "output", "pane_output", "paneOutput",
    "pipe_token", "pipeToken", "token", "pipe_token_hash", "token_hash", "pipe_token_sha256",
    "pipe_instance_id", "pipe_tmux_pane", "tmux_pane", "tmux_socket", "pane", "socket",
    "cwd", "aliases", "swarms", "metadata", "arbitrary_metadata",
}


class RegistryEventValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _err(code: str) -> RegistryEventValidationError:
    return RegistryEventValidationError(code)


def safe_error_code(exc: Exception) -> str:
    if isinstance(exc, RegistryEventValidationError):
        return exc.code
    return "registry_pane_output_event_error"


def _is_forbidden_key(key: str) -> bool:
    return key in DISALLOWED_TOP_LEVEL or pane_output_parser._is_forbidden_event_key(key)


def _bounded_string(value: Any, max_len: int, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise _err(code)
    if len(value) > max_len:
        raise _err("string_too_long")
    if any(ord(ch) < 32 and ch not in "\t" for ch in value):
        raise _err("string_contains_control")
    return value


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_string(value, MAX_PAYLOAD_STRING, "invalid_string")
    if isinstance(value, list):
        if len(value) > 20:
            raise _err("payload_list_too_long")
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        if len(value) > 20:
            raise _err("payload_object_too_large")
        sanitized = {}
        for key, item in value.items():
            safe_key = _bounded_string(key, 80, "invalid_payload_key")
            if _is_forbidden_key(safe_key):
                raise _err("forbidden_event_key")
            sanitized[safe_key] = _sanitize_value(item)
        return sanitized
    raise _err("payload_unsupported_type")


def _sanitize_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise _err("invalid_payload")
    return _sanitize_value(payload)


def _sanitize_state_patch(patch: Any) -> dict:
    try:
        return pane_output_parser.validate_state_patch(patch or {})
    except pane_output_parser.ParserValidationError as exc:
        raise _err(pane_output_parser.safe_error_code(exc)) from exc


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def make_event_id(source_tracker_id: str, local_seq: int | str | None, agent_id: str, event_type: str, payload: dict) -> str:
    if local_seq is not None:
        key = f"{source_tracker_id}:{agent_id}:{local_seq}"
    else:
        key = f"{source_tracker_id}:{agent_id}:{event_type}:{_canonical_json(payload)}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"broccoli-pane-output-event:{key}"))


def from_local_event(local_event: dict, *, source_tracker_id: str, source_hostname: str, ttl_seconds: int | float = DEFAULT_TTL_SECONDS, now: float | None = None) -> dict:
    """Builds a registry-safe event from a local agent_output_event."""
    if not isinstance(local_event, dict):
        raise _err("invalid_event")
    for key in local_event:
        if _is_forbidden_key(str(key)):
            raise _err("forbidden_event_key")
    agent_id = _bounded_string(local_event.get("agent_id") or local_event.get("target_agent_id"), 128, "invalid_agent_id")
    agent_name = local_event.get("agent_name") or local_event.get("target_agent_name")
    if agent_name is not None:
        agent_name = _bounded_string(agent_name, 128, "invalid_agent_name")
    event_type = _bounded_string(local_event.get("event_type"), MAX_EVENT_TYPE_LEN, "invalid_event_type")
    if not EVENT_TYPE_RE.match(event_type):
        raise _err("invalid_event_type")
    confidence = local_event.get("confidence", 1.0)
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        raise _err("invalid_confidence")
    payload = _sanitize_payload(local_event.get("payload") or {})
    state_patch = _sanitize_state_patch(local_event.get("state_patch") or {})
    now = time.time() if now is None else float(now)
    ttl = max(1.0, min(float(ttl_seconds), float(MAX_TTL_SECONDS)))
    event_id = make_event_id(source_tracker_id, local_event.get("seq"), agent_id, event_type, payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "source_tracker_id": _bounded_string(source_tracker_id, 200, "invalid_source_tracker_id"),
        "source_hostname": _bounded_string(source_hostname, 200, "invalid_source_hostname"),
        "agent_id": agent_id,
        "agent_name": agent_name,
        "source": "pipe-pane",
        "event_type": event_type,
        "confidence": float(confidence),
        "payload": payload,
        "created_at": now,
        "expires_at": now + ttl,
        "ttl_seconds": ttl,
    }
    if state_patch:
        normalized["state_patch"] = state_patch
    return normalized


def validate_registry_event(event: dict, *, now: float | None = None) -> dict:
    """Validates a registry pane-output event without trusting its producer."""
    if not isinstance(event, dict):
        raise _err("invalid_event")
    for key in event:
        if _is_forbidden_key(str(key)):
            raise _err("forbidden_event_key")
    now = time.time() if now is None else float(now)
    created_at = float(event.get("created_at") or now)
    supplied_expires_at = float(event.get("expires_at") or (created_at + DEFAULT_TTL_SECONDS))
    requested_ttl = supplied_expires_at - created_at
    if requested_ttl <= 0:
        raise _err("invalid_expiry")
    ttl = max(1.0, min(requested_ttl, float(MAX_TTL_SECONDS)))
    expires_at = created_at + ttl
    if expires_at <= now:
        raise _err("event_expired")
    local = {
        "seq": None,
        "agent_id": event.get("agent_id"),
        "agent_name": event.get("agent_name"),
        "event_type": event.get("event_type"),
        "confidence": event.get("confidence", 1.0),
        "payload": event.get("payload") or {},
        "state_patch": event.get("state_patch") or {},
    }
    normalized = from_local_event(
        local,
        source_tracker_id=event.get("source_tracker_id"),
        source_hostname=event.get("source_hostname"),
        ttl_seconds=ttl,
        now=created_at,
    )
    supplied_event_id = _bounded_string(event.get("event_id"), 200, "invalid_event_id")
    normalized["event_id"] = supplied_event_id
    normalized["expires_at"] = expires_at
    normalized["ttl_seconds"] = ttl
    return normalized


def to_remote_observer_event(event: dict) -> dict:
    """Maps a registry event to the local observer agent_output_event shape."""
    normalized = validate_registry_event(event)
    target_agent_id = f"{normalized['source_hostname']}/{normalized['agent_id']}"
    target_agent_name = f"{normalized['source_hostname']}/{normalized.get('agent_name') or normalized['agent_id']}"
    observer = {
        "schema_version": SCHEMA_VERSION,
        "registry_event_id": normalized["event_id"],
        "source_tracker_id": normalized["source_tracker_id"],
        "source_hostname": normalized["source_hostname"],
        "agent_id": normalized["agent_id"],
        "agent_name": normalized.get("agent_name"),
        "target_agent_id": target_agent_id,
        "target_agent_name": target_agent_name,
        "source": "registry-pane-output",
        "event_type": normalized["event_type"],
        "confidence": normalized["confidence"],
        "payload": normalized["payload"],
        "created_at": normalized["created_at"],
        "expires_at": normalized["expires_at"],
    }
    if normalized.get("state_patch"):
        observer["state_patch"] = normalized["state_patch"]
    return observer
