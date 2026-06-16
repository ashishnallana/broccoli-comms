import json
import logging
import os
import threading
from collections.abc import Iterable

import config
import registry_client

JOURNAL_PATH = os.path.join(str(config.get_base_cache_dir() / "agent-tracker"), "message_journal.jsonl")
SCHEMA_VERSION = 1
_journal_lock = threading.Lock()


def _normalize_swarms(swarms: object) -> list[dict[str, str]]:
    if not isinstance(swarms, list):
        return []
    normalized = []
    for item in swarms:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        role = item.get("role")
        if not isinstance(name, str) or not name:
            continue
        if role not in {"main", "subagent"}:
            continue
        normalized.append({"name": name, "role": role})
    return normalized


def _membership_by_swarm(agent_info: dict | None) -> dict[str, str]:
    return {item["name"]: item["role"] for item in _normalize_swarms((agent_info or {}).get("swarms"))}


def _context_swarm_names(swarm_context: object) -> set[str]:
    if isinstance(swarm_context, str) and swarm_context:
        return {swarm_context}
    if isinstance(swarm_context, dict):
        name = swarm_context.get("name") or swarm_context.get("swarm")
        return {name} if isinstance(name, str) and name else set()
    if isinstance(swarm_context, Iterable) and not isinstance(swarm_context, (str, bytes, dict)):
        names = set()
        for item in swarm_context:
            names.update(_context_swarm_names(item))
        return names
    return set()


def _explicit_swarm_names(swarms: object) -> set[str]:
    names = set()
    if isinstance(swarms, list):
        for item in swarms:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name"):
                names.add(item["name"])
    return names


def classify_swarms(sender_info: dict | None, recipient_info: dict | None, swarm_context: object = None, explicit_swarms: object = None) -> tuple[list[dict], dict]:
    """Classify a message into swarm timelines from sender/recipient membership.

    The primary rule is the intersection of sender and recipient swarm memberships.
    Optional swarm_context is accepted for future user->swarm-main send flows; it is
    only used when the recipient is a member and the sender has no local swarm
    membership to intersect.
    """
    sender_memberships = _membership_by_swarm(sender_info)
    recipient_memberships = _membership_by_swarm(recipient_info)

    swarm_names = set(sender_memberships).intersection(recipient_memberships)
    if not swarm_names and not sender_memberships:
        swarm_names.update(_context_swarm_names(swarm_context).intersection(recipient_memberships))
    if not swarm_names:
        swarm_names.update(_explicit_swarm_names(explicit_swarms))

    ordered_names = sorted(swarm_names)
    swarms = [{"name": name} for name in ordered_names]
    snapshot = {
        name: {
            "sender_role": sender_memberships.get(name),
            "recipient_role": recipient_memberships.get(name),
        }
        for name in ordered_names
    }
    return swarms, snapshot


def _event_message_id(event: dict) -> str | None:
    message_id = event.get("message_id")
    return message_id if isinstance(message_id, str) and message_id else None


def append_event(event: dict, journal_path: str | None = None) -> bool:
    """Append an event to the JSONL journal, de-duped by message_id.

    Returns True when a new row was appended, False when skipped because the row
    was duplicate or did not have a usable message_id.
    """
    path = journal_path or JOURNAL_PATH
    message_id = _event_message_id(event)
    if not message_id:
        return False

    with _journal_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            if json.loads(line).get("message_id") == message_id:
                                return False
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logging.warning("failed to scan message journal for dedupe %s: %s", path, e)

        try:
            with open(path, "a") as f:
                f.write(json.dumps(event, sort_keys=True) + "\n")
            return True
        except Exception as e:
            logging.warning("failed to append message journal %s: %s", path, e)
            return False


def build_message_event(
    sender_name: str,
    recipient_name: str,
    msg_obj: dict,
    *,
    sender_info: dict | None = None,
    recipient_info: dict | None = None,
    swarm_context: object = None,
    direction: str = "local",
    source: str = "deliver_local_message",
) -> dict | None:
    swarms, snapshot = classify_swarms(sender_info, recipient_info, swarm_context, msg_obj.get("swarms"))
    if not swarms:
        return None

    return {
        "schema_version": SCHEMA_VERSION,
        "message_id": msg_obj.get("message_id"),
        "delivery_id": msg_obj.get("delivery_id"),
        "timestamp": msg_obj.get("timestamp"),
        "sender": {
            "name": sender_name,
            "agent_id": (sender_info or {}).get("agent_id") or msg_obj.get("sender_agent_id"),
            "hostname": (sender_info or {}).get("hostname") or msg_obj.get("sender_hostname") or registry_client.HOSTNAME,
            "tracker_id": msg_obj.get("sender_tracker_id") or (sender_info or {}).get("tracker_id") or registry_client.TRACKER_ID,
        },
        "recipient": {
            "name": recipient_name,
            "agent_id": (recipient_info or {}).get("agent_id") or msg_obj.get("recipient_agent_id"),
            "hostname": (recipient_info or {}).get("hostname") or msg_obj.get("recipient_hostname") or registry_client.HOSTNAME,
            "tracker_id": (recipient_info or {}).get("tracker_id") or msg_obj.get("recipient_tracker_id") or registry_client.TRACKER_ID,
        },
        "message": msg_obj.get("message"),
        "attachments": msg_obj.get("attachments") or [],
        "swarms": swarms,
        "membership_snapshot": msg_obj.get("membership_snapshot") if isinstance(msg_obj.get("membership_snapshot"), dict) else snapshot,
        "direction": direction,
        "source": source,
    }


