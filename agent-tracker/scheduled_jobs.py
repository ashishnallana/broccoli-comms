"""Extensible scheduled jobs for the local agent-tracker daemon."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import time
from typing import Callable

import config
import state
import tmux_util


DEFAULT_AGENT_TASK_NUDGE_INTERVAL_SECONDS = 600
DEFAULT_AGENT_TASK_NUDGE_MAX_NUDGES = 5
DEFAULT_AGENT_TASK_NUDGE_BACKOFF_MULTIPLIER = 2.0
SYSTEM_SENDER = "agent-tracker-scheduler"


@dataclass(frozen=True)
class ScheduledJob:
    """A daemon-local scheduled job with config-driven cadence."""

    name: str
    default_interval_seconds: float
    run_once: Callable[[], None]


def _job_config(job_name: str, default_interval_seconds: float = DEFAULT_AGENT_TASK_NUDGE_INTERVAL_SECONDS) -> tuple[bool, float]:
    """Return (enabled, interval_seconds) for a scheduled job.

    Config shape:

        [scheduled_jobs]
        enabled = true

        [scheduled_jobs.agent_task_nudge]
        enabled = true
        interval_seconds = 600

    `interval_minutes` is also accepted for readability. Missing config keeps the
    job enabled at its default interval so existing installs get the requested
    behavior after deploying a version that includes this job.
    """
    cfg = config.load_config()
    scheduled = cfg.get("scheduled_jobs") if isinstance(cfg, dict) else {}
    if not isinstance(scheduled, dict):
        scheduled = {}
    if scheduled.get("enabled", True) is False:
        return False, default_interval_seconds
    job_cfg = scheduled.get(job_name) or {}
    if not isinstance(job_cfg, dict):
        job_cfg = {}
    enabled = bool(job_cfg.get("enabled", True))
    interval = job_cfg.get("interval_seconds")
    if interval is None and job_cfg.get("interval_minutes") is not None:
        interval = float(job_cfg["interval_minutes"]) * 60
    if interval is None:
        interval = default_interval_seconds
    try:
        interval_seconds = max(1.0, float(interval))
    except (TypeError, ValueError):
        interval_seconds = default_interval_seconds
    return enabled, interval_seconds


def _agent_task_nudge_config() -> dict:
    """Return config for the local-agent task nudge job."""
    enabled, interval_seconds = _job_config("agent_task_nudge", DEFAULT_AGENT_TASK_NUDGE_INTERVAL_SECONDS)
    cfg = config.load_config()
    scheduled = cfg.get("scheduled_jobs") if isinstance(cfg, dict) else {}
    job_cfg = (scheduled or {}).get("agent_task_nudge") if isinstance(scheduled, dict) else {}
    if not isinstance(job_cfg, dict):
        job_cfg = {}
    try:
        max_nudges = max(0, int(job_cfg.get("max_nudges", DEFAULT_AGENT_TASK_NUDGE_MAX_NUDGES)))
    except (TypeError, ValueError):
        max_nudges = DEFAULT_AGENT_TASK_NUDGE_MAX_NUDGES
    try:
        backoff_multiplier = max(1.0, float(job_cfg.get("backoff_multiplier", DEFAULT_AGENT_TASK_NUDGE_BACKOFF_MULTIPLIER)))
    except (TypeError, ValueError):
        backoff_multiplier = DEFAULT_AGENT_TASK_NUDGE_BACKOFF_MULTIPLIER
    state_path = job_cfg.get("state_path") or str(Path(state.CACHE_DIR) / "scheduled-task-nudges.json")
    return {
        "enabled": enabled,
        "interval_seconds": interval_seconds,
        "max_nudges": max_nudges,
        "backoff_multiplier": backoff_multiplier,
        "state_path": str(state_path),
    }


def _load_nudge_state(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logging.warning("failed to load scheduled nudge state %s: %s", path, exc)
        return {}


def _save_nudge_state(path: str, data: dict) -> None:
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        tmp.replace(target)
    except Exception as exc:
        logging.warning("failed to save scheduled nudge state %s: %s", path, exc)


def _task_nudge_allowed(task_id: str, nudge_state: dict, nudge_cfg: dict, now: float) -> tuple[bool, str]:
    if not task_id:
        return False, "no_task"
    entry = nudge_state.get(task_id) if isinstance(nudge_state.get(task_id), dict) else {}
    count = int(entry.get("count") or 0)
    if count >= nudge_cfg["max_nudges"]:
        return False, "max_nudges"
    last_nudged_at = float(entry.get("last_nudged_at") or 0.0)
    if last_nudged_at <= 0:
        return True, "ok"
    delay = nudge_cfg["interval_seconds"] * (nudge_cfg["backoff_multiplier"] ** count)
    if now - last_nudged_at < delay:
        return False, "backoff"
    return True, "ok"


def _record_task_nudge(task_id: str, nudge_state: dict, now: float) -> None:
    entry = nudge_state.get(task_id) if isinstance(nudge_state.get(task_id), dict) else {}
    nudge_state[task_id] = {
        "count": int(entry.get("count") or 0) + 1,
        "last_nudged_at": now,
    }


def _is_local_nudge_candidate(name: str, info: dict, task_fields: dict) -> bool:
    """Return whether a local registered agent should receive a task nudge."""
    if not name or not isinstance(info, dict):
        return False
    if info.get("scope") not in {None, "local"}:
        return False
    if info.get("is_mailbox") or info.get("direct_input_disabled") or info.get("agent_type") == "agent-communicator-ui":
        return False
    if not info.get("tmux_pane") or not info.get("tmux_socket"):
        return False
    if not task_fields.get("current_task_id"):
        return False
    if (task_fields.get("current_task_status") or "").lower() == "blocked":
        return False
    return True


def _send_agent_nudge_text(info: dict, task_fields: dict) -> None:
    """Type the nudge directly into the local agent pane without inbox delivery."""
    tmux_util.send_literal_text(
        info["tmux_pane"],
        _nudge_message(task_fields),
        submit=True,
        socket_path=info["tmux_socket"],
    )


def _nudge_message(task_fields: dict) -> str:
    task_id = task_fields.get("current_task_id") or "current task"
    title = task_fields.get("current_task") or "your current task"
    next_step = task_fields.get("current_task_next_step") or "continue from the latest task state"
    return (
        f"Scheduled task nudge: task `{task_id}` ({title}) is not marked blocked. "
        f"Please continue working on it. Next step: {next_step}. "
        "If you cannot proceed, mark the current task blocked to avoid future notifications."
    )


def run_agent_task_nudge_once(now: float | None = None) -> dict:
    """Nudge local agents whose current durable task is not blocked.

    Returns counters for tests/logging. Only local controllable pane agents are
    considered; remote registry agents are intentionally out of scope.
    """
    now = time.time() if now is None else now
    nudge_cfg = _agent_task_nudge_config()
    if not nudge_cfg["enabled"]:
        return {"checked": 0, "nudged": 0, "skipped": 0, "backoff_skipped": 0, "max_skipped": 0, "errors": 0}
    nudge_state = _load_nudge_state(nudge_cfg["state_path"])
    state_changed = False
    agents = state.get_all_agents() or {}
    durable_tasks = state.durable_current_tasks_by_agent()
    counts = {"checked": 0, "nudged": 0, "skipped": 0, "backoff_skipped": 0, "max_skipped": 0, "errors": 0}
    for name, info in agents.items():
        counts["checked"] += 1
        task_fields = state.current_task_fields_for_agent(name, info, durable_tasks)
        if not _is_local_nudge_candidate(name, info, task_fields):
            counts["skipped"] += 1
            continue
        task_id = task_fields.get("current_task_id") or ""
        allowed, reason = _task_nudge_allowed(task_id, nudge_state, nudge_cfg, now)
        if not allowed:
            if reason == "backoff":
                counts["backoff_skipped"] += 1
            elif reason == "max_nudges":
                counts["max_skipped"] += 1
            else:
                counts["skipped"] += 1
            continue
        try:
            tmux_util.send_symbolic_keys(info["tmux_pane"], ["Escape"], socket_path=info["tmux_socket"])
            _send_agent_nudge_text(info, task_fields)
            _record_task_nudge(task_id, nudge_state, now)
            state_changed = True
            counts["nudged"] += 1
        except Exception as exc:  # pragma: no cover - exact failures are environment-dependent.
            counts["errors"] += 1
            logging.warning("scheduled agent_task_nudge failed for %s: %s", name, exc)
    if state_changed:
        _save_nudge_state(nudge_cfg["state_path"], nudge_state)
    return counts


def scheduled_jobs() -> list[ScheduledJob]:
    """Return the registered scheduled jobs.

    Add future jobs here with their own config name and default interval.
    """
    return [
        ScheduledJob(
            name="agent_task_nudge",
            default_interval_seconds=DEFAULT_AGENT_TASK_NUDGE_INTERVAL_SECONDS,
            run_once=run_agent_task_nudge_once,
        )
    ]


def background_scheduler(stop_event=None, now: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None) -> None:
    """Run all scheduled jobs with per-job config-driven intervals."""
    now = now or time.time
    sleep = sleep or time.sleep
    last_run: dict[str, float] = {}
    while stop_event is None or not stop_event.is_set():
        current = now()
        next_sleep = 1.0
        for job in scheduled_jobs():
            enabled, interval_seconds = _job_config(job.name, job.default_interval_seconds)
            if not enabled:
                last_run.pop(job.name, None)
                continue
            previous = last_run.get(job.name, 0.0)
            remaining = interval_seconds - (current - previous)
            if previous <= 0 or remaining <= 0:
                try:
                    result = job.run_once()
                    logging.info("scheduled job %s completed: %s", job.name, result)
                except Exception as exc:  # pragma: no cover - defensive daemon guard.
                    logging.exception("scheduled job %s failed: %s", job.name, exc)
                last_run[job.name] = current
                remaining = interval_seconds
            next_sleep = min(next_sleep, max(0.1, remaining))
        if stop_event is not None and stop_event.wait(next_sleep):
            break
        if stop_event is None:
            sleep(next_sleep)
