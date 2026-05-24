import base64
import binascii
import errno
import json
import logging
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger("agent-registry")

TOKEN = os.environ.get("AGENT_REGISTRY_TOKEN", "")
AUTH_REQUIRED = os.environ.get("AGENT_REGISTRY_AUTH", "true").lower() not in ("0", "false", "no")
MAX_BODY_BYTES = int(os.environ.get("AGENT_MAX_DELIVERY_BYTES", "5242880"))
STALE = int(os.environ.get("TRACKER_STALE_SECONDS", "60"))
GONE = int(os.environ.get("TRACKER_GONE_SECONDS", "180"))
DELIVERY_WAIT_SECONDS = int(os.environ.get("AGENT_REGISTRY_DELIVERY_WAIT_SECONDS", "25"))
STATE_PATH = os.environ.get(
    "AGENT_REGISTRY_STATE_PATH",
    os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "agent-registry", "state.json"),
)


class Store:
    def __init__(self, state_path=None):
        self.state_path = state_path if state_path is not None else STATE_PATH
        self.trackers = {}
        self.agents = {}
        self.deliveries = {}
        self.tracker_events = {}
        self.lock = threading.RLock()
        self.cv = threading.Condition(self.lock)
        self._load_locked()

    def _load_locked(self):
        with self.lock:
            try:
                with open(self.state_path, "r") as f:
                    data = json.load(f)
            except FileNotFoundError:
                LOG.info("registry state file not found yet at %s; starting empty", self.state_path)
                return
            except Exception as e:
                LOG.warning("failed to load registry state from %s: %s", self.state_path, e)
                return
            self.trackers = data.get("trackers") or {}
            self.agents = data.get("agents") or {}
            self.deliveries = {
                tracker_id: {item["message_id"]: item for item in queue}
                for tracker_id, queue in (data.get("deliveries") or {}).items()
                if isinstance(queue, list)
            }
            self.tracker_events = {
                tracker_id: {item["event_id"]: item for item in queue}
                for tracker_id, queue in (data.get("tracker_events") or {}).items()
                if isinstance(queue, list)
            }
            LOG.info(
                "loaded registry state from %s trackers=%s agents=%s queued_trackers=%s",
                self.state_path,
                len(self.trackers),
                len(self.agents),
                len(self.deliveries),
            )

    def _persist_locked(self):
        if not self.state_path:
            return
        state_dir = os.path.dirname(self.state_path)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
        tmp = f"{self.state_path}.tmp"
        with open(tmp, "w") as f:
            json.dump(
                {
                    "trackers": self.trackers,
                    "agents": self.agents,
                    "deliveries": {
                        tracker_id: sorted(queue.values(), key=lambda item: item.get("queued_at", 0))
                        for tracker_id, queue in self.deliveries.items()
                    },
                    "tracker_events": {
                        tracker_id: sorted(queue.values(), key=lambda item: item.get("created_at", 0))
                        for tracker_id, queue in self.tracker_events.items()
                    },
                },
                f,
            )
        os.replace(tmp, self.state_path)

    def sweep(self, now=None):
        with self.lock:
            now = time.time() if now is None else now
            changed = False
            for tracker in self.trackers.values():
                age = now - tracker["last_heartbeat"]
                status = "active" if age <= STALE else "stale" if age <= GONE else "gone"
                if tracker.get("status") != status:
                    LOG.info(
                        "tracker_id=%s hostname=%s status transition %s -> %s age=%.1fs",
                        tracker.get("tracker_id"),
                        tracker.get("hostname"),
                        tracker.get("status"),
                        status,
                        age,
                    )
                    tracker["status"] = status
                    changed = True
            agents = {
                agent_id: info
                for agent_id, info in self.agents.items()
                if self.trackers.get(info["tracker_id"], {}).get("status") != "gone"
            }
            deliveries = {
                tracker_id: queue
                for tracker_id, queue in self.deliveries.items()
                if self.trackers.get(tracker_id, {}).get("status") != "gone"
            }
            if agents != self.agents:
                self.agents = agents
                changed = True
            if deliveries != self.deliveries:
                self.deliveries = deliveries
                changed = True
            tracker_events = {
                tracker_id: queue
                for tracker_id, queue in self.tracker_events.items()
                if self.trackers.get(tracker_id, {}).get("status") != "gone"
            }
            if tracker_events != self.tracker_events:
                self.tracker_events = tracker_events
                changed = True
            if changed:
                LOG.info("registry sweep updated state trackers=%s agents=%s queued_trackers=%s", len(self.trackers), len(self.agents), len(self.deliveries))
                self._persist_locked()

    def list_agents(self):
        with self.lock:
            return list(self.agents.values())

    def get_agent(self, agent_id):
        with self.lock:
            agent = self.agents.get(agent_id)
            return dict(agent) if agent else None

    def has_tracker(self, tracker_id):
        with self.lock:
            return tracker_id in self.trackers

    def get_tracker(self, tracker_id):
        with self.lock:
            tracker = self.trackers.get(tracker_id)
            return dict(tracker) if tracker else None

    def list_trackers(self):
        with self.lock:
            return [
                {
                    "tracker_id": t["tracker_id"],
                    "hostname": t["hostname"],
                    "address": t["address"],
                    "http_port": t["http_port"],
                    "status": t["status"],
                    "agent_configs": t.get("agent_configs") or [],
                }
                for t in self.trackers.values()
                if t["status"] != "gone"
            ]

    def put_tracker(self, body):
        with self.cv:
            existing = next((tid for tid, t in self.trackers.items() if t["hostname"] == body["hostname"] and tid != body["tracker_id"]), None)
            if existing:
                LOG.warning("replacing existing tracker_id=%s for hostname=%s with tracker_id=%s", existing, body["hostname"], body["tracker_id"])
                self.trackers.pop(existing, None)
                self.agents = {k: v for k, v in self.agents.items() if v["tracker_id"] != existing}
                self.deliveries.pop(existing, None)
                self.tracker_events.pop(existing, None)
            created = body["tracker_id"] not in self.trackers
            self.trackers[body["tracker_id"]] = {
                "tracker_id": body["tracker_id"],
                "hostname": body["hostname"],
                "address": body["address"],
                "http_port": body["http_port"],
                "last_heartbeat": time.time(),
                "status": "active",
                "agent_configs": body.get("agent_configs") or [],
            }
            self._replace_agents_locked(body["tracker_id"], body.get("agents", []))
            self.deliveries.setdefault(body["tracker_id"], {})
            self.tracker_events.setdefault(body["tracker_id"], {})
            self._persist_locked()
            self.cv.notify_all()
            LOG.info(
                "tracker %s tracker_id=%s hostname=%s http_port=%s agents=%s",
                "registered" if created else "updated",
                body["tracker_id"],
                body["hostname"],
                body["http_port"],
                len(body.get("agents", [])),
            )
            return created

    def _replace_agents_locked(self, tracker_id, agents):
        tracker, now = self.trackers[tracker_id], time.time()
        self.agents = {k: v for k, v in self.agents.items() if v["tracker_id"] != tracker_id}
        for agent in agents:
            self.agents[agent["agent_id"]] = {
                **agent,
                "tracker_id": tracker_id,
                "hostname": tracker["hostname"],
                "last_seen": now,
                "address": tracker["address"],
                "http_port": tracker["http_port"],
            }

    def heartbeat(self, tracker_id, agents, agent_configs=None):
        with self.cv:
            if tracker_id not in self.trackers:
                LOG.warning("heartbeat for unknown tracker_id=%s agents=%s", tracker_id, len(agents))
                return False
            self.trackers[tracker_id]["last_heartbeat"] = time.time()
            self.trackers[tracker_id]["status"] = "active"
            self.trackers[tracker_id]["agent_configs"] = agent_configs or []
            self._replace_agents_locked(tracker_id, agents)
            self._persist_locked()
            self.cv.notify_all()
            return True

    def update_agent(self, tracker_id, agent_id, status):
        with self.cv:
            agent = self.agents.get(agent_id)
            if not agent:
                LOG.warning("agent-update for missing agent_id=%s tracker_id=%s status=%s", agent_id, tracker_id, status)
                return 404
            if agent["tracker_id"] != tracker_id:
                LOG.warning("agent-update wrong tracker agent_id=%s expected_tracker_id=%s got_tracker_id=%s", agent_id, agent["tracker_id"], tracker_id)
                return 403
            agent["status"], agent["last_seen"] = status, time.time()
            self._persist_locked()
            return 200

    def enqueue_delivery(self, tracker_id, payload):
        entry = {**payload, "message_id": payload.get("message_id") or str(uuid.uuid4()), "queued_at": time.time()}
        with self.cv:
            self.deliveries.setdefault(tracker_id, {})[entry["message_id"]] = entry
            self._persist_locked()
            self.cv.notify_all()
            LOG.info(
                "queued delivery message_id=%s tracker_id=%s target_agent_id=%s sender_tracker=%s",
                entry["message_id"],
                tracker_id,
                entry.get("target_agent_id"),
                entry.get("sender_tracker"),
            )
        return entry

    def wait_for_deliveries(self, tracker_id, timeout):
        deadline = time.time() + max(timeout, 0)
        with self.cv:
            while True:
                queue = sorted(self.deliveries.get(tracker_id, {}).values(), key=lambda item: item.get("queued_at", 0))
                if queue:
                    LOG.info("returning %s queued deliveries to tracker_id=%s", len(queue), tracker_id)
                    return [dict(item) for item in queue]
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self.cv.wait(timeout=remaining)

    def ack_delivery(self, tracker_id, message_id):
        with self.cv:
            queue = self.deliveries.get(tracker_id)
            if not queue or message_id not in queue:
                LOG.warning("ack for unknown delivery tracker_id=%s message_id=%s", tracker_id, message_id)
                return False
            queue.pop(message_id, None)
            if not queue:
                self.deliveries.pop(tracker_id, None)
            self._persist_locked()
            LOG.info("acked delivery tracker_id=%s message_id=%s remaining=%s", tracker_id, message_id, len(self.deliveries.get(tracker_id, {})))
            return True

    def enqueue_tracker_event(self, target_tracker_id, event_type, source_tracker_id, payload):
        LOG.info("queueing tracker event type=%s source=%s target=%s payload=%s", event_type, source_tracker_id, target_tracker_id, payload)
        entry = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source_tracker_id": source_tracker_id,
            "target_tracker_id": target_tracker_id,
            "payload": payload or {},
            "created_at": time.time(),
        }
        with self.cv:
            self.tracker_events.setdefault(target_tracker_id, {})[entry["event_id"]] = entry
            self._persist_locked()
            self.cv.notify_all()
            return entry

    def wait_for_tracker_events(self, tracker_id, timeout):
        deadline = time.time() + max(timeout, 0)
        with self.cv:
            while True:
                queue = sorted(self.tracker_events.get(tracker_id, {}).values(), key=lambda item: item.get("created_at", 0))
                if queue:
                    LOG.info("returning %s queued tracker events to tracker_id=%s", len(queue), tracker_id)
                    return [dict(item) for item in queue]
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self.cv.wait(timeout=remaining)

    def ack_tracker_event(self, tracker_id, event_id):
        with self.cv:
            queue = self.tracker_events.get(tracker_id)
            if not queue or event_id not in queue:
                LOG.warning("ack for unknown tracker event tracker_id=%s event_id=%s", tracker_id, event_id)
                return False
            queue.pop(event_id, None)
            LOG.info("acked tracker event tracker_id=%s event_id=%s remaining=%s", tracker_id, event_id, len(queue))
            if not queue:
                self.tracker_events.pop(tracker_id, None)
            self._persist_locked()
            return True


