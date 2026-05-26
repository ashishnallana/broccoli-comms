import contextlib
import importlib.util
import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import unittest.mock as mock
from http.server import ThreadingHTTPServer

import http_sidecar
import registry_client
import rpc_handler
import state

_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent-registry", "server.py")
_spec = importlib.util.spec_from_file_location("agent_registry_server", _REGISTRY_PATH)
registry_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(registry_server)


def start(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def get(url, token=None):
    req = urllib.request.Request(url, headers=({"Authorization": f"Bearer {token}"} if token else {}))
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.status, json.loads(resp.read().decode())


def post(url, body, token=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.status, json.loads(resp.read().decode())


class TestHttpAndRegistry(unittest.TestCase):
    def setUp(self):
        state.state = {}
        state.name_index = {}
        state.pane_index = {}
        state.INBOX_DIR = "/tmp/test-agent-http-inboxes"

    def test_sidecar_requires_auth_and_returns_snapshot(self):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1"})
        server, base = start(http_sidecar.make_handler(token="secret", auth_required=True))
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            get(f"{base}/agents")
        self.assertEqual(ctx.exception.code, 401)
        self.assertEqual(get(f"{base}/healthz"), (200, {"ok": True}))
        code, body = get(f"{base}/agents", token="secret")
        self.assertEqual(code, 200)
        self.assertEqual(body["agents"][0]["agent_id"], "id-1")
        self.assertNotIn("tmux_pane", body["agents"][0])

    def test_sidecar_deliver_requires_auth_and_writes_inbox(self):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        if os.path.exists(inbox_path):
            os.remove(inbox_path)
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
        server, base = start(http_sidecar.make_handler(token="secret", auth_required=True))
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(f"{base}/deliver", {"target_agent_id": "id-1", "message": "hello"})
        self.assertEqual(ctx.exception.code, 401)
        with mock.patch("tmux_util.send_keys") as send_keys:
            self.assertEqual(post(f"{base}/deliver", {"target_agent_id": "id-1", "sender_name": "alice", "sender_tracker": "host2", "message": "hello"}, token="secret")[0], 200)
            send_keys.assert_called_once()
        with open(inbox_path, "r") as f:
            self.assertIn("alice (via host2)", f.read())

    def test_registry_register_heartbeat_update_and_gone_sweep(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            server, base = start(registry_server.make_handler(store=store, token="secret"))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            payload = {"tracker_id": "t1", "hostname": "host1", "address": "127.0.0.1", "http_port": 19876, "agents": [{"agent_id": "a1", "name": "agent1", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi", "cwd": "/work/project"}]}
            self.assertEqual(post(f"{base}/trackers", payload, token="secret")[0], 201)
            self.assertEqual(post(f"{base}/trackers/t1/agent-update", {"agent_id": "a1", "status": "working"}, token="secret")[0], 200)
            code, body = get(f"{base}/agents/a1", token="secret")
            self.assertEqual((code, body["status"], body["hostname"], body["cwd"]), (200, "working", "host1", "/work/project"))
            agents = get(f"{base}/agents", token="secret")[1]["agents"]
            self.assertIn("address", body)
            self.assertNotIn("address", agents[0])
            self.assertNotIn("http_port", agents[0])
            self.assertEqual(agents[0]["cwd"], "/work/project")
            self.assertEqual(post(f"{base}/trackers/t1/heartbeat", {"agents": payload["agents"]}, token="secret")[0], 200)
            old_stale, old_gone = registry_server.STALE, registry_server.GONE
            registry_server.STALE, registry_server.GONE = 1, 2
            self.addCleanup(setattr, registry_server, "STALE", old_stale)
            self.addCleanup(setattr, registry_server, "GONE", old_gone)
            store.trackers["t1"]["last_heartbeat"] = time.time() - 5
            self.assertEqual(get(f"{base}/agents", token="secret")[1]["agents"], [])

    def test_registry_long_poll_client_disconnect_has_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            target = {"tracker_id": "t2", "hostname": "host2", "address": "host2", "http_port": 19876, "agents": []}
            store.put_tracker(target)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                server, base = start(registry_server.make_handler(store=store, auth_required=False))
                self.addCleanup(server.shutdown)
                self.addCleanup(server.server_close)
                host, port = "127.0.0.1", server.server_port
                client = socket.create_connection((host, port), timeout=1)
                client.sendall(b"GET /trackers/t2/deliveries?wait=1 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                client.close()
                store.enqueue_delivery("t2", {"target_agent_id": "a2", "message": "hello"})
                time.sleep(0.2)
            self.assertNotIn("BrokenPipeError", stderr.getvalue())
            self.assertNotIn("Exception occurred during processing", stderr.getvalue())

    def test_registry_pane_inputs_default_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            source = {"tracker_id": "t1", "hostname": "host1", "address": "host1", "http_port": 19875, "agents": [{"agent_id": "a1", "name": "agent1", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "host2", "http_port": 19876, "agents": [{"agent_id": "a2", "name": "agent2", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            store.put_tracker(source)
            store.put_tracker(target)
            server, base = start(registry_server.make_handler(store=store, token="secret", remote_pane_input_enabled=False))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "t1", "target_agent_id": "a2", "pane_input_id": "pi-1", "request_id": "req-1", "input_type": "text", "text": "hello"}, token="secret")
            self.assertEqual(ctx.exception.code, 403)
            self.assertEqual(store.wait_for_deliveries("t2", 0), [])

    def test_registry_pane_inputs_validate_queue_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "registry-state.json")
            store = registry_server.Store(state_path=state_path)
            source = {"tracker_id": "t1", "hostname": "host1", "address": "host1", "http_port": 19875, "agents": [{"agent_id": "a1", "name": "agent1", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "host2", "http_port": 19876, "agents": [{"agent_id": "a2", "name": "agent2", "aliases": ["alias2"], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            store.put_tracker(source)
            store.put_tracker(target)
            server, base = start(registry_server.make_handler(store=store, token="secret", remote_pane_input_enabled=True))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            payload = {
                "sender_tracker_id": "t1",
                "sender_agent_id": "a1",
                "sender_agent_name": "agent1",
                "target_hostname": "host2",
                "target_agent_name": "alias2",
                "pane_input_id": "pi-1",
                "request_id": "req-1",
                "input_type": "keys",
                "keys": ["ctrl-c", "Enter"],
            }
            code, body = post(f"{base}/pane-inputs", payload, token="secret")
            self.assertEqual(code, 202)
            self.assertEqual(body["pane_input_id"], "pi-1")
            reloaded = registry_server.Store(state_path=state_path)
            delivery = reloaded.wait_for_deliveries("t2", 0)[0]
            self.assertEqual(delivery["delivery_type"], "pane_input")
            self.assertEqual(delivery["message_id"], "pi-1")
            self.assertEqual(delivery["request_id"], "req-1")
            self.assertEqual(delivery["target_agent_id"], "a2")
            self.assertEqual(delivery["keys"], ["C-c", "Enter"])
            self.assertNotIn("message", delivery)

    def test_registry_pane_inputs_reject_invalid_same_tracker_and_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            source = {"tracker_id": "t1", "hostname": "host1", "address": "host1", "http_port": 19875, "agents": [{"agent_id": "a1", "name": "agent1", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "host2", "http_port": 19876, "agents": [{"agent_id": "a2", "name": "agent2", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            store.put_tracker(source)
            store.put_tracker(target)
            server, base = start(registry_server.make_handler(store=store, token="secret", remote_pane_input_enabled=True))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "t1", "target_agent_name": "agent2", "pane_input_id": "pi-1", "request_id": "req-1", "input_type": "text", "text": "hello"}, token="secret")
            self.assertEqual(ctx.exception.code, 400)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "t1", "target_agent_id": "a2", "pane_input_id": ["bad"], "request_id": "req-list", "input_type": "text", "text": "hello"}, token="secret")
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(store.wait_for_deliveries("t2", 0), [])
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "t1", "target_agent_id": "a2", "pane_input_id": "   ", "request_id": "req-blank", "input_type": "text", "text": "hello"}, token="secret")
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(store.wait_for_deliveries("t2", 0), [])
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "missing", "target_agent_id": "a2", "pane_input_id": "pi-missing", "request_id": "req-missing", "input_type": "text", "text": "hello"}, token="secret")
            self.assertEqual(ctx.exception.code, 404)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "t2", "target_agent_id": "a2", "pane_input_id": "pi-2", "request_id": "req-2", "input_type": "text", "text": "hello"}, token="secret")
            self.assertEqual(ctx.exception.code, 400)
            store.trackers["t2"]["last_heartbeat"] = time.time() - 100
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "t1", "target_agent_id": "a2", "pane_input_id": "pi-3", "request_id": "req-3", "input_type": "text", "text": "hello"}, token="secret")
            self.assertEqual(ctx.exception.code, 503)
            store.trackers["t2"]["last_heartbeat"] = time.time()
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/pane-inputs", {"sender_tracker_id": "t1", "target_agent_id": "a2", "pane_input_id": "pi-4", "request_id": "req-4", "input_type": "keys", "keys": ["bad;key"]}, token="secret")
            self.assertEqual(ctx.exception.code, 400)

    def test_registry_messages_queue_ack_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "registry-state.json")
            store = registry_server.Store(state_path=state_path)
            source = {"tracker_id": "t1", "hostname": "host1", "address": "host1", "http_port": 19875, "agents": [{"agent_id": "a1", "name": "agent1", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "host2", "http_port": 19876, "agents": [{"agent_id": "a2", "name": "agent2", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            store.put_tracker(source)
            store.put_tracker(target)
            server, base = start(registry_server.make_handler(store=store, token="secret"))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            code, body = post(f"{base}/messages", {"sender_tracker_id": "t1", "sender_agent_name": "agent1", "target_agent_id": "a2", "message": "hello"}, token="secret")
            self.assertEqual(code, 202)
            message_id = body["message_id"]
            reloaded = registry_server.Store(state_path=state_path)
            self.assertEqual(reloaded.wait_for_deliveries("t2", 0)[0]["message_id"], message_id)
            code, deliveries = get(f"{base}/trackers/t2/deliveries?wait=0", token="secret")
            self.assertEqual(code, 200)
            self.assertEqual(deliveries["deliveries"][0]["message_id"], message_id)
            self.assertEqual(deliveries["deliveries"][0]["message"], "hello")
            self.assertEqual(post(f"{base}/trackers/t2/deliveries/{message_id}/ack", {}, token="secret")[0], 200)
            self.assertEqual(get(f"{base}/trackers/t2/deliveries?wait=0", token="secret")[1]["deliveries"], [])

    def test_registry_tracker_events_queue_ack_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "registry-state.json")
            store = registry_server.Store(state_path=state_path)
            source = {"tracker_id": "t1", "hostname": "host1", "address": "host1", "http_port": 19875, "agents": []}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "host2", "http_port": 19876, "agents": []}
            store.put_tracker(source)
            store.put_tracker(target)
            server, base = start(registry_server.make_handler(store, token="secret"))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)

            code, body = post(f"{base}/tracker-events", {"event_type": "message_read", "source_tracker_id": "t1", "target_tracker_id": "t2", "payload": {"message_id": "m1"}}, token="secret")
            self.assertEqual(code, 202)
            event_id = body["event_id"]
            reloaded = registry_server.Store(state_path=state_path)
            self.assertEqual(reloaded.wait_for_tracker_events("t2", 0)[0]["event_id"], event_id)
            code, events = get(f"{base}/trackers/t2/events?wait=0", token="secret")
            self.assertEqual(code, 200)
            self.assertEqual(events["events"][0]["payload"]["message_id"], "m1")
            self.assertEqual(post(f"{base}/trackers/t2/events/{event_id}/ack", {}, token="secret")[0], 200)
            self.assertEqual(get(f"{base}/trackers/t2/events?wait=0", token="secret")[1]["events"], [])

    def test_registry_messages_auth_same_tracker_offline_and_attachment_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            source = {"tracker_id": "t1", "hostname": "host1", "address": "host1", "http_port": 19875, "agents": [{"agent_id": "a1", "name": "agent1", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "host2", "http_port": 19876, "agents": [{"agent_id": "a2", "name": "agent2", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]}
            store.put_tracker(source)
            store.put_tracker(target)
            server, base = start(registry_server.make_handler(store=store, token="secret", auth_required=True))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/messages", {"sender_tracker_id": "t1", "target_agent_id": "a2", "message": "hi"})
            self.assertEqual(ctx.exception.code, 401)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/messages", {"sender_tracker_id": "t2", "target_agent_id": "a2", "message": "hi"}, token="secret")
            self.assertEqual(ctx.exception.code, 400)
            store.trackers["t2"]["last_heartbeat"] = time.time() - 100
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/messages", {"sender_tracker_id": "t1", "target_agent_id": "a2", "message": "hi"}, token="secret")
            self.assertEqual(ctx.exception.code, 503)
            store.trackers["t2"]["last_heartbeat"] = time.time()
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(f"{base}/messages", {"sender_tracker_id": "t1", "target_agent_id": "a2", "message": "hi", "attachments": [{"name": "bad.txt", "content_b64": "%%%"}]}, token="secret")
            self.assertEqual(ctx.exception.code, 400)

    def test_registry_client_delivery_loop_delivers_and_acks(self):
        delivery = {
            "message_id": "m1",
            "target_agent_id": "a2",
            "sender_name": "agent1",
            "sender_tracker": "host1",
            "message": "hello",
            "sent_at": "2026-05-17T00:00:00+00:00",
        }
        with mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch("rpc_handler.deliver_local_message") as deliver:
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        deliver.assert_called_once()
        ack.assert_called_once_with("m1")

    def test_registry_client_delivery_loop_retries_missing_target_until_available(self):
        delivery = {
            "message_id": "m1",
            "target_agent_id": "a2",
            "sender_name": "agent1",
            "sender_tracker": "host1",
            "message": "hello",
            "sent_at": "2026-05-17T00:00:00+00:00",
        }
        with mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), (200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch.object(registry_client, "DELIVERY_TARGET_GRACE_SECONDS", 60), \
             mock.patch.object(registry_client.time, "sleep") as sleep, \
             mock.patch.object(registry_client.time, "time", return_value=100.0), \
             mock.patch("rpc_handler.deliver_local_message", side_effect=[rpc_handler.DeliveryTargetNotFound("not recovered yet"), "agent2"]) as deliver:
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        self.assertEqual(deliver.call_count, 2)
        ack.assert_called_once_with("m1")
        sleep.assert_called_once_with(2)

    def test_registry_client_delivery_loop_acks_missing_target_after_grace(self):
        delivery = {
            "message_id": "m1",
            "target_agent_id": "a2",
            "sender_name": "agent1",
            "sender_tracker": "host1",
            "message": "hello",
            "sent_at": "2026-05-17T00:00:00+00:00",
        }
        with mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), (200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch.object(registry_client, "DELIVERY_TARGET_GRACE_SECONDS", 60), \
             mock.patch.object(registry_client.time, "sleep") as sleep, \
             mock.patch.object(registry_client.time, "time", side_effect=[100.0, 200.0]), \
             mock.patch("rpc_handler.deliver_local_message", side_effect=rpc_handler.DeliveryTargetNotFound("gone")):
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        ack.assert_called_once_with("m1")
        sleep.assert_called_once_with(2)

    def test_registry_client_delivery_loop_acks_invalid_delivery_immediately(self):
        delivery = {
            "message_id": "m1",
            "target_agent_id": "a2",
            "sender_name": "agent1",
            "sender_tracker": "host1",
            "message": "hello",
            "sent_at": "2026-05-17T00:00:00+00:00",
        }
        with mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch.object(registry_client.time, "sleep") as sleep, \
             mock.patch("rpc_handler.deliver_local_message", side_effect=rpc_handler.DeliveryValidationError("bad attachment")):
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        ack.assert_called_once_with("m1")
        sleep.assert_not_called()

    def test_registry_client_delivery_loop_does_not_ack_transient_failures(self):
        delivery = {
            "message_id": "m1",
            "target_agent_id": "a2",
            "sender_name": "agent1",
            "sender_tracker": "host1",
            "message": "hello",
            "sent_at": "2026-05-17T00:00:00+00:00",
        }
        with mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch.object(registry_client.time, "sleep"), \
             mock.patch("rpc_handler.deliver_local_message", side_effect=RuntimeError("disk full")):
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        ack.assert_not_called()

    def test_registry_client_delivery_loop_dispatches_pane_input_and_acks_after_injection(self):
        delivery = {
            "delivery_type": "pane_input",
            "message_id": "pi-1",
            "pane_input_id": "pi-1",
            "request_id": "req-1",
            "target_agent_id": "a2",
            "input_type": "text",
            "text": "hello",
            "submit": False,
        }
        with mock.patch.dict(os.environ, {"AGENT_TRACKER_REMOTE_PANE_INPUT_RECEIVE_ENABLED": "1"}, clear=True), \
             mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch.object(state, "pane_input_was_applied", return_value=False) as was_applied, \
             mock.patch.object(state, "mark_pane_input_applied") as mark_applied, \
             mock.patch("rpc_handler.handle_send_input", return_value={"success": True}):
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        was_applied.assert_called_once_with("req-1")
        mark_applied.assert_called_once_with("req-1", "pi-1", "a2")
        ack.assert_called_once_with("pi-1")

    def test_registry_client_delivery_loop_acks_duplicate_pane_input_without_injecting(self):
        delivery = {
            "delivery_type": "pane_input",
            "message_id": "pi-1",
            "pane_input_id": "pi-1",
            "request_id": "req-1",
            "target_agent_id": "a2",
            "input_type": "keys",
            "keys": ["Enter"],
        }
        with mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch.object(state, "pane_input_was_applied", return_value=True), \
             mock.patch("rpc_handler.handle_send_input") as send_input:
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        send_input.assert_not_called()
        ack.assert_called_once_with("pi-1")

    def test_registry_client_delivery_loop_does_not_ack_pane_input_transient_failure(self):
        delivery = {
            "delivery_type": "pane_input",
            "message_id": "pi-1",
            "pane_input_id": "pi-1",
            "request_id": "req-1",
            "target_agent_id": "a2",
            "input_type": "text",
            "text": "hello",
        }
        with mock.patch.dict(os.environ, {"AGENT_TRACKER_REMOTE_PANE_INPUT_RECEIVE_ENABLED": "1"}, clear=True), \
             mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery") as ack, \
             mock.patch.object(registry_client.time, "sleep"), \
             mock.patch.object(state, "pane_input_was_applied", return_value=False), \
             mock.patch("rpc_handler.handle_send_input", side_effect=RuntimeError("tmux down")):
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        ack.assert_not_called()

    def test_handle_pane_input_delivery_injects_without_inbox_or_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dedupe = state.PANE_INPUT_DEDUPE_PATH
            state.PANE_INPUT_DEDUPE_PATH = os.path.join(tmp, "dedupe.json")
            self.addCleanup(setattr, state, "PANE_INPUT_DEDUPE_PATH", old_dedupe)
            state.set_agent("agent2", {"agent_id": "a2", "status": "idle", "tmux_pane": "%2", "tmux_socket": "sock"})
            inbox_path = os.path.join(state.INBOX_DIR, "a2.inbox")
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            delivery = {
                "delivery_type": "pane_input",
                "message_id": "pi-1",
                "pane_input_id": "pi-1",
                "request_id": "req-1",
                "target_agent_id": "a2",
                "input_type": "text",
                "text": "hello",
                "submit": True,
            }
            with mock.patch.dict(os.environ, {"AGENT_TRACKER_REMOTE_PANE_INPUT_RECEIVE_ENABLED": "1"}, clear=True), \
                 mock.patch("tmux_util.send_literal_text") as send_literal, \
                 mock.patch("tmux_util.send_keys") as notify_send_keys:
                result = registry_client._handle_pane_input_delivery(delivery)
            self.assertEqual(result, "injected")
            send_literal.assert_called_once_with("%2", "hello", submit=True, socket_path="sock")
            notify_send_keys.assert_not_called()
            self.assertFalse(os.path.exists(inbox_path))
            self.assertTrue(state.pane_input_was_applied("req-1"))

    def test_registry_client_redelivery_after_write_before_ack_is_deduped(self):
        inbox_path = os.path.join(state.INBOX_DIR, "a2.inbox")
        if os.path.exists(inbox_path):
            os.remove(inbox_path)
        state.set_agent("agent2", {"agent_id": "a2", "status": "idle", "tmux_pane": "%2", "tmux_socket": "sock"})
        delivery = {
            "message_id": "m1",
            "target_agent_id": "a2",
            "sender_name": "agent1",
            "sender_tracker": "host1",
            "message": "hello",
            "sent_at": "2026-05-17T00:00:00+00:00",
        }
        with mock.patch.object(registry_client, "fetch_deliveries", side_effect=[(200, {"deliveries": [delivery]}), (200, {"deliveries": [delivery]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_delivery", side_effect=[None, 200]) as ack, \
             mock.patch("tmux_util.send_keys"):
            with self.assertRaises(SystemExit):
                registry_client._delivery_loop()
        self.assertEqual(ack.call_count, 2)
        with open(inbox_path, "r") as f:
            lines = [line for line in f if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["message_id"], "m1")

    def test_registry_client_heartbeat_reregisters_on_404(self):
        with mock.patch.object(registry_client, "register") as register, \
             mock.patch.object(registry_client, "heartbeat", side_effect=[404]), \
             mock.patch.object(registry_client.time, "sleep", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                registry_client._heartbeat_loop()
        self.assertEqual(register.call_count, 2)

    def test_registry_remote_save_triggers_tracker_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "registry-state.json")
            store = registry_server.Store(state_path=state_path)
            target = {
                "tracker_id": "t2",
                "hostname": "host2",
                "address": "host2",
                "http_port": 19876,
                "agents": [{"agent_id": "a2", "name": "agent2", "aliases": [], "status": "idle", "agent_type": "pi", "agent_cmd": "pi"}]
            }
            store.put_tracker(target)
            server, base = start(registry_server.make_handler(store, token="secret"))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)

            code, body = post(
                f"{base}/save-agent",
                {
                    "agent_to_save": "agent2",
                    "agent_name": "agent2-saved-config",
                    "command": "pi custom --args",
                    "description": "custom desc",
                    "cwd": "/custom/cwd"
                },
                token="secret"
            )
            self.assertEqual(code, 202)
            self.assertTrue(body["queued"])
            self.assertEqual(body["target_tracker"], "host2")
            
            code, events = get(f"{base}/trackers/t2/events?wait=0", token="secret")
            self.assertEqual(code, 200)
            self.assertEqual(len(events["events"]), 1)
            event = events["events"][0]
            self.assertEqual(event["event_type"], "save_request")
            self.assertEqual(event["payload"]["agent_to_save"], "a2")
            self.assertEqual(event["payload"]["agent_name"], "agent2-saved-config")
            self.assertEqual(event["payload"]["command"], "pi custom --args")
            self.assertEqual(event["payload"]["description"], "custom desc")
            self.assertEqual(event["payload"]["cwd"], "/custom/cwd")

    def test_registry_client_event_loop_handles_save_request(self):
        event = {
            "event_id": "e1",
            "event_type": "save_request",
            "payload": {
                "agent_to_save": "a2",
                "agent_name": "agent2-saved-config",
                "command": "pi custom --args",
                "description": "custom desc",
                "cwd": "/custom/cwd"
            }
        }
        with mock.patch.object(registry_client, "fetch_events", side_effect=[(200, {"events": [event]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_event") as ack, \
             mock.patch.object(registry_client, "_handle_remote_save") as handle_save, \
             mock.patch.object(registry_client, "register") as register, \
             mock.patch("registry_client.time.sleep") as sleep:
            with self.assertRaises(SystemExit):
                registry_client._event_loop()
        
        handle_save.assert_called_once_with("a2", "agent2-saved-config", "pi custom --args", "custom desc", "/custom/cwd")
        register.assert_called_once()
        ack.assert_called_once_with("e1")

    def test_handle_remote_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            def side_effect(path):
                if path == "~":
                    return tmp
                return path
            with mock.patch("os.path.expanduser", side_effect=side_effect):
                state.state = {
                    "a2": {
                        "agent_id": "a2",
                        "name": "agent2",
                        "aliases": [],
                        "status": "idle",
                        "agent_type": "pi",
                        "agent_cmd": "pi --foo bar",
                        "cwd": f"{tmp}/my-project"
                    }
                }
                state.name_index = {"agent2": "a2"}
                
                registry_client._handle_remote_save("agent2", "agent2-saved-config", "pi custom --args", "custom desc", f"{tmp}/custom-cwd")
                
                config_path = os.path.join(tmp, ".config", "agent-tracker", "agents", "agent2-saved-config", "config.json")
                self.assertTrue(os.path.isfile(config_path))
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                
                self.assertEqual(cfg["directory"], f"{tmp}/custom-cwd")
                self.assertEqual(cfg["agent-command"], "pi")
                self.assertEqual(cfg["agent-args"], ["custom", "--args"])
                self.assertEqual(cfg["description"], "custom desc")

    def test_registry_watch_leases_queue_and_fanout(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            
            # Register source tracker t1 and target tracker t2
            source = {"tracker_id": "t1", "hostname": "host1", "address": "127.0.0.1", "http_port": 19875, "agents": []}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "127.0.0.1", "http_port": 19876, "agents": [{"agent_id": "a2", "name": "agent2", "aliases": [], "status": "idle"}]}
            store.put_tracker(source)
            store.put_tracker(target)
            
            server, base = start(registry_server.make_handler(store, token="secret"))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            
            # Register a remote watch lease for client_win_1 from source t1 watching agent2 on host2
            lease_payload = {
                "client_id": "client_win_1",
                "watch_targets": ["host2/agent2"],
                "lease_seconds": 10.0
            }
            code, body = post(f"{base}/trackers/t1/watch-leases", lease_payload, token="secret")
            self.assertEqual(code, 200)
            
            # Verify watch lease registered inside store
            self.assertIn("t2", store.remote_watch_leases)
            self.assertIn(("t1", "client_win_1"), store.remote_watch_leases["t2"])
            
            # Enqueue a message delivery for target agent2 on target t2. This should trigger event fanout!
            msg_payload = {
                "sender_tracker_id": "t1",
                "sender_agent_name": "agent1",
                "target_agent_id": "a2",
                "message": "hello remote world"
            }
            code, body = post(f"{base}/messages", msg_payload, token="secret")
            self.assertEqual(code, 202)
            
            # Watcher tracker t1 should have received a remote_agent_event tracker event queued!
            code, events = get(f"{base}/trackers/t1/events?wait=0", token="secret")
            self.assertEqual(code, 200)
            self.assertEqual(len(events["events"]), 1)
            event = events["events"][0]
            self.assertEqual(event["event_type"], "remote_agent_event")
            self.assertEqual(event["payload"]["sender"], "agent1")
            self.assertEqual(event["payload"]["message"], "hello remote world")
            self.assertEqual(event["payload"]["target_agent_name"], "host2/agent2")
            
            # Clear watch lease
            req = urllib.request.Request(f"{base}/trackers/t1/watch-leases/client_win_1", headers={"Authorization": "Bearer secret"}, method="DELETE")
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                
            # Verify cleared
            self.assertNotIn(("t1", "client_win_1"), store.remote_watch_leases.get("t2", {}))

    def test_registry_broad_watch_policy_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            
            source = {"tracker_id": "t1", "hostname": "host1", "address": "127.0.0.1", "http_port": 19875, "agents": []}
            store.put_tracker(source)
            
            server, base = start(registry_server.make_handler(store, token="secret", remote_pane_input_enabled=False))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            
            old_allowed = registry_server.AGENT_REGISTRY_BROAD_WATCH_ALLOWED
            try:
                registry_server.AGENT_REGISTRY_BROAD_WATCH_ALLOWED = False
                
                lease_payload = {
                    "client_id": "client_win_1",
                    "watch_targets": ["host2/agent2"],
                    "scope": "broad",
                    "lease_seconds": 10.0
                }
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post(f"{base}/trackers/t1/watch-leases", lease_payload, token="secret")
                self.assertEqual(ctx.exception.code, 403)
                self.assertNotIn("t2", store.remote_watch_leases)
            finally:
                registry_server.AGENT_REGISTRY_BROAD_WATCH_ALLOWED = old_allowed

    def test_registry_narrow_watchlist_blocks_passive_broad_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = registry_server.Store(state_path=os.path.join(tmp, "registry-state.json"))
            
            source = {"tracker_id": "t1", "hostname": "host1", "address": "127.0.0.1", "http_port": 19875, "agents": []}
            target = {"tracker_id": "t2", "hostname": "host2", "address": "127.0.0.1", "http_port": 19876, "agents": [{"agent_id": "a2", "name": "agent2", "aliases": [], "status": "idle"}]}
            store.put_tracker(source)
            store.put_tracker(target)
            
            server, base = start(registry_server.make_handler(store, token="secret"))
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            
            lease_payload = {
                "client_id": "client_win_1",
                "watch_targets": ["host2/agent2"],
                "scope": "narrow",
                "lease_seconds": 10.0
            }
            code, body = post(f"{base}/trackers/t1/watch-leases", lease_payload, token="secret")
            self.assertEqual(code, 200)
            
            msg_payload = {
                "sender_tracker_id": "t3",
                "sender_agent_name": "agent3",
                "target_agent_id": "a2",
                "message": "passive observation text"
            }
            code, body = post(f"{base}/messages", msg_payload, token="secret")
            self.assertEqual(code, 202)
            
            code, events = get(f"{base}/trackers/t1/events?wait=0", token="secret")
            self.assertEqual(code, 200)
            self.assertEqual(events["events"], [])


if __name__ == "__main__":
    unittest.main()
