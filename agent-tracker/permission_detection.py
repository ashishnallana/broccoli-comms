"""Config-driven blocked-agent detection for local tmux panes.

Phase 1 is deliberately detection-only: capture a small pane excerpt, match
configured words/phrases, and notify agent-communicator. It never sends keys,
never approves/denies, and never executes captured pane text.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import state
import tmux_util

DEFAULT_CAPTURE_LINES = 5
MAX_CAPTURE_LINES = 5
DEFAULT_SCAN_INTERVAL_SECONDS = 5.0
DEFAULT_NOTIFY_COOLDOWN_SECONDS = 300.0
DEFAULT_NOTIFY_TARGET = "agent-communicator"
DEFAULT_SENDER_NAME = "permission-monitor"
DEFAULT_MAX_EXCERPT_CHARS = 2000
MAX_RECENT_NOTIFICATIONS = 1000
CONFIG_ENV = "AGENT_TRACKER_DETECTION_CONFIG"


@dataclass(frozen=True)
class AgentDetectionConfig:
    enabled: bool
    capture_lines: int
    scan_interval_seconds: float
    notify_cooldown_seconds: float
    keyword_matches_required: int
    max_excerpt_chars: int
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class DetectionConfig:
    enabled: bool
    notify_target: str
    sender_name: str
    agents: dict[str, AgentDetectionConfig]
    default: AgentDetectionConfig | None


@dataclass(frozen=True)
class BlockingDetection:
    agent_name: str
    agent_id: str
    pane_id: str
    capture_lines: int
    matched_keywords: tuple[str, ...]
    excerpt: str
    fingerprint: str


_config_cache: tuple[str, float | None, DetectionConfig] | None = None
_last_scan_by_agent: dict[str, float] = {}
_recent_notifications: dict[str, float] = {}


def detection_config_path() -> str:
    override = os.environ.get(CONFIG_ENV)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(config_home, "agent-tracker", "detection.json")


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_int(value: Any, default: int, minimum: int, maximum: int | None = None) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        coerced = default
    coerced = max(minimum, coerced)
    if maximum is not None:
        coerced = min(maximum, coerced)
    return coerced


def _coerce_float(value: Any, default: float, minimum: float) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        coerced = default
    return max(minimum, coerced)


def _coerce_keywords(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    keywords = []
    seen = set()
    for raw in value:
        if not isinstance(raw, str):
            continue
        keyword = " ".join(raw.lower().split())
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(keywords)


def _agent_config(raw: dict[str, Any], inherited: AgentDetectionConfig | None = None, *, agent_entry: bool = False) -> AgentDetectionConfig:
    inherited_keywords = inherited.keywords if inherited else ()
    explicit_keywords = _coerce_keywords(raw.get("keywords"))
    keywords = explicit_keywords or inherited_keywords
    required_default = inherited.keyword_matches_required if inherited else 1
    required = _coerce_int(raw.get("keyword_matches_required"), required_default, 1)
    if keywords:
        required = min(required, len(keywords))
    default_enabled = inherited.enabled if inherited else False
    if agent_entry and "enabled" not in raw and explicit_keywords:
        default_enabled = True
    return AgentDetectionConfig(
        enabled=_coerce_bool(raw.get("enabled"), default_enabled),
        capture_lines=_coerce_int(raw.get("capture_lines"), inherited.capture_lines if inherited else DEFAULT_CAPTURE_LINES, 1, MAX_CAPTURE_LINES),
        scan_interval_seconds=_coerce_float(raw.get("scan_interval_seconds"), inherited.scan_interval_seconds if inherited else DEFAULT_SCAN_INTERVAL_SECONDS, 1.0),
        notify_cooldown_seconds=_coerce_float(raw.get("notify_cooldown_seconds"), inherited.notify_cooldown_seconds if inherited else DEFAULT_NOTIFY_COOLDOWN_SECONDS, 0.0),
        keyword_matches_required=required,
        max_excerpt_chars=_coerce_int(raw.get("max_excerpt_chars"), inherited.max_excerpt_chars if inherited else DEFAULT_MAX_EXCERPT_CHARS, 200, 4000),
        keywords=keywords,
    )


def _load_config_uncached(path: str) -> DetectionConfig:
    if not os.path.exists(path):
        return DetectionConfig(enabled=False, notify_target=DEFAULT_NOTIFY_TARGET, sender_name=DEFAULT_SENDER_NAME, agents={}, default=None)
    try:
        with open(path, "r") as f:
            raw = json.load(f)
    except Exception as e:
        logging.warning("Failed to read detection config %s: %s", path, e)
        return DetectionConfig(enabled=False, notify_target=DEFAULT_NOTIFY_TARGET, sender_name=DEFAULT_SENDER_NAME, agents={}, default=None)
    if not isinstance(raw, dict):
        logging.warning("Detection config %s must be a JSON object", path)
        return DetectionConfig(enabled=False, notify_target=DEFAULT_NOTIFY_TARGET, sender_name=DEFAULT_SENDER_NAME, agents={}, default=None)

    default_raw = raw.get("default") if isinstance(raw.get("default"), dict) else {}
    default_cfg = _agent_config(default_raw)
    agents_raw = raw.get("agents") if isinstance(raw.get("agents"), dict) else {}
    agents = {
        str(name): _agent_config(agent_raw if isinstance(agent_raw, dict) else {}, default_cfg, agent_entry=True)
        for name, agent_raw in agents_raw.items()
    }
    notify_target = str(raw.get("notify_target") or DEFAULT_NOTIFY_TARGET).strip() or DEFAULT_NOTIFY_TARGET
    sender_name = str(raw.get("sender_name") or DEFAULT_SENDER_NAME).strip() or DEFAULT_SENDER_NAME
    return DetectionConfig(
        enabled=_coerce_bool(raw.get("enabled"), True),
        notify_target=notify_target,
        sender_name=sender_name,
        agents=agents,
        default=default_cfg,
    )


def load_detection_config() -> DetectionConfig:
    """Loads detection.json, caching by path/mtime so config edits are picked up."""
    global _config_cache
    path = detection_config_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    if _config_cache and _config_cache[0] == path and _config_cache[1] == mtime:
        return _config_cache[2]
    cfg = _load_config_uncached(path)
    _config_cache = (path, mtime, cfg)
    return cfg


def agent_detection_config(config: DetectionConfig, agent_name: str) -> AgentDetectionConfig | None:
    if not config.enabled:
        return None
    return config.agents.get(agent_name) or config.default


def normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def detect_blocking_prompt(agent_name: str, info: dict[str, Any], pane_text: str, cfg: AgentDetectionConfig) -> BlockingDetection | None:
    if not cfg.enabled or not cfg.keywords:
        return None
    normalized = normalize_text(pane_text)
    matched = tuple(keyword for keyword in cfg.keywords if keyword in normalized)
    if len(matched) < cfg.keyword_matches_required:
        return None
    excerpt = (pane_text or "").strip()
    if len(excerpt) > cfg.max_excerpt_chars:
        excerpt = excerpt[-cfg.max_excerpt_chars:]
    pane_id = str(info.get("tmux_pane") or "")
    agent_id = str(info.get("agent_id") or info.get("uuid") or agent_name)
    fingerprint_material = "\0".join([agent_id, pane_id, normalize_text(excerpt), ",".join(matched)])
    fingerprint = hashlib.sha256(fingerprint_material.encode()).hexdigest()
    return BlockingDetection(
        agent_name=agent_name,
        agent_id=agent_id,
        pane_id=pane_id,
        capture_lines=cfg.capture_lines,
        matched_keywords=matched,
        excerpt=excerpt,
        fingerprint=fingerprint,
    )


def _format_detection_message(detection: BlockingDetection) -> str:
    matched = "\n".join(f"- {keyword}" for keyword in detection.matched_keywords)
    return (
        f"Agent `{detection.agent_name}` appears blocked on a permission/approval prompt.\n\n"
        f"Pane: `{detection.pane_id}`\n"
        f"Captured with `capture-pane` last {detection.capture_lines} lines.\n\n"
        f"Matched keywords:\n{matched}\n\n"
        f"Recent capture-pane output:\n\n"
        f"```text\n{detection.excerpt}\n```\n\n"
        f"Please inspect the pane and use `/text` or `/keys` to unblock the agent manually."
    )


def _send_detection_notification(config: DetectionConfig, detection: BlockingDetection) -> None:
    # Import lazily to avoid a module import cycle at daemon startup.
    import rpc_handler

    if not state.get_agent(config.notify_target):
        rpc_handler.handle_ensure_mailbox({"agent_name": config.notify_target})
    rpc_handler.handle_send_message({
        "agent_name": config.notify_target,
        "sender_name": config.sender_name,
        "message": _format_detection_message(detection),
    })


def _should_skip_agent(agent_name: str, info: dict[str, Any], notify_target: str) -> bool:
    if agent_name == notify_target:
        return True
    if info.get("is_mailbox"):
        return True
    if not info.get("tmux_pane"):
        return True
    return False


def detection_monitor_once(now: float | None = None) -> int:
    """Runs one detection pass. Returns number of notifications sent."""
    now = now if now is not None else time.time()
    config = load_detection_config()
    if not config.enabled:
        return 0

    sent = 0
    for agent_name, info in state.get_all_agents().items():
        if _should_skip_agent(agent_name, info, config.notify_target):
            continue
        agent_cfg = agent_detection_config(config, agent_name)
        if not agent_cfg or not agent_cfg.enabled or not agent_cfg.keywords:
            continue

        last_scan = _last_scan_by_agent.get(agent_name, 0.0)
        if now - last_scan < agent_cfg.scan_interval_seconds:
            continue
        _last_scan_by_agent[agent_name] = now

        try:
            pane_text = tmux_util.capture_pane_visible_text(
                info.get("tmux_pane"),
                last_lines=agent_cfg.capture_lines,
                socket_path=info.get("tmux_socket"),
                include_ansi=False,
            )
        except Exception as e:
            logging.debug("Skipping detection for %s; pane capture failed: %s", agent_name, e)
            continue

        detection = detect_blocking_prompt(agent_name, info, pane_text, agent_cfg)
        if not detection:
            continue

        last_notified = _recent_notifications.get(detection.fingerprint, 0.0)
        if now - last_notified < agent_cfg.notify_cooldown_seconds:
            continue

        _sweep_recent_notifications(now, agent_cfg.notify_cooldown_seconds)
        try:
            _send_detection_notification(config, detection)
            _recent_notifications[detection.fingerprint] = now
            sent += 1
            logging.info("Permission/blocking prompt detected for %s pane=%s fingerprint=%s", agent_name, detection.pane_id, detection.fingerprint[:12])
        except Exception as e:
            logging.warning("Failed to notify %s about blocked agent %s: %s", config.notify_target, agent_name, e)
    return sent


def _sweep_recent_notifications(now: float, cooldown: float) -> None:
    if len(_recent_notifications) <= MAX_RECENT_NOTIFICATIONS:
        return
    cutoff = now - max(cooldown, DEFAULT_NOTIFY_COOLDOWN_SECONDS)
    for fingerprint, timestamp in list(_recent_notifications.items()):
        if timestamp < cutoff:
            _recent_notifications.pop(fingerprint, None)
    if len(_recent_notifications) > MAX_RECENT_NOTIFICATIONS:
        oldest = sorted(_recent_notifications, key=_recent_notifications.get)
        for fingerprint in oldest[: len(_recent_notifications) - MAX_RECENT_NOTIFICATIONS]:
            _recent_notifications.pop(fingerprint, None)


def background_detection_monitor() -> None:
    """Background loop for Phase 1 detection-only permission monitoring."""
    logging.info("Starting permission/blocking detection monitor; config=%s", detection_config_path())
    while True:
        try:
            detection_monitor_once()
        except Exception as e:
            logging.warning("Permission/blocking detection pass failed: %s", e)
        time.sleep(1.0)


_SAMPLE_CONFIG = {
    "version": 1,
    "enabled": True,
    "notify_target": "agent-communicator",
    "default": {
        "enabled": False,
        "capture_lines": 5,
        "scan_interval_seconds": 5,
        "notify_cooldown_seconds": 300,
        "keyword_matches_required": 2,
        "keywords": ["permission", "approve", "allow", "blocked"],
    },
    "agents": {
        "claude-1": {
            "enabled": True,
            "capture_lines": 5,
            "scan_interval_seconds": 3,
            "notify_cooldown_seconds": 300,
            "keyword_matches_required": 2,
            "keywords": ["wants to use bash", "do you want to allow", "allow this command", "yes", "no"],
        },
        "codex-1": {
            "enabled": True,
            "capture_lines": 5,
            "scan_interval_seconds": 3,
            "notify_cooldown_seconds": 300,
            "keyword_matches_required": 2,
            "keywords": ["approve", "allow command", "command execution", "accept", "decline"],
        },
    },
}


def sample_config_json() -> str:
    return json.dumps(_SAMPLE_CONFIG, indent=2) + "\n"
