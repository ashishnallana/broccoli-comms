from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any
from contextlib import closing

SCHEMA_VERSION = 1
TASK_STATUSES = {"queued", "ready", "working", "blocked", "review", "done", "validated", "archived"}
STATE_STATUSES = {"working", "blocked", "waiting", "review", "done"}
RESULT_STATUSES = {"good", "bad", "need_improvements"}
APPROVAL_STATUSES = {"pending", "decided", "superseded"}
DONE_STATUSES = {"done", "validated"}
TEXT_LIMITS = {
    "title": 200,
    "description": 8000,
    "next_step": 1000,
    "blocked_reason": 1000,
    "result_summary": 2000,
    "result_notes": 2000,
    "current_activity": 500,
    "notes": 4000,
    "list_item": 1000,
    "agent": 200,
    "scope": 500,
    "event_text": 1000,
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d+)([smhd]?)", value.strip())
    if not m:
        raise ValueError("duration must look like 30m, 2h, 10s, or seconds")
    amount = int(m.group(1))
    return amount * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def clean_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    text = text.strip()
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if required and not text:
        raise ValueError(f"{field} is required")
    limit = TEXT_LIMITS.get(field, TEXT_LIMITS["event_text"])
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def clean_text_list(values: list[str] | None, field: str) -> list[str]:
    return [item for item in (clean_text(v, field) for v in (values or [])) if item]


def clean_nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a non-negative integer")
    if number < 0 or number > 1000000:
        raise ValueError(f"{field} must be between 0 and 1000000")
    return number


def clean_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean metadata must be true or false")


def safe_payload(value: Any) -> Any:
    if isinstance(value, str):
        text = clean_text(value, "event_text") or ""
        return text[:TEXT_LIMITS["event_text"]]
    if isinstance(value, list):
        return [safe_payload(v) for v in value[:20]]
    if isinstance(value, dict):
        return {str(k)[:100]: safe_payload(v) for k, v in list(value.items())[:40]}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return clean_text(str(value), "event_text")


