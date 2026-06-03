import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import rpc_handler
import state
import config

AUTH_REQUIRED = config.get("registry", "auth_enabled", True)
MAX_BODY_BYTES = config.get("tracker", "max_delivery_bytes", 5242880)

def make_handler(snapshot_fn=state.get_agents_for_registry, token=None, auth_required=None):
    token = config.get("registry", "token", "") if token is None else token
    auth_required = AUTH_REQUIRED if auth_required is None else auth_required
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): return
        def _json(self, code, payload):
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(payload).encode())
        def _authorized(self): return (not auth_required) or (bool(token) and self.headers.get("Authorization") == f"Bearer {token}")
        def _body(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > MAX_BODY_BYTES: return "__too_large__"
            try: return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError: return None
        def do_GET(self):
            if self.path == "/healthz": return self._json(200, {"ok": True})
            if not self._authorized(): return self._json(401, {"error": "unauthorized", "message": "invalid or missing token"})
            if self.path == "/agents": return self._json(200, {"agents": snapshot_fn()})
            return self._json(404, {"error": "not_found", "message": "no such endpoint"})
        def do_POST(self):
            if not self._authorized(): return self._json(401, {"error": "unauthorized", "message": "invalid or missing token"})
            if self.path != "/deliver": return self._json(404, {"error": "not_found", "message": "no such endpoint"})
            body = self._body()
            if body == "__too_large__": return self._json(413, {"error": "payload_too_large", "message": "request body exceeds limit"})
            if body is None: return self._json(400, {"error": "invalid_request", "message": "malformed JSON body"})
            if "target_agent_id" not in body or (not body.get("message") and not body.get("attachments")):
                return self._json(400, {"error": "invalid_request", "message": "target_agent_id and message or attachments are required"})
            try:
                sender = body.get("sender_name", "unknown")
                sender_tracker = body.get("sender_tracker", "unknown")
                rpc_handler.deliver_local_message(body["target_agent_id"], {
                    "sender": f"{sender} (via {sender_tracker})",
                    "timestamp": body.get("sent_at") or rpc_handler._utc_now_isoformat(),
                    "message": body.get("message"),
                    "attachments": body.get("attachments"),
                    "read": False,
                })
                return self._json(200, {"ok": True})
            except rpc_handler.DeliveryTargetNotFound:
                return self._json(404, {"error": "agent_not_found", "message": "no local agent with that ID"})
            except rpc_handler.DeliveryValidationError as e:
                return self._json(400, {"error": "invalid_request", "message": str(e)})
            except RuntimeError as e:
                return self._json(500, {"error": "inbox_error", "message": str(e)})
    return Handler

def serve_forever():
    ThreadingHTTPServer(("0.0.0.0", config.get("tracker", "http_port", 19876)), make_handler()).serve_forever()