def _validate_attachments(body):
    seen_names = set()
    for att in body.get("attachments") or []:
        safe_name = os.path.basename(att.get("name") or "")
        if not safe_name or "content_b64" not in att:
            return "invalid attachments"
        if safe_name in seen_names:
            return "duplicate attachment name"
        seen_names.add(safe_name)
        try:
            base64.b64decode(att["content_b64"], validate=True)
        except (binascii.Error, ValueError):
            return "invalid attachment payload"
    return None


def make_handler(store=None, token=None, auth_required=None):
    store, token = store or Store(), TOKEN if token is None else token
    auth_required = AUTH_REQUIRED if auth_required is None else auth_required

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def _json(self, code, payload):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(json.dumps(payload).encode())
            except (BrokenPipeError, ConnectionResetError) as e:
                LOG.debug("client disconnected while writing response path=%s error=%s", self.path, e)
            except OSError as e:
                if getattr(e, "errno", None) in (errno.EPIPE, errno.ECONNRESET):
                    LOG.debug("client disconnected while writing response path=%s error=%s", self.path, e)
                    return
                raise

        def _parts(self):
            return [p for p in urlparse(self.path).path.split("/") if p]

        def _body(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > MAX_BODY_BYTES:
                return "__too_large__"
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return None

        def _check(self):
            store.sweep()
            if self.path == "/healthz":
                return True
            if (not auth_required) or (token and self.headers.get("Authorization") == f"Bearer {token}"):
                return True
            self._json(401, {"error": "unauthorized", "message": "invalid or missing token"})
            return False

        def do_GET(self):
            if not self._check():
                return
            if self.path == "/healthz":
                return self._json(200, {"ok": True})
            parts = self._parts()
            query = parse_qs(urlparse(self.path).query)
            agents = store.list_agents()
            if parts == ["trackers"]:
                return self._json(200, {"trackers": store.list_trackers()})
            if parts == ["agents"]:
                for key in ("name", "hostname", "status"):
                    if query.get(key):
                        agents = [agent for agent in agents if agent.get(key) == query[key][0]]
                public_keys = ("agent_id", "name", "aliases", "tracker_id", "hostname", "status", "agent_type", "agent_cmd", "cwd", "last_seen")
                agents = [{k: agent[k] for k in public_keys if k in agent} for agent in agents]
                return self._json(200, {"agents": agents})
            if len(parts) == 2 and parts[0] == "agents":
                agent = store.get_agent(parts[1])
                return self._json(200, agent) if agent else self._json(404, {"error": "agent_not_found", "message": "no agent with that ID is registered"})
            if len(parts) == 3 and parts[0] == "trackers" and parts[2] == "deliveries":
                tracker_id = parts[1]
                if not store.has_tracker(tracker_id):
                    LOG.warning("delivery poll for unknown tracker_id=%s", tracker_id)
                    return self._json(404, {"error": "tracker_not_found", "message": "tracker not registered; call POST /trackers first"})
                wait = min(max(int((query.get("wait") or [DELIVERY_WAIT_SECONDS])[0]), 0), DELIVERY_WAIT_SECONDS)
                return self._json(200, {"deliveries": store.wait_for_deliveries(tracker_id, wait)})
            if len(parts) == 3 and parts[0] == "trackers" and parts[2] == "events":
                tracker_id = parts[1]
                if not store.has_tracker(tracker_id):
                    return self._json(404, {"error": "tracker_not_found", "message": "tracker not registered; call POST /trackers first"})
                wait = min(max(int((query.get("wait") or [DELIVERY_WAIT_SECONDS])[0]), 0), DELIVERY_WAIT_SECONDS)
                return self._json(200, {"events": store.wait_for_tracker_events(tracker_id, wait)})
            self._json(404, {"error": "not_found", "message": "no such endpoint"})

        def do_POST(self):
            if not self._check():
                return
            parts, body = self._parts(), self._body()
            if body == "__too_large__":
                return self._json(413, {"error": "payload_too_large", "message": "request body exceeds limit"})
            if body is None:
                return self._json(400, {"error": "invalid_request", "message": "malformed JSON body"})
            if parts == ["trackers"]:
                if not {"tracker_id", "hostname", "address", "http_port"}.issubset(body):
                    return self._json(400, {"error": "invalid_request", "message": "tracker_id, hostname, address, http_port are required"})
                return self._json(201 if store.put_tracker(body) else 200, {"tracker_id": body["tracker_id"]})
            if len(parts) == 3 and parts[0] == "trackers" and parts[2] in {"heartbeat", "agent-update"}:
                tracker_id = parts[1]
                if not store.has_tracker(tracker_id):
                    LOG.warning("tracker write %s for unknown tracker_id=%s", parts[2], tracker_id)
                    return self._json(404, {"error": "tracker_not_found", "message": "tracker not registered; call POST /trackers first"})
                if parts[2] == "heartbeat":
                    store.heartbeat(tracker_id, body.get("agents", []), body.get("agent_configs", []))
                    return self._json(200, {"ok": True})
                if not {"agent_id", "status"}.issubset(body):
                    return self._json(400, {"error": "invalid_request", "message": "agent_id and status are required"})
                code = store.update_agent(tracker_id, body["agent_id"], body["status"])
                if code == 200:
                    return self._json(200, {"ok": True})
                if code == 403:
                    return self._json(403, {"error": "wrong_tracker", "message": "agent does not belong to this tracker"})
                return self._json(404, {"error": "agent_not_found", "message": "agent not in registry cache; wait for next heartbeat"})
            if len(parts) == 5 and parts[0] == "trackers" and parts[2] == "deliveries" and parts[4] == "ack":
                tracker_id, message_id = parts[1], parts[3]
                if not store.has_tracker(tracker_id):
                    LOG.warning("ack for unknown tracker_id=%s message_id=%s", tracker_id, message_id)
                    return self._json(404, {"error": "tracker_not_found", "message": "tracker not registered; call POST /trackers first"})
                if store.ack_delivery(tracker_id, message_id):
                    return self._json(200, {"ok": True})
                return self._json(404, {"error": "delivery_not_found", "message": "no queued delivery with that message_id"})
            if len(parts) == 5 and parts[0] == "trackers" and parts[2] == "events" and parts[4] == "ack":
                tracker_id, event_id = parts[1], parts[3]
                if not store.has_tracker(tracker_id):
                    return self._json(404, {"error": "tracker_not_found", "message": "tracker not registered; call POST /trackers first"})
                if store.ack_tracker_event(tracker_id, event_id):
                    return self._json(200, {"ok": True})
                return self._json(404, {"error": "event_not_found", "message": "no queued event with that event_id"})
            if parts == ["tracker-events"]:
                required = {"event_type", "source_tracker_id", "target_tracker_id", "payload"}
                if not required.issubset(body) or not isinstance(body.get("payload"), dict):
                    return self._json(400, {"error": "invalid_request", "message": "event_type, source_tracker_id, target_tracker_id, payload object are required"})
                if not store.has_tracker(body["source_tracker_id"]) or not store.has_tracker(body["target_tracker_id"]):
                    return self._json(404, {"error": "tracker_not_found", "message": "source or target tracker not registered"})
                event = store.enqueue_tracker_event(body["target_tracker_id"], body["event_type"], body["source_tracker_id"], body["payload"])
                LOG.info("accepted tracker event event_id=%s type=%s source=%s target=%s", event["event_id"], body["event_type"], body["source_tracker_id"], body["target_tracker_id"])
                return self._json(202, {"ok": True, "event_id": event["event_id"]})
            if parts == ["save-agent"]:
                if not body.get("agent_to_save"):
                    return self._json(400, {"error": "invalid_request", "message": "agent_to_save is required"})
                agent_to_save = body["agent_to_save"]
                agent_name = body.get("agent_name")
                command = body.get("command")
                description = body.get("description")
                cwd = body.get("cwd")
                
                target = store.get_agent(agent_to_save)
                if not target:
                    target = next((agent for agent in store.list_agents() if agent["name"] == agent_to_save or agent_to_save in agent.get("aliases", [])), None)
                
                if not target:
                    return self._json(404, {"error": "agent_not_found", "message": "no agent with that ID or name is registered globally"})
                    
                tracker = store.get_tracker(target["tracker_id"]) or {}
                if tracker.get("status") != "active":
                    return self._json(503, {"error": "tracker_offline", "message": "target tracker is stale or gone", "tracker_status": tracker.get("status", "gone")})
                    
                event = store.enqueue_tracker_event(
                    target["tracker_id"],
                    "save_request",
                    "registry",
                    {
                        "agent_to_save": target["agent_id"],
                        "agent_name": agent_name,
                        "command": command,
                        "description": description,
                        "cwd": cwd
                    }
                )
                return self._json(202, {"ok": True, "queued": True, "event_id": event["event_id"], "target_tracker": target["hostname"]})

            if parts == ["messages"]:
                if not body.get("message") and not body.get("attachments"):
                    return self._json(400, {"error": "invalid_request", "message": "message text or attachments are required"})
                attachment_error = _validate_attachments(body)
                if attachment_error:
                    return self._json(400, {"error": "invalid_request", "message": attachment_error})
                target = store.get_agent(body.get("target_agent_id")) if body.get("target_agent_id") else None
                if not target and body.get("target_agent_name"):
                    if not body.get("target_hostname"):
                        return self._json(400, {"error": "hostname_required", "message": "target_hostname is required when using target_agent_name; bare-name global resolution is not supported"})
                    target = next((agent for agent in store.list_agents() if agent["hostname"] == body["target_hostname"] and (agent["name"] == body["target_agent_name"] or body["target_agent_name"] in agent.get("aliases", []))), None)
                if not target:
                    if body.get("target_agent_name") or body.get("target_agent_id"):
                        LOG.warning("message target not found target_agent_id=%s target_agent_name=%s target_hostname=%s sender_tracker_id=%s", body.get("target_agent_id"), body.get("target_agent_name"), body.get("target_hostname"), body.get("sender_tracker_id"))
                        return self._json(404, {"error": "agent_not_found", "message": "no agent with that ID or name is registered on the specified tracker"})
                    return self._json(400, {"error": "missing_target", "message": "provide target_agent_id or target_agent_name"})
                if body.get("sender_tracker_id") == target["tracker_id"]:
                    return self._json(400, {"error": "same_tracker", "message": "target agent is on the same tracker; use local send"})
                tracker = store.get_tracker(target["tracker_id"]) or {}
                if tracker.get("status") != "active":
                    LOG.warning("message target tracker not active target_tracker_id=%s status=%s target_agent_id=%s", target["tracker_id"], tracker.get("status", "gone"), target["agent_id"])
                    return self._json(503, {"error": "tracker_offline", "message": "target tracker is stale or gone", "tracker_status": tracker.get("status", "gone")})
                entry = store.enqueue_delivery(target["tracker_id"], {
                    "target_agent_id": target["agent_id"],
                    "sender_name": body.get("sender_agent_name", "unknown"),
                    "sender_agent_id": body.get("sender_agent_id"),
                    "sender_tracker": (store.get_tracker(body.get("sender_tracker_id")) or {}).get("hostname", body.get("sender_tracker_id")),
                    "message": body.get("message"),
                    "attachments": body.get("attachments"),
                    "sender_agent_id": body.get("sender_agent_id"),
                    "sender_tracker_id": body.get("sender_tracker_id"),
                    "message_id": body.get("message_id"),
                    "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                })
                return self._json(202, {"ok": True, "queued": True, "message_id": entry["message_id"], "target_agent_id": target["agent_id"], "target_name": target["name"], "target_tracker": target["hostname"]})
            self._json(404, {"error": "not_found", "message": "no such endpoint"})

    return Handler


def serve_forever():
    port = int(os.environ.get("AGENT_REGISTRY_PORT", "8080"))
    LOG.info("starting agent-registry bind=0.0.0.0 port=%s state_path=%s auth_required=%s", port, STATE_PATH, AUTH_REQUIRED)
    ThreadingHTTPServer(("0.0.0.0", port), make_handler()).serve_forever()


if __name__ == "__main__":
    serve_forever()