class LearningKernel:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init(self) -> None:
        with closing(self.connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version(version) SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
            CREATE TABLE IF NOT EXISTS tasks(
              task_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL, assigned_agent TEXT, scope TEXT, depends_on TEXT NOT NULL DEFAULT '[]',
              priority TEXT NOT NULL DEFAULT 'normal', next_step TEXT, acceptance_criteria TEXT NOT NULL DEFAULT '[]',
              context_refs TEXT NOT NULL DEFAULT '[]', result_summary TEXT, result_status TEXT, result_notes TEXT,
              blocked_reason TEXT, created_by TEXT, updated_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS working_states(
              state_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, agent TEXT NOT NULL, instance_id TEXT,
              task_chain_id TEXT NOT NULL DEFAULT '', root_task_id TEXT,
              status TEXT NOT NULL, current_activity TEXT, next_step TEXT, blockers TEXT NOT NULL DEFAULT '[]',
              notes TEXT, stale_after_seconds INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              version INTEGER NOT NULL DEFAULT 1, UNIQUE(task_id, agent, task_chain_id)
            );
            CREATE TABLE IF NOT EXISTS user_profiles(
              profile_id TEXT PRIMARY KEY, format TEXT NOT NULL, body TEXT NOT NULL, source TEXT,
              updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, timestamp TEXT NOT NULL,
              actor_type TEXT NOT NULL, actor_id TEXT NOT NULL, agent_instance_id TEXT,
              subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, task_id TEXT, scope TEXT,
              payload TEXT NOT NULL DEFAULT '{}', refs TEXT NOT NULL DEFAULT '{}', visibility TEXT NOT NULL DEFAULT 'private',
              schema_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS task_approvals(
              approval_id TEXT PRIMARY KEY, idempotency_key TEXT, task_id TEXT NOT NULL,
              task_chain_id TEXT NOT NULL DEFAULT '', root_task_id TEXT, status TEXT NOT NULL,
              result TEXT, created_event_seq INTEGER, decided_event_seq INTEGER,
              task_version_at_submission INTEGER NOT NULL, event_seq_at_submission INTEGER NOT NULL DEFAULT 0,
              submitter_profile TEXT NOT NULL, submitter_instance_id TEXT,
              result_summary TEXT NOT NULL, acceptance_summary TEXT,
              reusable_discoveries TEXT NOT NULL DEFAULT '[]', clarification_count INTEGER,
              correction_count INTEGER, need_improvements_count INTEGER, first_pass_success INTEGER,
              created_at TEXT NOT NULL, decided_at TEXT, version INTEGER NOT NULL DEFAULT 1,
              UNIQUE(submitter_profile, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_next ON tasks(status, assigned_agent, scope, updated_at);
            CREATE INDEX IF NOT EXISTS idx_events_subject ON events(subject_type, subject_id, timestamp);
            """)
            self._migrate_working_states(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_states_lookup ON working_states(task_id, agent, task_chain_id)")
            self.bootstrap_user_profile(conn)

    def _migrate_working_states(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(working_states)").fetchall()}
        needs_rebuild = "task_chain_id" not in columns or "root_task_id" not in columns
        for idx in conn.execute("PRAGMA index_list(working_states)").fetchall():
            if not idx["unique"]:
                continue
            idx_cols = [r["name"] for r in conn.execute(f"PRAGMA index_info({idx['name']})").fetchall()]
            if idx_cols == ["task_id", "agent"]:
                needs_rebuild = True
        if not needs_rebuild:
            return
        conn.executescript("""
        ALTER TABLE working_states RENAME TO working_states_old;
        CREATE TABLE working_states(
          state_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, agent TEXT NOT NULL, instance_id TEXT,
          task_chain_id TEXT NOT NULL DEFAULT '', root_task_id TEXT,
          status TEXT NOT NULL, current_activity TEXT, next_step TEXT, blockers TEXT NOT NULL DEFAULT '[]',
          notes TEXT, stale_after_seconds INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 1, UNIQUE(task_id, agent, task_chain_id)
        );
        """)
        old_cols = {row["name"] for row in conn.execute("PRAGMA table_info(working_states_old)").fetchall()}
        task_chain_expr = "COALESCE(task_chain_id, '')" if "task_chain_id" in old_cols else "''"
        root_expr = "root_task_id" if "root_task_id" in old_cols else "task_id"
        conn.execute(f"""
            INSERT OR IGNORE INTO working_states(state_id,task_id,agent,instance_id,task_chain_id,root_task_id,status,current_activity,next_step,blockers,notes,stale_after_seconds,created_at,updated_at,version)
            SELECT state_id,task_id,agent,instance_id,{task_chain_expr},{root_expr},status,current_activity,next_step,blockers,notes,stale_after_seconds,created_at,updated_at,version FROM working_states_old
        """)
        conn.execute("DROP TABLE working_states_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_states_lookup ON working_states(task_id, agent, task_chain_id)")

    def bootstrap_user_profile(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT 1 FROM user_profiles WHERE profile_id='default'").fetchone()
        if row:
            return
        body = """# User Profile\n\nShared local preferences for Broccoli Comms agents.\n\n- Be concise in updates.\n- Run relevant tests before reporting completion.\n- Ask for context when confidence is low.\n- Do not store secrets, tokens, raw terminal output, or full transcripts in durable state.\n- Do not commit, push, deploy, or restart services unless explicitly instructed.\n"""
        conn.execute(
            "INSERT INTO user_profiles(profile_id, format, body, source, updated_at) VALUES(?,?,?,?,?)",
            ("default", "markdown", body, "bootstrap", now_iso()),
        )

    def event(self, conn: sqlite3.Connection, event_type: str, actor_type: str, actor_id: str, subject_type: str,
              subject_id: str, payload: dict[str, Any] | None = None, task_id: str | None = None,
              scope: str | None = None, refs: dict[str, Any] | None = None) -> dict[str, Any]:
        ev = {
            "event_id": f"evt-{uuid.uuid4().hex[:16]}", "event_type": event_type, "timestamp": now_iso(),
            "actor_type": actor_type, "actor_id": actor_id, "subject_type": subject_type, "subject_id": subject_id,
            "task_id": task_id, "scope": clean_text(scope, "scope") if scope else None, "payload": safe_payload(payload or {}), "refs": safe_payload(refs or {}),
            "visibility": "private", "schema_version": SCHEMA_VERSION,
        }
        conn.execute(
            "INSERT INTO events(event_id,event_type,timestamp,actor_type,actor_id,subject_type,subject_id,task_id,scope,payload,refs,visibility,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ev["event_id"], ev["event_type"], ev["timestamp"], ev["actor_type"], ev["actor_id"], ev["subject_type"], ev["subject_id"], ev["task_id"], ev["scope"], json.dumps(ev["payload"], sort_keys=True), json.dumps(ev["refs"], sort_keys=True), ev["visibility"], ev["schema_version"]),
        )
        ev["event_seq"] = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        return ev

    def row_task(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        d = dict(row)
        for key in ("depends_on", "acceptance_criteria", "context_refs"):
            d[key] = json.loads(d[key] or "[]")
        return d

    def row_state(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        d = dict(row)
        d["blockers"] = json.loads(d.get("blockers") or "[]")
        return d

    def row_approval(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        d = dict(row)
        d["reusable_discoveries"] = json.loads(d.get("reusable_discoveries") or "[]")
        d["first_pass_success"] = None if d.get("first_pass_success") is None else bool(d["first_pass_success"])
        return d

    def _clean_discoveries(self, discoveries: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        cleaned = []
        for item in (discoveries or [])[:20]:
            if not isinstance(item, dict):
                raise ValueError("discovery must be an object")
            cleaned.append({
                "label": clean_text(item.get("label"), "list_item", required=True) or "",
                "value": clean_text(item.get("value"), "list_item", required=True) or "",
                "reason": clean_text(item.get("reason") or "", "list_item") or "",
            })
        return cleaned

    def task_create(self, **kw: Any) -> dict[str, Any]:
        status = kw.get("status") or "ready"
        if status not in TASK_STATUSES:
            raise ValueError("invalid task status")
        deps = kw.get("depends_on") or []
        task_id = kw.get("task_id") or f"task-{uuid.uuid4().hex[:12]}"
        title = clean_text(kw.get("title"), "title", required=True)
        description = clean_text(kw.get("description") or "", "description") or ""
        assigned_agent = clean_text(kw.get("assigned_agent"), "agent")
        scope = clean_text(kw.get("scope"), "scope")
        next_step = clean_text(kw.get("next_step"), "next_step")
        acceptance = clean_text_list(kw.get("acceptance_criteria") or [], "list_item")
        context_refs = clean_text_list(kw.get("context_refs") or [], "list_item")
        actor = clean_text(kw.get("actor") or "user", "agent") or "user"
        ts = now_iso()
        with closing(self.connect()) as conn:
            self._validate_deps(conn, deps, task_id)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO tasks(task_id,title,description,status,assigned_agent,scope,depends_on,priority,next_step,acceptance_criteria,context_refs,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, title, description, status, assigned_agent, scope, json.dumps(deps), clean_text(kw.get("priority") or "normal", "list_item") or "normal", next_step, json.dumps(acceptance), json.dumps(context_refs), actor, actor, ts, ts),
            )
            self.event(conn, "task_created", "user", actor, "task", task_id, {"title": title, "status": status, "assigned_agent": assigned_agent}, task_id, scope)
            if assigned_agent:
                self.event(conn, "task_assigned", "user", actor, "task", task_id, {"assigned_agent": assigned_agent}, task_id, scope)
            conn.execute("COMMIT")
            return self.row_task(conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())

    def _validate_deps(self, conn: sqlite3.Connection, deps: list[str], self_id: str) -> None:
        if self_id in deps:
            raise ValueError("task cannot depend on itself")
        for dep in deps:
            if not conn.execute("SELECT 1 FROM tasks WHERE task_id=?", (dep,)).fetchone():
                raise ValueError(f"missing dependency: {dep}")

    def task_show(self, task_id: str) -> dict[str, Any]:
        with closing(self.connect()) as conn:
            task = self.row_task(conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())
            if not task:
                raise KeyError(task_id)
            return task

    def task_list(self, agent: str | None = None, statuses: list[str] | None = None, include_archived: bool = False, scope: str | None = None) -> list[dict[str, Any]]:
        clauses, args = [], []
        if agent:
            clauses.append("assigned_agent=?"); args.append(agent)
        if statuses:
            clauses.append("status IN (%s)" % ",".join("?" for _ in statuses)); args.extend(statuses)
        elif not include_archived:
            clauses.append("status!='archived'")
        if scope:
            clauses.append("scope=?"); args.append(scope)
        sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, created_at"
        with closing(self.connect()) as conn:
            return [self.row_task(r) for r in conn.execute(sql, args).fetchall()]

    def task_next(self, agent: str | None = None, scope: str | None = None, include_profile: bool = False) -> dict[str, Any]:
        candidates = self.task_list(agent=agent, statuses=["ready"], include_archived=False, scope=scope)
        with closing(self.connect()) as conn:
            for task in candidates:
                deps = task.get("depends_on") or []
                if all((conn.execute("SELECT status FROM tasks WHERE task_id=?", (d,)).fetchone() or {"status": None})["status"] in DONE_STATUSES for d in deps):
                    payload = {"task": task}
                    if include_profile:
                        payload["user_profile"] = self.user_profile(raw=True)
                    return payload
        payload = {"task": None}
        if include_profile:
            payload["user_profile"] = self.user_profile(raw=True)
        return payload

    def task_update(self, task_id: str, **kw: Any) -> dict[str, Any]:
        allowed = {"status", "next_step", "blocked_reason", "result_summary", "assigned_agent"}
        updates = {k: v for k, v in kw.items() if k in allowed and v is not None}
        for key in list(updates):
            if key != "status":
                updates[key] = clean_text(updates[key], "agent" if key == "assigned_agent" else key)
        actor = clean_text(kw.get("actor") or "user", "agent") or "user"
        if "status" in updates and updates["status"] not in TASK_STATUSES:
            raise ValueError("invalid task status")
        if not updates:
            return self.task_show(task_id)
        with closing(self.connect()) as conn:
            old = self.row_task(conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())
            if not old:
                raise KeyError(task_id)
            conn.execute("BEGIN IMMEDIATE")
            sets = [f"{k}=?" for k in updates] + ["updated_by=?", "updated_at=?", "version=version+1"]
            conn.execute(f"UPDATE tasks SET {','.join(sets)} WHERE task_id=?", [*updates.values(), actor, now_iso(), task_id])
            self.event(conn, "task_updated", "user", actor, "task", task_id, updates, task_id, old.get("scope"))
            if "status" in updates and updates["status"] != old.get("status"):
                self.event(conn, "task_status_changed", "user", actor, "task", task_id, {"old": old.get("status"), "new": updates["status"]}, task_id, old.get("scope"))
            if "assigned_agent" in updates and updates["assigned_agent"] != old.get("assigned_agent"):
                self.event(conn, "task_assigned", "user", actor, "task", task_id, {"assigned_agent": updates["assigned_agent"]}, task_id, old.get("scope"))
            conn.execute("COMMIT")
            return self.task_show(task_id)

    def _validated_result_fields(self, result: str, notes: str | None = None, actor: str = "user", next_step: str | None = None, status: str | None = None) -> tuple[str | None, str, str, str]:
        if result not in RESULT_STATUSES:
            raise ValueError("invalid result")
        notes = clean_text(notes, "result_notes")
        next_step = clean_text(next_step, "next_step")
        actor = clean_text(actor, "agent") or "user"
        if result == "good":
            if status and status != "validated":
                raise ValueError("good results must use status=validated")
            status = "validated"
        else:
            if not next_step:
                raise ValueError("--next-step is required when result is bad or need_improvements")
            allowed_statuses = {"ready", "working", "blocked"}
            status = status or ("blocked" if result == "bad" else "ready")
            if status not in allowed_statuses:
                raise ValueError("non-good result status must be ready, working, or blocked")
        return notes, next_step, actor, status

    def _mark_result_in_tx(self, conn: sqlite3.Connection, task_id: str, result: str, notes: str | None, actor: str, next_step: str | None, status: str, approval_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        conn.execute("UPDATE tasks SET result_status=?, result_notes=?, status=?, next_step=COALESCE(?, next_step), updated_by=?, updated_at=?, version=version+1 WHERE task_id=?", (result, notes, status, next_step, actor, now_iso(), task_id))
        payload = {"result_status": result, "result_notes": notes, "status": status, "next_step": next_step}
        if approval_id:
            payload["approval_id"] = clean_text(approval_id, "list_item")
        ev = self.event(conn, "task_result_marked", "user", actor, "task", task_id, payload, task_id)
        task = self.row_task(conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())
        return task, ev

    def mark_result(self, task_id: str, result: str, notes: str | None = None, actor: str = "user", next_step: str | None = None, status: str | None = None, approval_id: str | None = None) -> dict[str, Any]:
        notes, next_step, actor, status = self._validated_result_fields(result, notes, actor, next_step, status)
        with closing(self.connect()) as conn:
            if not conn.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone():
                raise KeyError(task_id)
            conn.execute("BEGIN IMMEDIATE")
            task, _ev = self._mark_result_in_tx(conn, task_id, result, notes, actor, next_step, status, approval_id)
            conn.execute("COMMIT")
            return task

    def state_set(self, task_id: str, agent: str, **kw: Any) -> dict[str, Any]:
        status = kw.get("status") or "working"
        if status not in STATE_STATUSES:
            raise ValueError("invalid state status")
        agent = clean_text(agent, "agent", required=True) or agent
        current_activity = clean_text(kw.get("current_activity"), "current_activity")
        next_step = clean_text(kw.get("next_step"), "next_step")
        blockers = clean_text_list(kw.get("blockers") or [], "list_item")
        notes = clean_text(kw.get("notes"), "notes")
        instance_id = clean_text(kw.get("instance_id"), "agent")
        root_task_id = clean_text(kw.get("root_task_id") or task_id, "list_item")
        task_chain_id = clean_text(kw.get("task_chain_id") or root_task_id, "list_item")
        clarification_count = clean_nonnegative_int(kw.get("clarification_count"), "clarification_count")
        correction_count = clean_nonnegative_int(kw.get("correction_count"), "correction_count")
        need_improvements_count = clean_nonnegative_int(kw.get("need_improvements_count"), "need_improvements_count")
        first_pass_success = clean_bool(kw.get("first_pass_success"))
        ts = now_iso()
        with closing(self.connect()) as conn:
            if not conn.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone():
                raise KeyError(task_id)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT state_id, instance_id, status FROM working_states WHERE task_id=? AND agent=? AND task_chain_id=?", (task_id, agent, task_chain_id)).fetchone()
            if existing:
                existing_instance = existing["instance_id"]
                if existing_instance and existing["status"] != "done" and (not instance_id or existing_instance != instance_id):
                    raise ValueError(f"working state conflict for task={task_id} agent={agent} task_chain_id={task_chain_id}: owned by instance {existing_instance}")
                state_id = existing["state_id"]
                conn.execute("UPDATE working_states SET instance_id=?,task_chain_id=?,root_task_id=?,status=?,current_activity=?,next_step=?,blockers=?,notes=?,stale_after_seconds=?,updated_at=?,version=version+1 WHERE state_id=?", (instance_id, task_chain_id, root_task_id, status, current_activity, next_step, json.dumps(blockers), notes, kw.get("stale_after_seconds"), ts, state_id))
            else:
                state_id = f"state-{uuid.uuid4().hex[:12]}"
                conn.execute("INSERT INTO working_states(state_id,task_id,agent,instance_id,task_chain_id,root_task_id,status,current_activity,next_step,blockers,notes,stale_after_seconds,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (state_id, task_id, agent, instance_id, task_chain_id, root_task_id, status, current_activity, next_step, json.dumps(blockers), notes, kw.get("stale_after_seconds"), ts, ts))
            event_payload = {"status": status, "current_activity": current_activity, "next_step": next_step, "blocker_count": len(blockers)}
            structured = {
                "agent_instance_id": instance_id,
                "task_chain_id": task_chain_id,
                "root_task_id": root_task_id,
                "clarification_count": clarification_count,
                "correction_count": correction_count,
                "need_improvements_count": need_improvements_count,
                "first_pass_success": first_pass_success,
            }
            event_payload.update({k: v for k, v in structured.items() if v is not None})
            self.event(conn, "working_state_set", "agent", agent, "working_state", state_id, event_payload, task_id)
            conn.execute("COMMIT")
            return self.row_state(conn.execute("SELECT * FROM working_states WHERE state_id=?", (state_id,)).fetchone())

    def state_show(self, task_id: str, agent: str | None = None) -> dict[str, Any] | list[dict[str, Any]] | None:
        with closing(self.connect()) as conn:
            if agent:
                rows = [self.row_state(r) for r in conn.execute("SELECT * FROM working_states WHERE task_id=? AND agent=? ORDER BY task_chain_id, updated_at DESC", (task_id, agent)).fetchall()]
                if not rows:
                    return None
                return rows[0] if len(rows) == 1 else rows
            return [self.row_state(r) for r in conn.execute("SELECT * FROM working_states WHERE task_id=? ORDER BY task_chain_id, updated_at DESC", (task_id,)).fetchall()]

    def state_list(self, agent: str | None = None, task_id: str | None = None, stale_after: int | None = None) -> list[dict[str, Any]]:
        clauses, args = [], []
        if agent:
            clauses.append("agent=?"); args.append(agent)
        if task_id:
            clauses.append("task_id=?"); args.append(task_id)
        with closing(self.connect()) as conn:
            rows = [self.row_state(r) for r in conn.execute("SELECT * FROM working_states" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY updated_at DESC", args).fetchall()]
        if stale_after is not None:
            cutoff = time.time() - stale_after
            rows = [r for r in rows if _iso_to_epoch(r["updated_at"]) < cutoff]
        return rows

    def state_clear(self, task_id: str, agent: str | None = None, actor: str = "user") -> dict[str, Any]:
        actor = clean_text(actor, "agent") or "user"
        agent = clean_text(agent, "agent") if agent else None
        with closing(self.connect()) as conn:
            if agent:
                states = [self.row_state(r) for r in conn.execute("SELECT * FROM working_states WHERE task_id=? AND agent=?", (task_id, agent)).fetchall()]
            else:
                states = [self.row_state(r) for r in conn.execute("SELECT * FROM working_states WHERE task_id=?", (task_id,)).fetchall()]
            conn.execute("BEGIN IMMEDIATE")
            if agent:
                conn.execute("DELETE FROM working_states WHERE task_id=? AND agent=?", (task_id, agent))
            else:
                conn.execute("DELETE FROM working_states WHERE task_id=?", (task_id,))
            for st in states:
                self.event(conn, "working_state_cleared", "user", actor, "working_state", st["state_id"], {"agent": st["agent"], "task_chain_id": st.get("task_chain_id"), "root_task_id": st.get("root_task_id"), "agent_instance_id": st.get("instance_id")}, task_id)
            conn.execute("COMMIT")
            return {"cleared": len(states), "task_id": task_id, "agent": agent}

    def submit_completion(self, task_id: str, **kw: Any) -> dict[str, Any]:
        if kw.get("non_learning"):
            raise ValueError("immutable/non-learning instances cannot submit learning approvals")
        agent = clean_text(kw.get("agent"), "agent", required=True) or "agent"
        instance_id = clean_text(kw.get("agent_instance_id"), "agent")
        root_task_id = clean_text(kw.get("root_task_id") or task_id, "list_item")
        task_chain_id = clean_text(kw.get("task_chain_id") or root_task_id, "list_item")
        result_summary = clean_text(kw.get("result_summary"), "result_summary", required=True) or ""
        acceptance_summary = clean_text(kw.get("acceptance_summary"), "result_summary")
        idempotency_key = clean_text(kw.get("idempotency_key"), "list_item")
        discoveries = self._clean_discoveries(kw.get("reusable_discoveries") or [])
        clarification_count = clean_nonnegative_int(kw.get("clarification_count"), "clarification_count")
        correction_count = clean_nonnegative_int(kw.get("correction_count"), "correction_count")
        need_improvements_count = clean_nonnegative_int(kw.get("need_improvements_count"), "need_improvements_count")
        first_pass_success = clean_bool(kw.get("first_pass_success"))
        ts = now_iso()
        with closing(self.connect()) as conn:
            task = self.row_task(conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())
            if not task:
                raise KeyError(task_id)
            payload_fingerprint = {
                "task_id": task_id, "task_chain_id": task_chain_id, "root_task_id": root_task_id,
                "agent_instance_id": instance_id, "result_summary": result_summary,
                "acceptance_summary": acceptance_summary, "reusable_discoveries": discoveries,
                "clarification_count": clarification_count, "correction_count": correction_count,
                "need_improvements_count": need_improvements_count, "first_pass_success": first_pass_success,
            }
            if idempotency_key:
                existing = self.row_approval(conn.execute("SELECT * FROM task_approvals WHERE submitter_profile=? AND idempotency_key=?", (agent, idempotency_key)).fetchone())
                if existing:
                    existing_fingerprint = {
                        "task_id": existing["task_id"], "task_chain_id": existing.get("task_chain_id") or "", "root_task_id": existing.get("root_task_id") or existing["task_id"],
                        "agent_instance_id": existing.get("submitter_instance_id"), "result_summary": existing.get("result_summary"),
                        "acceptance_summary": existing.get("acceptance_summary"), "reusable_discoveries": existing.get("reusable_discoveries") or [],
                        "clarification_count": existing.get("clarification_count"), "correction_count": existing.get("correction_count"),
                        "need_improvements_count": existing.get("need_improvements_count"), "first_pass_success": existing.get("first_pass_success"),
                    }
                    if existing_fingerprint != payload_fingerprint:
                        raise ValueError("idempotency key reuse with different completion payload")
                    return {"approval": existing, "task": task, "idempotent": True, "notification": None}
            conn.execute("BEGIN IMMEDIATE")
            pending = conn.execute("SELECT approval_id FROM task_approvals WHERE task_id=? AND task_chain_id=? AND status='pending'", (task_id, task_chain_id)).fetchone()
            if pending:
                conn.execute("ROLLBACK")
                raise ValueError(f"pending approval already exists for task={task_id} task_chain_id={task_chain_id}: {pending['approval_id']}")
            conn.execute("UPDATE tasks SET status='review', result_summary=?, updated_by=?, updated_at=?, version=version+1 WHERE task_id=?", (result_summary, agent, ts, task_id))
            approval_id = f"apr-{uuid.uuid4().hex[:12]}"
            submitted = self.event(conn, "task_completion_submitted", "agent", agent, "task", task_id, {"approval_id": approval_id, "task_chain_id": task_chain_id, "root_task_id": root_task_id, "agent_profile": agent, "agent_instance_id": instance_id, "result_summary": result_summary, "acceptance_summary": acceptance_summary, "reusable_discoveries": discoveries, "clarification_count": clarification_count, "correction_count": correction_count, "need_improvements_count": need_improvements_count, "first_pass_success": first_pass_success}, task_id)
            requested = self.event(conn, "task_approval_requested", "system", "task-kernel", "task_approval", approval_id, {"approval_id": approval_id, "task_id": task_id, "task_chain_id": task_chain_id, "root_task_id": root_task_id, "agent_profile": agent, "agent_instance_id": instance_id}, task_id)
            conn.execute("""
                INSERT INTO task_approvals(approval_id,idempotency_key,task_id,task_chain_id,root_task_id,status,created_event_seq,task_version_at_submission,event_seq_at_submission,submitter_profile,submitter_instance_id,result_summary,acceptance_summary,reusable_discoveries,clarification_count,correction_count,need_improvements_count,first_pass_success,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (approval_id, idempotency_key, task_id, task_chain_id, root_task_id, "pending", requested["event_seq"], task.get("version"), submitted["event_seq"], agent, instance_id, result_summary, acceptance_summary, json.dumps(discoveries), clarification_count, correction_count, need_improvements_count, None if first_pass_success is None else int(first_pass_success), ts))
            conn.execute("COMMIT")
            approval = self.row_approval(conn.execute("SELECT * FROM task_approvals WHERE approval_id=?", (approval_id,)).fetchone())
            updated_task = self.task_show(task_id)
            return {"approval": approval, "task": updated_task, "idempotent": False, "notification": None}

    def record_approval_notification(self, approval_id: str, sent: bool, detail: str | None = None) -> dict[str, Any]:
        with closing(self.connect()) as conn:
            approval = self.row_approval(conn.execute("SELECT * FROM task_approvals WHERE approval_id=?", (approval_id,)).fetchone())
            if not approval:
                raise KeyError(approval_id)
            conn.execute("BEGIN IMMEDIATE")
            ev = self.event(conn, "task_approval_notification_sent" if sent else "task_approval_notification_failed", "system", "task-kernel", "task_approval", approval_id, {"approval_id": approval_id, "detail": clean_text(detail, "event_text")}, approval["task_id"])
            conn.execute("COMMIT")
            return ev

    def review_completion(self, approval_id: str, result: str, **kw: Any) -> dict[str, Any]:
        if result not in RESULT_STATUSES:
            raise ValueError("invalid result")
        next_step = clean_text(kw.get("next_step"), "next_step")
        notes = clean_text(kw.get("notes"), "result_notes")
        expected_version = kw.get("task_version_at_submission")
        actor = clean_text(kw.get("actor") or "user", "agent") or "user"
        with closing(self.connect()) as conn:
            approval = self.row_approval(conn.execute("SELECT * FROM task_approvals WHERE approval_id=?", (approval_id,)).fetchone())
            if not approval:
                raise KeyError(approval_id)
            task = self.row_task(conn.execute("SELECT * FROM tasks WHERE task_id=?", (approval["task_id"],)).fetchone())
            if not task:
                raise KeyError(approval["task_id"])
            if approval["status"] == "decided":
                if approval.get("result") == result:
                    return {"approval": approval, "task": task, "idempotent": True}
                raise ValueError("approval already decided with a different result")
            if expected_version is not None and int(expected_version) != int(approval["task_version_at_submission"]):
                raise ValueError("refresh required: stale approval card")
            expected_current_version = int(approval["task_version_at_submission"]) + 1
            if task.get("status") != "review" or int(task.get("version") or 0) != expected_current_version:
                raise ValueError("refresh required: task changed since approval submission")
            notes, next_step, actor, status = self._validated_result_fields(result, notes, actor, next_step, kw.get("status"))
            conn.execute("BEGIN IMMEDIATE")
            latest = self.row_approval(conn.execute("SELECT * FROM task_approvals WHERE approval_id=?", (approval_id,)).fetchone())
            latest_task = self.row_task(conn.execute("SELECT * FROM tasks WHERE task_id=?", (approval["task_id"],)).fetchone())
            if latest["status"] != "pending" or latest_task.get("status") != "review" or int(latest_task.get("version") or 0) != expected_current_version:
                conn.execute("ROLLBACK")
                raise ValueError("refresh required: approval or task changed")
            updated_task, ev = self._mark_result_in_tx(conn, approval["task_id"], result, notes, actor, next_step, status, approval_id)
            conn.execute("UPDATE task_approvals SET status='decided', result=?, decided_event_seq=?, decided_at=?, version=version+1 WHERE approval_id=?", (result, ev["event_seq"], now_iso(), approval_id))
            conn.execute("COMMIT")
        return {"approval": self.show_approval(approval_id), "task": updated_task, "idempotent": False}

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        clauses, args = [], []
        if status:
            clauses.append("status=?"); args.append(status)
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT * FROM task_approvals" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY created_at, approval_id", args).fetchall()
        return [self.row_approval(r) for r in rows]

    def show_approval(self, approval_id: str) -> dict[str, Any]:
        with closing(self.connect()) as conn:
            approval = self.row_approval(conn.execute("SELECT * FROM task_approvals WHERE approval_id=?", (approval_id,)).fetchone())
        if not approval:
            raise KeyError(approval_id)
        return approval

    def user_profile(self, raw: bool = False) -> dict[str, Any]:
        with closing(self.connect()) as conn:
            row = dict(conn.execute("SELECT * FROM user_profiles WHERE profile_id='default'").fetchone())
        row["warning"] = "User profile is local/private and must not contain secrets or tokens."
        return row

    def events(self, task_id: str | None = None, subject_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses, args = [], []
        if task_id:
            clauses.append("task_id=?"); args.append(task_id)
        if subject_id:
            clauses.append("subject_id=?"); args.append(subject_id)
        args.append(limit)
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT rowid AS event_seq, * FROM events" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY rowid LIMIT ?", args).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["payload"] = json.loads(d["payload"] or "{}"); d["refs"] = json.loads(d["refs"] or "{}"); out.append(d)
        return out


def _iso_to_epoch(value: str) -> float:
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return 0.0


DEFAULT_AGENT_CONTRACT_TEMPLATE = """# Agent Operating Contract

You are: {agent}
Agent profile: {agent}
Instance: {instance}
Ephemeral cwd: {cwd}

Durable state lives in Broccoli Comms. Do not rely on this cwd for memory.

## Required startup
1. Run `broccoli-comms task bootstrap --agent {agent} --json` or `broccoli-comms task next --agent {agent} --include-profile --json`.
2. If a task is returned, run `broccoli-comms state show --task <task_id> --agent {agent} --json`.
3. If no task is ready, stand by and do not invent work.

## Checkpoint and discovery rules
- Update WorkingState when starting, blocking, requesting review, finishing, or discovering reusable facts.
- Use `broccoli-comms state set --task <task_id> --agent {agent} --instance <agent_instance_id> --task-chain-id <chain> --root-task-id <root> --status working --current-activity ... --next-step ... --notes ... --clarification-count N --correction-count N --need-improvements-count N --first-pass-success|--no-first-pass-success --json` for bounded checkpoints.
- Checkpoint important discoveries such as database names, table names, commands/tools used, blockers, assumptions, and the next_step.
- Example: when finding the right database, record the database/table name and why it was correct as a bounded checkpoint so future agents can avoid rediscovery.

## Result and validation workflow
- When completing work, update the task with a bounded result_summary suitable for user validation.
- When the user says a result is correct, ensure the task is marked `good`/`validated` with `broccoli-comms task mark-result <task_id> --result good --json` so the append-only event log captures: goal -> checkpoints/discoveries -> result summary -> user validation.
- For partial or incorrect results, include a remediation next_step with `task mark-result --result bad|need_improvements --next-step ...`.

## Clarification and correction tracking
- Record each user clarification or correction as bounded task/state/result metadata, not raw chat.
- Use structured `state set` metadata flags for clarification_count, correction_count, need_improvements_count, and first_pass_success so these metrics are derivable from `working_state_set` events.
- Before marking good/validated, ensure the append-only log can show whether success was first-pass or correction-assisted.
- For examples like finding the right database, checkpoint user corrections/clarifications and the final corrected database/table name so future agents know why the answer was correct.

## Parallel instances and task chains
- `{agent}` is the stable agent profile/name; each process has its own runtime agent_instance_id and ephemeral workspace.
- Multiple active instances of the same profile may work in parallel on different task_chain_id/root_task_id values while sharing the ordered append-only log.
- Do not overwrite another instance's same-chain checkpoint; if duplicate same-profile instances target the same active task chain, ask the coordinator to resolve claiming.

## Immutable / non-learning instances
- Phase 1 durable CLI commands are for normal reproducible learning instances.
- If you are explicitly launched as immutable or non-learning, treat work as transient: do not write state checkpoints, task results, or learning events to the persistent append-only log.
- Immutable/non-learning messages or results cannot be used for future validated learning unless a coordinator explicitly records them separately as learning-eligible facts.
- Do not silently claim task chains that require durable validation when operating in immutable/non-learning mode.

## Safety and memory boundaries
- Ask user/coordinator for context if confidence is low.
- Explicit user instructions override task/profile/habits.
- Save durable outputs only through Broccoli Comms commands.
- Never store raw terminal transcripts, full query logs, secrets, tokens, passwords, or large file contents in task/state/result text.
- Keep task/state/result text concise and bounded; store facts and conclusions, not bulky evidence.
"""


def agent_contract(agent: str, instance: str | None, cwd: str | Path, template: str | None = None) -> str:
    cwd = str(cwd)
    instance = instance or f"{agent}@manual"
    return (template or DEFAULT_AGENT_CONTRACT_TEMPLATE).format(agent=agent, instance=instance, cwd=cwd)