def record_local_message(
    sender_name: str,
    recipient_name: str,
    msg_obj: dict,
    *,
    sender_info: dict | None = None,
    recipient_info: dict | None = None,
    swarm_context: object = None,
    source: str = "deliver_local_message",
    direction: str = "local",
    journal_path: str | None = None,
) -> dict | None:
    event = build_message_event(
        sender_name,
        recipient_name,
        msg_obj,
        sender_info=sender_info,
        recipient_info=recipient_info,
        swarm_context=swarm_context,
        direction=direction,
        source=source,
    )
    if not event:
        return None
    return event if append_event(event, journal_path=journal_path) else None


def to_registry_event(event: dict) -> dict:
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    recipient = event.get("recipient") if isinstance(event.get("recipient"), dict) else {}
    return {
        "schema_version": event.get("schema_version") or SCHEMA_VERSION,
        "message_id": event.get("message_id"),
        "delivery_id": event.get("delivery_id"),
        "timestamp": event.get("timestamp"),
        "sender_tracker_id": sender.get("tracker_id"),
        "sender_hostname": sender.get("hostname"),
        "sender_agent_id": sender.get("agent_id"),
        "sender_agent_name": sender.get("name"),
        "recipient_tracker_id": recipient.get("tracker_id"),
        "recipient_hostname": recipient.get("hostname"),
        "recipient_agent_id": recipient.get("agent_id"),
        "recipient_agent_name": recipient.get("name"),
        "swarms": event.get("swarms") or [],
        "message": event.get("message"),
        "attachments": event.get("attachments") or [],
        "membership_snapshot": event.get("membership_snapshot") or {},
        "direction": event.get("direction"),
        "source": event.get("source"),
    }


def read_events(journal_path: str | None = None) -> list[dict]:
    path = journal_path or JOURNAL_PATH
    if not os.path.exists(path):
        return []
    events = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
    except Exception as e:
        logging.warning("failed to read message journal %s: %s", path, e)
        return []
    return events


def _event_has_swarm(event: dict, swarm_name: str) -> bool:
    for item in event.get("swarms") or []:
        if isinstance(item, dict) and item.get("name") == swarm_name:
            return True
    return False


def _timeline_row(event: dict) -> dict:
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    recipient = event.get("recipient") if isinstance(event.get("recipient"), dict) else {}
    return {
        "message_id": event.get("message_id"),
        "sender": sender.get("name"),
        "sender_agent_id": sender.get("agent_id"),
        "sender_tracker_id": sender.get("tracker_id"),
        "recipient": recipient.get("name"),
        "recipient_agent_id": recipient.get("agent_id"),
        "recipient_tracker_id": recipient.get("tracker_id"),
        "sender_hostname": sender.get("hostname"),
        "recipient_hostname": recipient.get("hostname"),
        "timestamp": event.get("timestamp"),
        "message": event.get("message"),
        "attachments": event.get("attachments") or [],
        "swarms": event.get("swarms") or [],
        "membership_snapshot": event.get("membership_snapshot") or {},
        "direction": event.get("direction"),
        "journal_source": event.get("source"),
        "source": "message_journal",
    }


def registry_event_to_timeline_row(event: dict) -> dict:
    sender_name = event.get("sender_agent_name")
    sender_hostname = event.get("sender_hostname")
    recipient_name = event.get("recipient_agent_name")
    recipient_hostname = event.get("recipient_hostname")
    return {
        "message_id": event.get("message_id"),
        "sender": f"{sender_hostname}/{sender_name}" if sender_hostname and sender_name else sender_name,
        "sender_agent_id": event.get("sender_agent_id"),
        "sender_tracker_id": event.get("sender_tracker_id"),
        "recipient": f"{recipient_hostname}/{recipient_name}" if recipient_hostname and recipient_name else recipient_name,
        "recipient_agent_id": event.get("recipient_agent_id"),
        "recipient_tracker_id": event.get("recipient_tracker_id"),
        "timestamp": event.get("timestamp"),
        "message": event.get("message"),
        "attachments": event.get("attachments") or [],
        "swarms": event.get("swarms") or [],
        "membership_snapshot": event.get("membership_snapshot") or {},
        "direction": event.get("direction") or "registry",
        "source": "registry_message_event",
    }


def read_swarm_timeline(swarm_name: str, last_n: int = 200, journal_path: str | None = None) -> list[dict]:
    rows_by_id = {}
    rows_without_id = []
    for event in read_events(journal_path=journal_path):
        if not _event_has_swarm(event, swarm_name):
            continue
        row = _timeline_row(event)
        message_id = row.get("message_id")
        if message_id:
            rows_by_id[message_id] = row
        else:
            rows_without_id.append(row)
    rows = list(rows_by_id.values()) + rows_without_id
    rows.sort(key=lambda e: e.get("timestamp") or "")
    return rows[-last_n:]
