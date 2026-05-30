import datetime
import json
import os
import threading
import time
import unittest
from unittest import mock

import registry_client
import rpc_handler
import state


class TestRpcHandler(unittest.TestCase):
    def setUp(self):
        state.state = {}
        state.name_index = {}
        state.pane_index = {}
        state.events = []
        state.event_sequence_id = 0
        state.INBOX_DIR = "/tmp/test-agent-inboxes"

    @mock.patch("tmux_util.set_agent_no_registry")
    @mock.patch("tmux_util.set_agent_no_notify_with_send_keys")
    @mock.patch("tmux_util.set_agent_cmd")
    @mock.patch("tmux_util.set_agent_type")
    @mock.patch("tmux_util.set_agent_name")
    @mock.patch("tmux_util.set_pane_title")
    @mock.patch("tmux_util.set_agent_uuid")
    @mock.patch("tmux_util.set_agent_id")
    def test_register_same_agent_id_preserves_runtime_state(self, _set_agent_id, _set_agent_uuid, _set_pane_title, _set_agent_name, _set_agent_type, _set_agent_cmd, _set_agent_no_notify, _set_agent_no_registry):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "working",
                "waiting_approval": True,
                "pending_notifications": ["peer-agent"],
                "pid": 12345,
                "session": "old-session",
                "tmux_pane": "%1",
                "tmux_socket": "old-sock",
                "wrapper_pid": 111,
                "agent_type": "pi",
                "agent_cmd": "pi",
            },
        )

        name = rpc_handler.handle_register(
            {
                "session": "new-session",
                "tmux_pane": "%2",
                "wrapper_pid": 222,
                "tmux_socket": "new-sock",
                "name": "agent1",
                "agent_type": "pi",
                "agent_cmd": "pi",
                "agent_id": "id-1",
            }
        )

        self.assertEqual(name, "agent1")
        info = state.get_agent("agent1")
        self.assertEqual(info["agent_id"], "id-1")
        self.assertEqual(info["status"], "working")
        self.assertTrue(info["waiting_approval"])
        self.assertEqual(info["pending_notifications"], ["peer-agent"])
        self.assertEqual(info["pid"], 12345)
        self.assertEqual(info["session"], "new-session")
        self.assertEqual(info["tmux_pane"], "%2")
        self.assertEqual(info["tmux_socket"], "new-sock")
        self.assertEqual(info["wrapper_pid"], 222)
        self.assertEqual(info["model_type"], "pi")
        self.assertFalse(info.get("no_notify_with_send_keys", False))
        self.assertFalse(info.get("no_registry", False))
        self.assertIn("last_heartbeat", info)
        self.assertEqual(len(state.state), 1)
        self.assertEqual(state.events[-1]["type"], "agent_registered")
        self.assertEqual(state.events[-1]["target_agent_id"], "id-1")

    def test_handle_list_includes_local_metadata_and_model_type(self):
        with mock.patch.object(registry_client, "HOSTNAME", "test-host"), mock.patch.object(registry_client, "TRACKER_ID", "tracker-1"):
            state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "agent_type": "codex", "agent_cmd": "codex"})
            result = rpc_handler.handle_list({})
        self.assertEqual(result["agent1"]["scope"], "local")
        self.assertEqual(result["agent1"]["hostname"], "test-host")
        self.assertEqual(result["agent1"]["tracker_id"], "tracker-1")
        self.assertEqual(result["agent1"]["target_address"], "agent1")
        self.assertEqual(result["agent1"]["model_type"], "codex")

    def test_get_inbox_missing_agent_has_structured_error_data(self):
        with self.assertRaises(rpc_handler.RPCStructuredError) as ctx:
            rpc_handler.handle_get_inbox({"agent_name": "missing"})
        self.assertEqual(ctx.exception.code, -32004)
        self.assertEqual(ctx.exception.data["error_code"], "agent_not_found")
        self.assertEqual(ctx.exception.data["operation"], "get_inbox")
        self.assertTrue(ctx.exception.data["retryable"])

    @mock.patch("tmux_util.set_pane_title")
    @mock.patch("tmux_util.set_agent_no_registry")
    @mock.patch("tmux_util.set_agent_no_notify_with_send_keys")
    @mock.patch("tmux_util.set_agent_cmd")
    @mock.patch("tmux_util.set_agent_type")
    @mock.patch("tmux_util.set_agent_name")
    @mock.patch("tmux_util.set_agent_uuid")
    @mock.patch("tmux_util.set_agent_id")
    def test_register_persists_restart_recovery_tmux_metadata(
        self,
        set_agent_id,
        set_agent_uuid,
        set_agent_name,
        set_agent_type,
        set_agent_cmd,
        set_agent_no_notify,
        set_agent_no_registry,
        set_pane_title,
    ):
        name = rpc_handler.handle_register(
            {
                "session": "sess",
                "tmux_pane": "%9",
                "wrapper_pid": 999,
                "tmux_socket": "sock",
                "name": "agent9",
                "agent_type": "pi",
                "agent_cmd": "pi",
                "agent_id": "id-9",
            }
        )

        self.assertEqual(name, "agent9")
        set_agent_id.assert_called_once_with("%9", "id-9", "sock")
        set_agent_uuid.assert_called_once_with("%9", "id-9", "sock")
        set_agent_name.assert_called_once_with("%9", "agent9", "sock")
        set_agent_type.assert_called_once_with("%9", "pi", "sock")
        set_agent_cmd.assert_called_once_with("%9", "pi", "sock")
        set_agent_no_notify.assert_called_once_with("%9", False, "sock")
        set_agent_no_registry.assert_called_once_with("%9", False, "sock")
        set_pane_title.assert_called_once_with("%9", "agent9", "sock")

    @mock.patch("tmux_util.set_pane_title")
    @mock.patch("tmux_util.set_agent_no_registry")
    @mock.patch("tmux_util.set_agent_no_notify_with_send_keys")
    @mock.patch("tmux_util.set_agent_cmd")
    @mock.patch("tmux_util.set_agent_type")
    @mock.patch("tmux_util.set_agent_name")
    @mock.patch("tmux_util.set_agent_uuid")
    @mock.patch("tmux_util.set_agent_id")
    def test_register_stores_no_registry_and_no_notify_flags(
        self,
        _set_agent_id,
        _set_agent_uuid,
        _set_agent_name,
        _set_agent_type,
        _set_agent_cmd,
        set_agent_no_notify,
        set_agent_no_registry,
        _set_pane_title,
    ):
        name = rpc_handler.handle_register({
            "session": "sess",
            "tmux_pane": "%9",
            "wrapper_pid": 999,
            "tmux_socket": "sock",
            "name": "agent9",
            "agent_type": "pi",
            "agent_cmd": "pi",
            "agent_id": "id-9",
            "no_notify_with_send_keys": True,
            "no_registry": True,
            "cwd": "/work/project",
        })
        self.assertEqual(name, "agent9")
        info = state.get_agent("agent9")
        self.assertTrue(info["no_notify_with_send_keys"])
        self.assertTrue(info["no_registry"])
        self.assertEqual(info["cwd"], "/work/project")
        set_agent_no_notify.assert_called_once_with("%9", True, "sock")
        set_agent_no_registry.assert_called_once_with("%9", True, "sock")

    @mock.patch("rpc_handler.time.time", return_value=123.0)
    @mock.patch("tmux_util.set_agent_no_registry")
    @mock.patch("tmux_util.set_agent_no_notify_with_send_keys")
    @mock.patch("tmux_util.set_agent_cmd")
    @mock.patch("tmux_util.set_agent_type")
    @mock.patch("tmux_util.set_agent_name")
    @mock.patch("tmux_util.set_pane_title")
    @mock.patch("tmux_util.set_agent_uuid")
    @mock.patch("tmux_util.set_agent_id")
    @mock.patch("state.discover_agent_process", return_value=None)
    @mock.patch("tmux_util.get_pane_info", return_value={"tty": "/dev/pts/1", "session": "sess", "pid": 101})
    @mock.patch("tmux_util.list_panes", return_value=[{
        "pane_id": "%1",
        "agent_name": "agent1",
        "agent_id": "id-1",
        "agent_uuid": "id-1",
        "agent_type": "pi",
        "agent_cmd": "pi",
        "no_notify_with_send_keys": True,
        "no_registry": True,
        "pane_active": False,
    }])
    def test_register_clears_recovered_at_after_recovery(
        self,
        _list_panes,
        _get_pane_info,
        _discover_agent_process,
        _set_agent_id,
        _set_agent_uuid,
        _set_pane_title,
        _set_agent_name,
        _set_agent_type,
        _set_agent_cmd,
        _set_agent_no_notify,
        _set_agent_no_registry,
        _time,
    ):
        state.init_state()
        recovered = state.get_agent("agent1")
        self.assertEqual(recovered["status"], "unknown")
        self.assertTrue(recovered["no_notify_with_send_keys"])
        self.assertTrue(recovered["no_registry"])
        self.assertIsNotNone(recovered["recovered_at"])

        rpc_handler.handle_register(
            {
                "session": "new-session",
                "tmux_pane": "%2",
                "wrapper_pid": 222,
                "tmux_socket": "new-sock",
                "name": "agent1",
                "agent_type": "pi",
                "agent_cmd": "pi",
                "agent_id": "id-1",
            }
        )

        info = state.get_agent("agent1")
        self.assertEqual(info["tmux_pane"], "%2")
        self.assertEqual(info["wrapper_pid"], 222)
        self.assertEqual(info["last_heartbeat"], 123.0)
        self.assertFalse(info["no_notify_with_send_keys"])
        self.assertFalse(info["no_registry"])
        self.assertIsNone(info["recovered_at"])

    @mock.patch("rpc_handler.time.time", return_value=456.0)
    def test_heartbeat_clears_recovered_at(self, _time):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "unknown",
                "recovered_at": 100.0,
            },
        )

        self.assertTrue(rpc_handler.handle_heartbeat({"agent_id": "id-1"}))

        info = state.get_agent("agent1")
        self.assertEqual(info["last_heartbeat"], 456.0)
        self.assertIsNone(info["recovered_at"])

    @mock.patch("tmux_util.set_agent_uuid")
    @mock.patch("tmux_util.set_agent_id")
    @mock.patch("state.discover_agent_process", return_value=None)
    @mock.patch("tmux_util.get_pane_info", return_value={"tty": "/dev/pts/1", "session": "sess", "pid": 101})
    @mock.patch("tmux_util.list_panes", return_value=[{
        "pane_id": "%1",
        "agent_name": "agent2",
        "agent_id": "id-1",
        "agent_uuid": "id-1",
        "agent_type": "pi",
        "agent_cmd": "pi",
        "pane_active": False,
    }])
    @mock.patch("subprocess.run")
    @mock.patch("tmux_util.set_pane_title_sync")
    @mock.patch("tmux_util.set_agent_name_sync")
    def test_recovery_prefers_tmux_name_over_stale_register_name(
        self,
        _set_agent_name_sync,
        _set_pane_title_sync,
        _subprocess_run,
        _list_panes,
        _get_pane_info,
        _discover_agent_process,
        _set_agent_id,
        _set_agent_uuid,
    ):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "idle",
                "tmux_pane": "%1",
                "tmux_socket": "sock",
            },
        )
        self.assertTrue(rpc_handler.handle_rename({"old_name": "agent1", "new_name": "agent2", "force": True}))
        self.assertIsNotNone(state.get_agent("agent2"))

        state.state = {}
        state.name_index = {}
        state.init_state()
        self.assertIsNotNone(state.get_agent("agent2"))

        assigned_name = rpc_handler.handle_register(
            {
                "session": "new-session",
                "tmux_pane": "%2",
                "wrapper_pid": 222,
                "tmux_socket": "new-sock",
                "name": "agent1",
                "agent_type": "pi",
                "agent_cmd": "pi",
                "agent_id": "id-1",
            }
        )

        self.assertEqual(assigned_name, "agent2")
        self.assertIsNone(state.get_agent("agent1"))
        info = state.get_agent("agent2")
        self.assertEqual(info["agent_id"], "id-1")
        self.assertEqual(info["tmux_pane"], "%2")

    @mock.patch("tmux_util.send_keys")
    def test_send_message_targets_agent_id(self, send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent(
                "agent1",
                {
                    "agent_id": "id-1",
                    "status": "working",
                    "waiting_approval": False,
                    "pending_notifications": [],
                    "tmux_pane": "%1",
                    "tmux_socket": "sock",
                },
            )
            self.assertTrue(
                rpc_handler.handle_send_message({"agent_id": "id-1", "message": "hello", "sender_name": "tester"})
            )
            info = state.get_agent("agent1")
            self.assertEqual(info.get("pending_notifications", []), [])
            send_keys.assert_called_once_with("%1", "New message in inbox from tester", "sock")
            with open(inbox_path, "r") as f:
                message = json.loads(f.readline())
            timestamp = datetime.datetime.fromisoformat(message["timestamp"])
            self.assertIsNotNone(timestamp.tzinfo)
            self.assertIsNotNone(timestamp.utcoffset())
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    def test_deliver_local_message_is_idempotent_for_message_id(self):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent(
                "agent1",
                {
                    "agent_id": "id-1",
                    "status": "working",
                    "waiting_approval": False,
                    "pending_notifications": [],
                    "tmux_pane": "%1",
                    "tmux_socket": "sock",
                },
            )
            msg = {"sender": "tester", "timestamp": rpc_handler._utc_now_isoformat(), "message": "hello", "read": False, "message_id": "m1"}
            rpc_handler.deliver_local_message("agent1", msg, "tester")
            rpc_handler.deliver_local_message("agent1", msg, "tester")
            with open(inbox_path, "r") as f:
                lines = [line for line in f if line.strip()]
            self.assertEqual(len(lines), 1)
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.send_keys")
    def test_deliver_local_message_publishes_event_for_communicator(self, _send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "sock",
                "status": "idle",
            })

            rpc_handler.deliver_local_message("receiver", {
                "sender": "sender-agent",
                "timestamp": "now",
                "message": "hello",
                "read": False,
                "message_id": "msg-1",
            })

            result = rpc_handler.handle_wait_events({"since": 0, "timeout": 0})
            self.assertEqual(len(result["events"]), 2)
            event = result["events"][0]
            self.assertEqual(event["type"], "message_delivered")
            self.assertEqual(event["target_agent_id"], "receiver-id")
            self.assertEqual(event["target_agent_name"], "receiver")
            self.assertEqual(event["sender"], "sender-agent")
            self.assertEqual(event["message_id"], "msg-1")
            self.assertEqual(result["events"][1]["type"], "message_notified")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.send_keys")
    def test_deliver_local_message_publishes_notified_event_when_idle(self, _send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "sock",
                "status": "idle",
            })

            rpc_handler.deliver_local_message("receiver", {
                "sender": "sender-agent",
                "timestamp": "now",
                "message": "hello",
                "read": False,
                "message_id": "msg-1",
            })

            result = rpc_handler.handle_wait_events({"since": 0, "timeout": 0})
            self.assertEqual([event["type"] for event in result["events"]], ["message_delivered", "message_notified"])
            self.assertEqual(result["events"][1]["message_id"], "msg-1")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("registry_client.publish_tracker_event")
    @mock.patch("tmux_util.send_keys")
    def test_deliver_local_message_relays_remote_delivered_and_notified(self, _send_keys, publish_tracker_event):
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "sock",
                "status": "idle",
            })

            rpc_handler.deliver_local_message("receiver", {
                "sender": "sender-agent (via host)",
                "timestamp": "now",
                "message": "hello",
                "read": False,
                "message_id": "msg-1",
                "sender_agent_id": "sender-id",
                "sender_tracker_id": "tracker-1",
            })

            publish_tracker_event.assert_any_call("tracker-1", "message_delivered", {
                "message_id": "msg-1",
                "sender_agent_id": "sender-id",
                "receiver_agent_id": "receiver-id",
                "receiver_agent_name": "receiver",
            })
            publish_tracker_event.assert_any_call("tracker-1", "message_notified", {
                "message_id": "msg-1",
                "sender_agent_id": "sender-id",
                "receiver_agent_id": "receiver-id",
                "receiver_agent_name": "receiver",
            })
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.focus_pane")
    @mock.patch("registry_client.publish_tracker_event")
    def test_remote_message_focus_enabled_uses_registered_socket(self, _publish_tracker_event, focus_pane):
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "/tmp/private.sock",
                "session": "sess",
                "status": "idle",
                "no_notify_with_send_keys": True,
            })
            with mock.patch.dict(os.environ, {"BROCCOLI_COMMS_FOCUS_REMOTE_MESSAGES": "1"}, clear=True):
                rpc_handler.deliver_local_message("receiver", {
                    "sender": "sender-agent (via host)",
                    "timestamp": "now",
                    "message": "hello",
                    "read": False,
                    "message_id": "focus-msg-1",
                    "sender_agent_id": "sender-id",
                    "sender_tracker_id": "tracker-1",
                })
            focus_pane.assert_called_once_with("%1", session="sess", socket_path="/tmp/private.sock")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.focus_pane")
    @mock.patch("registry_client.publish_tracker_event")
    def test_remote_message_focus_disabled_by_default(self, _publish_tracker_event, focus_pane):
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "/tmp/private.sock",
                "session": "sess",
                "status": "idle",
                "no_notify_with_send_keys": True,
            })
            with mock.patch.dict(os.environ, {}, clear=True):
                rpc_handler.deliver_local_message("receiver", {
                    "sender": "sender-agent (via host)",
                    "timestamp": "now",
                    "message": "hello",
                    "read": False,
                    "message_id": "focus-msg-disabled",
                    "sender_agent_id": "sender-id",
                    "sender_tracker_id": "tracker-1",
                })
            focus_pane.assert_not_called()
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.focus_pane", side_effect=RuntimeError("focus failed"))
    @mock.patch("registry_client.publish_tracker_event")
    def test_remote_message_focus_failure_does_not_fail_delivery(self, _publish_tracker_event, focus_pane):
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "/tmp/private.sock",
                "session": "sess",
                "status": "idle",
                "no_notify_with_send_keys": True,
            })
            with mock.patch.dict(os.environ, {"BROCCOLI_COMMS_FOCUS_REMOTE_MESSAGES": "true"}, clear=True):
                self.assertEqual(rpc_handler.deliver_local_message("receiver", {
                    "sender": "sender-agent (via host)",
                    "timestamp": "now",
                    "message": "hello",
                    "read": False,
                    "message_id": "focus-msg-fail",
                    "sender_agent_id": "sender-id",
                    "sender_tracker_id": "tracker-1",
                }), "receiver")
            focus_pane.assert_called_once_with("%1", session="sess", socket_path="/tmp/private.sock")
            with open(inbox_path, "r") as f:
                self.assertTrue(any(json.loads(line).get("message_id") == "focus-msg-fail" for line in f if line.strip()))
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.focus_pane")
    @mock.patch("registry_client.publish_tracker_event")
    def test_local_message_never_triggers_remote_focus(self, _publish_tracker_event, focus_pane):
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "/tmp/private.sock",
                "session": "sess",
                "status": "idle",
                "no_notify_with_send_keys": True,
            })
            with mock.patch.dict(os.environ, {"BROCCOLI_COMMS_FOCUS_REMOTE_MESSAGES": "1"}, clear=True):
                rpc_handler.deliver_local_message("receiver", {
                    "sender": "local-sender",
                    "timestamp": "now",
                    "message": "hello",
                    "read": False,
                    "message_id": "focus-local-msg",
                    "sender_agent_id": "sender-id",
                    "sender_tracker_id": registry_client.TRACKER_ID,
                })
            focus_pane.assert_not_called()
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    def test_wait_events_timeout_returns_empty_best_effort_response(self):
        result = rpc_handler.handle_wait_events({"since": 0, "timeout": 0})
        self.assertEqual(result["events"], [])
        self.assertEqual(result["last_seq"], 0)
        self.assertFalse(result["reset"])
        self.assertFalse(result["gap"])

    def test_wait_events_wakes_on_publish(self):
        result_box = {}
        waiter = threading.Thread(
            target=lambda: result_box.update(rpc_handler.handle_wait_events({"since": 0, "timeout": 2}))
        )
        waiter.start()
        time.sleep(0.05)
        state.publish_event("message_delivered", {"target_agent_id": "id-1"})
        waiter.join(timeout=1)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(result_box["events"][0]["target_agent_id"], "id-1")

    def test_wait_events_reports_seq_reset(self):
        result = rpc_handler.handle_wait_events({"since": 99, "timeout": 0})
        self.assertTrue(result["reset"])
        self.assertEqual(result["events"], [])
        state.publish_event("message_delivered", {"target_agent_id": "id-1"})
        result = rpc_handler.handle_wait_events({"since": 99, "timeout": 0})
        self.assertTrue(result["reset"])
        self.assertEqual(len(result["events"]), 1)

    def test_wait_events_reports_gap_when_events_truncated(self):
        old_max = state.MAX_EVENTS
        try:
            state.MAX_EVENTS = 2
            state.publish_event("message_delivered", {"target_agent_id": "id-1"})
            state.publish_event("message_delivered", {"target_agent_id": "id-2"})
            state.publish_event("message_delivered", {"target_agent_id": "id-3"})
            result = rpc_handler.handle_wait_events({"since": 0, "timeout": 0})
            self.assertTrue(result["gap"])
            self.assertEqual([event["target_agent_id"] for event in result["events"]], ["id-2", "id-3"])
        finally:
            state.MAX_EVENTS = old_max

    def test_wait_events_filters_and_rejects_invalid_params(self):
        state.publish_event("message_delivered", {"target_agent_id": "id-1", "target_agent_name": "one"})
        state.publish_event("message_delivered", {"target_agent_id": "id-2", "target_agent_name": "two"})
        result = rpc_handler.handle_wait_events({"since": 0, "timeout": 0, "target_agent_id": "id-2"})
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["target_agent_name"], "two")
        with self.assertRaises(ValueError):
            rpc_handler.handle_wait_events({"since": -1})
        with self.assertRaises(ValueError):
            rpc_handler.handle_wait_events({"timeout": "bad"})

    @mock.patch("tmux_util.send_keys")
    def test_no_notify_with_send_keys_suppresses_tmux_notification(self, send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent(
                "agent1",
                {
                    "agent_id": "id-1",
                    "status": "idle",
                    "waiting_approval": False,
                    "pending_notifications": [],
                    "tmux_pane": "%1",
                    "tmux_socket": "sock",
                    "no_notify_with_send_keys": True,
                },
            )

            self.assertTrue(
                rpc_handler.handle_send_message({"agent_id": "id-1", "message": "hello", "sender_name": "tester"})
            )

            send_keys.assert_not_called()
            self.assertEqual(state.get_agent("agent1").get("pending_notifications"), [])
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    def test_ensure_mailbox_creates_local_no_notify_identity(self):
        result = rpc_handler.handle_ensure_mailbox({"agent_name": "agent-communicator"})
        self.assertEqual(result["name"], "agent-communicator")
        info = state.get_agent("agent-communicator")
        self.assertEqual(info.get("agent_id"), result["agent_id"])
        self.assertTrue(info.get("is_mailbox"))
        self.assertTrue(info.get("no_notify_with_send_keys"))
        self.assertTrue(info.get("no_registry"))
        self.assertEqual(info.get("agent_type"), "agent-communicator-ui")
        self.assertIsNone(info.get("session"))
        self.assertIsNone(info.get("tmux_pane"))
        self.assertIsNone(info.get("tmux_socket"))
        self.assertIsNone(info.get("wrapper_pid"))
        self.assertIsNone(info.get("pid"))

    def test_ensure_mailbox_clears_existing_pane_metadata_and_blocks_direct_input(self):
        state.set_agent("agent-communicator", {
            "agent_id": "ui-id",
            "uuid": "ui-id",
            "session": "old-session",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "wrapper_pid": 123,
            "pid": 456,
        })
        rpc_handler.handle_ensure_mailbox({"agent_name": "agent-communicator"})
        info = state.get_agent("agent-communicator")
        self.assertIsNone(info.get("session"))
        self.assertIsNone(info.get("tmux_pane"))
        self.assertIsNone(info.get("tmux_socket"))
        self.assertIsNone(info.get("wrapper_pid"))
        self.assertIsNone(info.get("pid"))
        with self.assertRaisesRegex(RuntimeError, "UI/mailbox"):
            rpc_handler.handle_send_input({"agent_name": "agent-communicator", "input_type": "text", "text": "unsafe"})

    def test_ensure_mailbox_can_preserve_existing_pane_metadata(self):
        state.set_agent("agent-communicator", {
            "agent_id": "ui-id",
            "uuid": "ui-id",
            "session": "old-session",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "wrapper_pid": 123,
            "pid": 456,
            "no_registry": False,
        })
        rpc_handler.handle_ensure_mailbox({"agent_name": "agent-communicator", "preserve_pane": True})
        info = state.get_agent("agent-communicator")
        self.assertEqual(info.get("session"), "old-session")
        self.assertEqual(info.get("tmux_pane"), "%1")
        self.assertEqual(info.get("tmux_socket"), "sock")
        self.assertEqual(info.get("wrapper_pid"), 123)
        self.assertEqual(info.get("pid"), 456)
        self.assertTrue(info.get("no_registry"))
        self.assertTrue(info.get("is_mailbox"))
        with self.assertRaisesRegex(RuntimeError, "UI/mailbox"):
            rpc_handler.handle_send_input({"agent_name": "agent-communicator", "input_type": "keys", "keys": ["Enter"]})

    def test_ensure_mailbox_rejects_remote_names(self):
        with self.assertRaises(ValueError):
            rpc_handler.handle_ensure_mailbox({"agent_name": "host/agent-communicator"})
        with self.assertRaises(ValueError):
            rpc_handler.handle_ensure_mailbox({"agent_name": "registry:host/agent-communicator"})

    @mock.patch("state.publish_event")
    def test_get_inbox_publishes_message_read_event_once(self, publish_event):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            state.set_agent("agent1", {"agent_id": "id-1", "uuid": "id-1"})
            os.makedirs(state.INBOX_DIR, exist_ok=True)
            with open(inbox_path, "w") as f:
                f.write(json.dumps({"sender": "agent-communicator", "message": "hi", "read": False, "message_id": "m1"}) + "\n")

            result = rpc_handler.handle_get_inbox({"agent_name": "agent1"})
            self.assertEqual(result["mode"], "unread")
            publish_event.assert_called_once_with("message_read", {
                "target_agent_id": "id-1",
                "target_agent_name": "agent1",
                "sender": "agent-communicator",
                "message_id": "m1",
            })

            publish_event.reset_mock()
            rpc_handler.handle_get_inbox({"agent_name": "agent1"})
            publish_event.assert_not_called()
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("state.publish_event")
    def test_get_inbox_mark_read_false_does_not_mark_or_publish(self, publish_event):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            state.set_agent("agent1", {"agent_id": "id-1", "uuid": "id-1"})
            os.makedirs(state.INBOX_DIR, exist_ok=True)
            with open(inbox_path, "w") as f:
                f.write(json.dumps({"sender": "alpha", "sender_agent_id": "alpha-id", "message": "hi", "read": False, "message_id": "m1"}) + "\n")

            result = rpc_handler.handle_get_inbox({"agent_name": "agent1", "mark_read": False, "last_n": 100})
            self.assertEqual(result["mode"], "last_n")
            self.assertEqual(len(result["messages"]), 1)
            publish_event.assert_not_called()

            with open(inbox_path, "r") as f:
                stored = [json.loads(line) for line in f if line.strip()]
            self.assertFalse(stored[0]["read"])
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    def test_tracker_info_includes_health_snapshot(self):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle"})
        state.set_agent("agent2", {"agent_id": "id-2", "status": "offline"})
        with mock.patch.object(rpc_handler, "_read_registry_status", return_value={"connected": False, "registries": {"local": {"connected": False}}}), \
             mock.patch.object(registry_client, "fetch_trackers", return_value=(200, {"trackers": [{"tracker_id": registry_client.TRACKER_ID, "status": "active"}, {"tracker_id": "remote-1", "status": "active"}, {"tracker_id": "remote-2", "status": "gone"}]})):
            result = rpc_handler.handle_tracker_info({})
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["agent_count"], 2)
        self.assertEqual(result["online_agent_count"], 1)
        self.assertFalse(result["registry_connected"])
        self.assertEqual(result["registries"][0]["name"], "local")
        self.assertEqual(result["remote_tracker_count"], 2)
        self.assertEqual(result["online_remote_tracker_count"], 1)

    def test_get_unread_counts_counts_stable_sender_keys_without_marking_read(self):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            state.set_agent("agent1", {"agent_id": "id-1", "uuid": "id-1"})
            os.makedirs(state.INBOX_DIR, exist_ok=True)
            with open(inbox_path, "w") as f:
                f.write(json.dumps({"sender": "alpha", "sender_agent_id": "alpha-id", "sender_tracker_id": registry_client.TRACKER_ID, "message": "a", "read": False, "message_id": "m1"}) + "\n")
                f.write(json.dumps({"sender": "remote-alpha", "sender_agent_id": "alpha-id", "sender_tracker_id": "remote-tracker", "message": "b", "read": False, "message_id": "m2"}) + "\n")
                f.write(json.dumps({"sender": "legacy", "message": "c", "read": False, "message_id": "m3"}) + "\n")
                f.write(json.dumps({"sender": "alpha", "sender_agent_id": "alpha-id", "message": "read", "read": True, "message_id": "m4"}) + "\n")

            result = rpc_handler.handle_get_unread_counts({"agent_name": "agent1"})
            self.assertEqual(result["total"], 3)
            self.assertEqual(result["counts"]["local:alpha-id"], 1)
            self.assertEqual(result["counts"]["remote:remote-tracker:alpha-id"], 1)
            self.assertEqual(result["counts"]["sender:legacy"], 1)

            with open(inbox_path, "r") as f:
                stored = [json.loads(line) for line in f if line.strip()]
            self.assertFalse(stored[0]["read"])
            self.assertFalse(stored[1]["read"])
            self.assertFalse(stored[2]["read"])
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("state.publish_event")
    def test_get_inbox_sender_filter_marks_only_matching_messages(self, publish_event):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            state.set_agent("agent1", {"agent_id": "id-1", "uuid": "id-1"})
            os.makedirs(state.INBOX_DIR, exist_ok=True)
            with open(inbox_path, "w") as f:
                f.write(json.dumps({"sender": "alpha", "sender_agent_id": "alpha-id", "sender_tracker_id": registry_client.TRACKER_ID, "message": "a", "read": False, "message_id": "m1"}) + "\n")
                f.write(json.dumps({"sender": "alpha", "sender_agent_id": "alpha-id", "sender_tracker_id": "remote-tracker", "message": "remote", "read": False, "message_id": "m2"}) + "\n")
                f.write(json.dumps({"sender": "alpha", "sender_agent_id": "alpha-id", "message": "legacy local", "read": False, "message_id": "m3"}) + "\n")
                f.write(json.dumps({"sender": "beta", "sender_agent_id": "beta-id", "message": "b", "read": False, "message_id": "m4"}) + "\n")

            result = rpc_handler.handle_get_inbox({"agent_name": "agent1", "sender_agent_id": "alpha-id", "sender_tracker_id": registry_client.TRACKER_ID})
            self.assertEqual([m["message_id"] for m in result["messages"]], ["m1", "m3"])

            with open(inbox_path, "r") as f:
                stored = [json.loads(line) for line in f if line.strip()]
            self.assertTrue(stored[0]["read"])
            self.assertFalse(stored[1]["read"])
            self.assertTrue(stored[2]["read"])
            self.assertFalse(stored[3]["read"])
            self.assertEqual(publish_event.call_count, 2)
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("registry_client.push_agent_update")
    def test_update_agent_publishes_status_changed_event(self, push_update):
        state.set_agent("agent1", {"agent_id": "id-1", "uuid": "id-1", "status": "idle", "agent_type": "pi", "agent_cmd": "pi"})
        self.assertTrue(rpc_handler.handle_update_agent({"agent_name": "agent1", "status": "running"}))
        push_update.assert_called_once_with("id-1", "running")
        event = state.events[-1]
        self.assertEqual(event["type"], "agent_status_changed")
        self.assertEqual(event["target_agent_id"], "id-1")
        self.assertEqual(event["old_status"], "idle")
        self.assertEqual(event["status"], "running")

    def test_heartbeat_publishes_status_changed_event(self):
        state.set_agent("agent1", {"agent_id": "id-1", "uuid": "id-1", "status": "idle", "agent_type": "pi", "agent_cmd": "pi"})
        self.assertTrue(rpc_handler.handle_heartbeat({"agent_name": "agent1", "status": "running"}))
        event = state.events[-1]
        self.assertEqual(event["type"], "agent_status_changed")
        self.assertEqual(event["target_agent_id"], "id-1")
        self.assertEqual(event["old_status"], "idle")
        self.assertEqual(event["status"], "running")

    @mock.patch("tmux_util.send_keys")
    def test_send_message_notifies_recovered_unknown_agent(self, send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent(
                "agent1",
                {
                    "agent_id": "id-1",
                    "status": "unknown",
                    "waiting_approval": False,
                    "pending_notifications": [],
                    "tmux_pane": "%1",
                    "tmux_socket": "sock",
                },
            )

            self.assertTrue(
                rpc_handler.handle_send_message({"agent_id": "id-1", "message": "hello", "sender_name": "tester"})
            )

            info = state.get_agent("agent1")
            self.assertEqual(info["pending_notifications"], [])
            send_keys.assert_called_once_with("%1", "New message in inbox from tester", "sock")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.set_agent_uuid")
    @mock.patch("tmux_util.set_agent_id")
    def test_simultaneous_wrapper_reconnect_race(self, _set_agent_id, _set_agent_uuid):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "unknown",
                "waiting_approval": False,
                "pending_notifications": [],
                "tmux_pane": "%1",
                "tmux_socket": "sock",
            },
        )

        name1 = rpc_handler.handle_register(
            {
                "session": "sess",
                "tmux_pane": "%1",
                "wrapper_pid": 111,
                "tmux_socket": "sock",
                "name": "agent1",
                "agent_id": "id-1",
            }
        )
        name2 = rpc_handler.handle_register(
            {
                "session": "sess",
                "tmux_pane": "%1",
                "wrapper_pid": 222,
                "tmux_socket": "sock",
                "name": "agent1",
                "agent_id": "id-1",
            }
        )

        self.assertEqual(name1, "agent1")
        self.assertEqual(name2, "agent1")
        self.assertEqual(len(state.state), 1)
        info = state.get_agent("agent1")
        self.assertEqual(info["wrapper_pid"], 222)
        self.assertEqual(info["status"], "unknown")

    @mock.patch("tmux_util.spin_agent")
    @mock.patch("tmux_util.set_agent_uuid")
    @mock.patch("tmux_util.set_agent_id")
    def test_placeholder_spawning_replaced_by_real_register(self, _set_agent_id, _set_agent_uuid, _spin):
        _spin.return_value = "%42"
        assigned_name = rpc_handler.handle_spin_agent(
            {"session": "sess", "command": "jetski", "name": "agent1"}
        )
        self.assertEqual(assigned_name, "agent1")
        spawning_info = state.get_agent("agent1")
        self.assertEqual(spawning_info["status"], "spawning")
        self.assertEqual(spawning_info["session"], "sess")
        self.assertEqual(spawning_info["tmux_pane"], "%42")

        real_name = rpc_handler.handle_register(
            {
                "session": "sess",
                "tmux_pane": "%2",
                "wrapper_pid": 333,
                "tmux_socket": "sock",
                "name": "agent1",
                "agent_id": "real-uuid-123",
            }
        )
        self.assertEqual(real_name, "agent1")
        self.assertEqual(len(state.state), 1)
        info = state.get_agent("agent1")
        self.assertEqual(info["agent_id"], "real-uuid-123")
        self.assertEqual(info["status"], "idle")

    @mock.patch("tmux_util.spin_agent")
    @mock.patch("rpc_handler._identify_agent", return_value="parent-agent")
    def test_handle_spin_agent_strips_inherited_identity(self, mock_identify, mock_spin):
        mock_spin.return_value = "%42"
        state.set_agent("parent-agent", {"agent_id": "parent-id", "session": "sess", "tmux_pane": "%1", "tmux_socket": "sock"})

        env = {"PATH": "/bin", "AGENT_ID": "parent-id", "AGENT_NAME": "parent-agent", "AGENT_UUID": "parent-id"}
        rpc_handler.handle_spin_agent(
            {"session": "sess", "command": "jetski", "name": "agent1", "env": env},
            caller_pid=999
        )

        mock_identify.assert_called_once_with({}, 999)
        mock_spin.assert_called_once_with("agent1", "jetski", "%1", session="sess", directory=None, env=env, tmux_socket="sock")
        self.assertNotIn("AGENT_ID", env)
        self.assertNotIn("AGENT_NAME", env)
        self.assertNotIn("AGENT_UUID", env)
        self.assertEqual(env["SUGGESTED_AGENT_NAME"], "agent1")
        self.assertEqual(env["PATH"], "/bin")

    @mock.patch("tmux_util.spin_agent")
    @mock.patch("rpc_handler._identify_agent", return_value="parent-agent")
    def test_handle_spin_agent_preserves_explicit_identity_override(self, mock_identify, mock_spin):
        mock_spin.return_value = "%42"
        state.set_agent("parent-agent", {"agent_id": "parent-id", "session": "sess", "tmux_pane": "%1", "tmux_socket": "sock"})

        env = {"PATH": "/bin", "AGENT_ID": "custom-subagent-id", "AGENT_NAME": "custom-subagent-name", "AGENT_UUID": "custom-subagent-id"}
        rpc_handler.handle_spin_agent(
            {"session": "sess", "command": "jetski", "name": "agent1", "env": env},
            caller_pid=999
        )

        mock_identify.assert_called_once_with({}, 999)
        mock_spin.assert_called_once_with("agent1", "jetski", "%1", session="sess", directory=None, env=env, tmux_socket="sock")
        self.assertEqual(env["AGENT_ID"], "custom-subagent-id")
        self.assertEqual(env["AGENT_NAME"], "custom-subagent-name")
        self.assertEqual(env["AGENT_UUID"], "custom-subagent-id")
        self.assertEqual(env["SUGGESTED_AGENT_NAME"], "agent1")
        self.assertEqual(env["PATH"], "/bin")

    @mock.patch("tmux_util.spin_agent")
    @mock.patch("rpc_handler._identify_agent", return_value="caller")
    def test_spin_uses_caller_tmux_context_and_placeholder_name(self, mock_identify, mock_spin):
        mock_spin.return_value = "%42"
        state.set_agent("caller", {"agent_id": "caller-id", "session": "sess", "tmux_pane": "%5", "tmux_socket": "sock"})

        assigned_name = rpc_handler.handle_spin_agent({"command": "pi", "name": "child", "env": {}}, caller_pid=222)

        self.assertEqual(assigned_name, "child")
        mock_identify.assert_called_once_with({}, 222)
        mock_spin.assert_called_once_with("child", "pi", "%5", session="sess", directory=None, env={"SUGGESTED_AGENT_NAME": "child"}, tmux_socket="sock")
        self.assertEqual(state.get_agent("child")["status"], "spawning")

    @mock.patch("registry_client.send_remote_message", return_value=(202, {"ok": True}))
    def test_send_message_routes_remote_target_address_via_registry(self, send_remote):
        state.set_agent("sender", {"agent_id": "id-s", "status": "idle"})
        self.assertTrue(rpc_handler.handle_send_message({"agent_name": "sender", "target_address": "remote-host/agent2", "message": "hello"}))
        send_remote.assert_called_once_with("sender", "id-s", mock.ANY, "remote-host", "agent2", "hello", None, None, mock.ANY)
        self.assertEqual(send_remote.call_args.args[8]["sender_model_type"], "unknown")

    @mock.patch("registry_client.send_remote_message", return_value=(202, {"ok": True}))
    def test_send_message_routes_remote_uuid_target_address_via_registry(self, send_remote):
        state.set_agent("sender", {"agent_id": "id-s", "status": "idle"})
        target_id = "961477f2-6523-4dae-87ea-bc6223fa04df"
        self.assertTrue(rpc_handler.handle_send_message({"agent_name": "sender", "target_address": f"remote-host/{target_id}", "message": "hello"}))
        send_remote.assert_called_once_with("sender", "id-s", mock.ANY, "remote-host", target_id, "hello", None, None, mock.ANY)

    @mock.patch("registry_client.send_remote_message_to_registry", return_value=(202, {"ok": True}))
    def test_send_message_routes_explicit_registry_target_address(self, send_remote):
        state.set_agent("sender", {"agent_id": "id-s", "status": "idle"})
        self.assertTrue(rpc_handler.handle_send_message({"agent_name": "sender", "target_address": "corp:remote-host/agent2", "message": "hello"}))
        send_remote.assert_called_once_with("corp", "sender", "id-s", mock.ANY, "remote-host", "agent2", "hello", None, None, mock.ANY)

    @mock.patch("tmux_util.send_keys")
    def test_local_send_preserves_message_id_and_sender_metadata(self, send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
            state.set_agent("agent-communicator", {"agent_id": "sender-id", "status": "idle", "agent_type": "pi", "agent_cmd": "pi"})

            self.assertTrue(rpc_handler.handle_send_message({"agent_name": "agent1", "message": "hello", "sender_name": "agent-communicator", "message_id": "m1"}))

            with open(inbox_path) as f:
                msg = json.loads(f.readline())
            self.assertEqual(msg["message_id"], "m1")
            self.assertEqual(msg["sender_agent_id"], "sender-id")
            self.assertEqual(msg["sender_tracker_id"], registry_client.TRACKER_ID)
            self.assertEqual(msg["sender_hostname"], registry_client.HOSTNAME)
            self.assertEqual(msg["sender_model_type"], "pi")
            self.assertEqual(msg["sender_agent_type"], "pi")
            self.assertEqual(msg["sender_agent_cmd"], "pi")
            self.assertEqual(msg["kind"], "text")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("registry_client.send_remote_message")
    @mock.patch("tmux_util.send_keys")
    def test_send_message_treats_local_target_address_as_local_only(self, send_keys, send_remote):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
            self.assertTrue(rpc_handler.handle_send_message({"target_address": "local/agent1", "message": "hello", "sender_name": "tester"}))
            send_remote.assert_not_called()
            send_keys.assert_called_once()
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.send_keys")
    def test_busy_agent_notifies_immediately(self, send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent(
                "agent1",
                {
                    "agent_id": "id-1",
                    "status": "working",
                    "waiting_approval": False,
                    "pending_notifications": [],
                    "tmux_pane": "%1",
                    "tmux_socket": "sock",
                },
            )

            self.assertTrue(
                rpc_handler.handle_send_message({"agent_id": "id-1", "message": "msg1", "sender_name": "alice"})
            )
            self.assertTrue(
                rpc_handler.handle_send_message({"agent_id": "id-1", "message": "msg2", "sender_name": "bob"})
            )

            info = state.get_agent("agent1")
            self.assertEqual(info.get("pending_notifications", []), [])
            self.assertEqual(send_keys.call_count, 2)
            send_keys.assert_any_call("%1", "New message in inbox from alice", "sock")
            send_keys.assert_any_call("%1", "New message in inbox from bob", "sock")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    def test_get_inbox_clear_keeps_last_25_messages(self):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            state.set_agent("agent1", {"agent_id": "id-1", "uuid": "id-1"})
            os.makedirs(state.INBOX_DIR, exist_ok=True)
            
            with open(inbox_path, "w") as f:
                for i in range(1, 31):
                    msg = {"sender": f"agent-{i}", "message": f"msg-{i}", "read": False, "message_id": f"m{i}"}
                    f.write(json.dumps(msg) + "\n")

            result = rpc_handler.handle_get_inbox({"agent_name": "agent1", "clear": True})
            
            self.assertEqual(result["mode"], "unread")
            self.assertEqual(len(result["messages"]), 30)

            self.assertTrue(os.path.exists(inbox_path))
            remaining_messages = []
            with open(inbox_path, "r") as f:
                for line in f:
                    if line.strip():
                        remaining_messages.append(json.loads(line))

            self.assertEqual(len(remaining_messages), 25)
            self.assertEqual(remaining_messages[0]["sender"], "agent-6")
            self.assertEqual(remaining_messages[-1]["sender"], "agent-30")
            self.assertTrue(all(msg["read"] for msg in remaining_messages))
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.send_keys")
    @mock.patch("tmux_util.send_keys_reliable")
    def test_deliver_local_message_reliable_success(self, mock_send_keys_reliable, mock_send_keys):
        mock_send_keys_reliable.return_value = True
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "sock",
                "status": "idle",
            })

            rpc_handler.deliver_local_message("receiver", {
                "sender": "sender-agent",
                "message": "hello",
                "message_id": "msg-1",
            })

            mock_send_keys_reliable.assert_called_once_with("%1", "New message in inbox from sender-agent", "sock", timeout=5)
            mock_send_keys.assert_not_called()
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.send_keys")
    @mock.patch("tmux_util.send_keys_reliable")
    def test_deliver_local_message_reliable_failure_fallback(self, mock_send_keys_reliable, mock_send_keys):
        mock_send_keys_reliable.return_value = False
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "sock",
                "status": "idle",
            })

            rpc_handler.deliver_local_message("receiver", {
                "sender": "sender-agent",
                "message": "hello",
                "message_id": "msg-1",
            })

            mock_send_keys_reliable.assert_called_once_with("%1", "New message in inbox from sender-agent", "sock", timeout=5)
            mock_send_keys.assert_called_once_with("%1", "New message in inbox from sender-agent", "sock")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.send_keys")
    @mock.patch("tmux_util.send_keys_reliable")
    def test_deliver_local_message_reliable_exception_fallback(self, mock_send_keys_reliable, mock_send_keys):
        mock_send_keys_reliable.side_effect = Exception("tmux error")
        inbox_path = os.path.join(state.INBOX_DIR, "receiver-id.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("receiver", {
                "agent_id": "receiver-id",
                "uuid": "receiver-id",
                "tmux_pane": "%1",
                "tmux_socket": "sock",
                "status": "idle",
            })

            rpc_handler.deliver_local_message("receiver", {
                "sender": "sender-agent",
                "message": "hello",
                "message_id": "msg-1",
            })

            mock_send_keys_reliable.assert_called_once_with("%1", "New message in inbox from sender-agent", "sock", timeout=5)
            mock_send_keys.assert_called_once_with("%1", "New message in inbox from sender-agent", "sock")
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    @mock.patch("tmux_util.capture_pane_visible_text")
    @mock.patch("tmux_util.is_pane_in_copy_mode")
    def test_handle_capture_pane_by_agent_name(self, mock_copy_mode, mock_capture):
        state.set_agent("agent1", {
            "agent_id": "id-1",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "session": "sess-1",
            "status": "idle"
        })
        mock_copy_mode.return_value = False
        mock_capture.return_value = "Screen Text"

        res = rpc_handler.handle_capture_pane({
            "agent_name": "agent1",
            "last_lines": 100,
            "include_ansi": True
        })

        self.assertEqual(res["agent_name"], "agent1")
        self.assertEqual(res["agent_id"], "id-1")
        self.assertEqual(res["tmux_pane"], "%1")
        self.assertEqual(res["session"], "sess-1")
        self.assertFalse(res["copy_mode"])
        self.assertEqual(res["content"], "Screen Text")
        self.assertEqual(res["lines_requested"], 100)
        mock_copy_mode.assert_called_once_with("%1", "sock")
        mock_capture.assert_called_once_with("%1", last_lines=100, socket_path="sock", include_ansi=True)

    @mock.patch("tmux_util.capture_pane_visible_text")
    @mock.patch("tmux_util.is_pane_in_copy_mode")
    def test_handle_capture_pane_by_agent_id(self, mock_copy_mode, mock_capture):
        state.set_agent("agent1", {
            "agent_id": "id-1",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "session": "sess-1"
        })
        mock_copy_mode.return_value = True
        mock_capture.return_value = "Screen Text Copy"

        res = rpc_handler.handle_capture_pane({
            "agent_id": "id-1",
            "last_lines": 200
        })

        self.assertEqual(res["agent_name"], "agent1")
        self.assertEqual(res["agent_id"], "id-1")
        self.assertTrue(res["copy_mode"])
        self.assertEqual(res["content"], "Screen Text Copy")
        mock_capture.assert_called_once_with("%1", last_lines=200, socket_path="sock", include_ansi=False)

    @mock.patch("tmux_util.capture_pane_visible_text")
    @mock.patch("tmux_util.is_pane_in_copy_mode")
    @mock.patch("tmux_util.get_pane_info")
    def test_handle_capture_pane_by_pane_directly(self, mock_pane_info, mock_copy_mode, mock_capture):
        mock_copy_mode.return_value = False
        mock_capture.return_value = "Direct Pane Text"
        mock_pane_info.return_value = {"tty": "/dev/pts/1", "session": "sess-direct", "pid": 123}

        res = rpc_handler.handle_capture_pane({
            "pane": "%5",
            "last_lines": 50
        })

        self.assertIsNone(res["agent_name"])
        self.assertIsNone(res["agent_id"])
        self.assertEqual(res["tmux_pane"], "%5")
        self.assertEqual(res["session"], "sess-direct")
        self.assertEqual(res["content"], "Direct Pane Text")
        mock_capture.assert_called_once_with("%5", last_lines=50, socket_path=None, include_ansi=False)

    @mock.patch("tmux_util.capture_pane_visible_text")
    @mock.patch("tmux_util.is_pane_in_copy_mode")
    def test_handle_capture_pane_default_lines_from_env(self, mock_copy_mode, mock_capture):
        state.set_agent("agent1", {
            "agent_id": "id-1",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "session": "sess-1"
        })
        mock_copy_mode.return_value = False
        mock_capture.return_value = "Default lines text"

        with mock.patch.dict(os.environ, {"AGENT_TRACKER_CAPTURE_PANE_DEFAULT_LINES": "42"}, clear=False):
            res = rpc_handler.handle_capture_pane({"agent_id": "id-1"})

        self.assertEqual(res["lines_requested"], 42)
        mock_capture.assert_called_once_with("%1", last_lines=42, socket_path="sock", include_ansi=False)

    def test_handle_capture_pane_invalid_target_raises(self):
        with self.assertRaises(ValueError):
            rpc_handler.handle_capture_pane({
                "agent_name": "non-existent"
            })

    @mock.patch("tmux_util.capture_pane_visible_text")
    @mock.patch("tmux_util.is_pane_in_copy_mode")
    def test_handle_capture_pane_safety_bounds_cap(self, mock_copy_mode, mock_capture):
        state.set_agent("agent1", {
            "agent_id": "id-1",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "session": "sess-1"
        })
        mock_copy_mode.return_value = False
        mock_capture.return_value = "Screen Text capped"

        res = rpc_handler.handle_capture_pane({
            "agent_id": "id-1",
            "last_lines": 5000
        })

        self.assertEqual(res["lines_requested"], 1000) # capped!
        mock_capture.assert_called_once_with("%1", last_lines=1000, socket_path="sock", include_ansi=False)

    @mock.patch("tmux_util.capture_pane_visible_text")
    @mock.patch("tmux_util.is_pane_in_copy_mode")
    def test_handle_capture_pane_graceful_exception(self, mock_copy_mode, mock_capture):
        state.set_agent("agent1", {
            "agent_id": "id-1",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "session": "sess-1"
        })
        mock_copy_mode.return_value = False
        mock_capture.side_effect = RuntimeError("tmux command failed or zero-column")

        with self.assertRaises(RuntimeError) as ctx:
            rpc_handler.handle_capture_pane({
                "agent_id": "id-1",
                "last_lines": 100
            })
        self.assertIn("Failed to capture pane visible text buffer", str(ctx.exception))


    @mock.patch("tmux_util.send_literal_text")
    def test_send_input_text_by_local_name_uses_registered_socket(self, send_literal):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
        result = rpc_handler.handle_send_input({"agent_name": "agent1", "input_type": "text", "text": "hello"})
        self.assertEqual(result, {"success": True, "target": "agent1", "mode": "text", "submitted": True})
        send_literal.assert_called_once_with("%1", "hello", submit=True, socket_path="sock")

    @mock.patch("tmux_util.send_symbolic_keys")
    def test_send_input_keys_by_id_uses_registered_socket(self, send_keys):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
        result = rpc_handler.handle_send_input({"agent_id": "id-1", "mode": "keys", "key": "C-c"})
        self.assertEqual(result, {"success": True, "target": "agent1", "mode": "keys", "keys": ["C-c"]})
        send_keys.assert_called_once_with("%1", ["C-c"], socket_path="sock")

    @mock.patch("tmux_util.send_literal_text")
    def test_send_input_local_target_address_resolves_locally(self, send_literal):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
        result = rpc_handler.handle_send_input({"target_address": "local/agent1", "input_type": "text", "text": "draft", "submit": False})
        self.assertFalse(result["submitted"])
        send_literal.assert_called_once_with("%1", "draft", submit=False, socket_path="sock")

    @mock.patch("tmux_util.send_literal_text")
    def test_send_input_hostname_local_target_address_resolves_locally(self, send_literal):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
        result = rpc_handler.handle_send_input({"target_address": f"{rpc_handler.LOCAL_HOSTNAME}/id-1", "input_type": "text", "text": "hello"})
        self.assertTrue(result["success"])
        send_literal.assert_called_once_with("%1", "hello", submit=True, socket_path="sock")

    @mock.patch("tmux_util.send_literal_text")
    def test_send_input_missing_tmux_socket_fails_without_default_fallback(self, send_literal):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1"})
        with self.assertRaises(RuntimeError) as ctx:
            rpc_handler.handle_send_input({"agent_name": "agent1", "input_type": "text", "text": "hello"})
        self.assertIn("no registered tmux socket", str(ctx.exception))
        send_literal.assert_not_called()

    def test_send_input_missing_pane_fails(self):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_socket": "sock"})
        with self.assertRaises(RuntimeError) as ctx:
            rpc_handler.handle_send_input({"agent_name": "agent1", "input_type": "text", "text": "hello"})
        self.assertIn("no registered tmux pane", str(ctx.exception))

    @mock.patch("tmux_util.send_literal_text", side_effect=RuntimeError("tmux socket unreachable"))
    def test_send_input_unreachable_registered_socket_fails_clearly(self, send_literal):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
        with self.assertRaises(RuntimeError) as ctx:
            rpc_handler.handle_send_input({"agent_name": "agent1", "input_type": "text", "text": "hello"})
        self.assertIn("Failed to send direct pane input", str(ctx.exception))
        send_literal.assert_called_once_with("%1", "hello", submit=True, socket_path="sock")

    def test_send_input_remote_target_address_disabled(self):
        with self.assertRaises(RuntimeError) as ctx:
            rpc_handler.handle_send_input({"target_address": "remote-host/agent1", "input_type": "text", "text": "hello"})
        self.assertIn("remote direct pane input is disabled", str(ctx.exception))

    @mock.patch.object(registry_client, "send_remote_pane_input", return_value=(202, {"pane_input_id": "pi-1", "request_id": "req-1"}))
    def test_send_input_remote_target_address_routes_when_enabled(self, send_remote):
        state.set_agent("sender", {"agent_id": "sender-id", "status": "idle"})
        with mock.patch.dict(os.environ, {"AGENT_TRACKER_REMOTE_PANE_INPUT_SEND_ENABLED": "1"}, clear=True):
            result = rpc_handler.handle_send_input({
                "sender_name": "sender",
                "target_address": "remote-host/agent1",
                "input_type": "text",
                "text": "hello",
                "pane_input_id": "pi-1",
                "request_id": "req-1",
            })
        self.assertEqual(result, {"success": True, "queued": True, "mode": "text", "pane_input_id": "pi-1", "request_id": "req-1"})
        send_remote.assert_called_once_with(
            "sender", "sender-id", registry_client.TRACKER_ID, "remote-host", "agent1", "text",
            text="hello", keys=None, submit=True, pane_input_id="pi-1", request_id="req-1"
        )

    @mock.patch.object(registry_client, "send_remote_pane_input_to_registry", return_value=(202, {"pane_input_id": "pi-2", "request_id": "req-2"}))
    def test_send_input_remote_registry_qualified_routes_keys(self, send_remote):
        with mock.patch.dict(os.environ, {"AGENT_TRACKER_REMOTE_PANE_INPUT_SEND_ENABLED": "1"}, clear=True):
            result = rpc_handler.handle_send_input({
                "target_address": "work:remote-host/agent1",
                "input_type": "keys",
                "keys": ["ctrl-c", "enter"],
                "pane_input_id": "pi-2",
                "request_id": "req-2",
            })
        self.assertTrue(result["success"])
        send_remote.assert_called_once_with(
            "work", "cli-user", None, registry_client.TRACKER_ID, "remote-host", "agent1", "keys",
            text=None, keys=["C-c", "Enter"], submit=True, pane_input_id="pi-2", request_id="req-2"
        )

    def test_send_input_invalid_params(self):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
        invalid_params = [
            {"agent_name": "agent1", "input_type": "bogus", "text": "hello"},
            {"agent_name": "agent1", "input_type": "text", "text": "hello", "submit": "yes"},
            {"agent_name": "agent1", "input_type": "keys"},
            {"input_type": "text", "text": "hello"},
        ]
        for params in invalid_params:
            with self.subTest(params=params):
                with self.assertRaises(ValueError):
                    rpc_handler.handle_send_input(params)

    @mock.patch("tmux_util.send_keys")
    @mock.patch("tmux_util.send_literal_text")
    def test_send_input_bypasses_inbox_and_notifications(self, send_literal, notify_send_keys):
        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        try:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)
            state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "tmux_socket": "sock"})
            result = rpc_handler.handle_send_input({"agent_name": "agent1", "input_type": "text", "text": "hello"})
            self.assertTrue(result["success"])
            self.assertFalse(os.path.exists(inbox_path))
            notify_send_keys.assert_not_called()
        finally:
            if os.path.exists(inbox_path):
                os.remove(inbox_path)

    def test_wait_events_with_custom_watchlist_and_lease(self):
        state.events = []
        state.event_sequence_id = 0
        state.active_watchlists = {}
        
        # Call wait_events with custom watchlist and client_id
        params = {
            "client_id": "client1",
            "cursor": 0,
            "watch_list": ["target-agent"],
            "lease_seconds": 5.0,
            "timeout": 0
        }
        result = rpc_handler.handle_wait_events(params)
        
        self.assertEqual(result["events"], [])
        self.assertIn("client1", state.active_watchlists)
        self.assertEqual(state.active_watchlists["client1"]["watch_list"], {"target-agent"})
        
        # Publish an event that doesn't match target-agent
        state.publish_event("dummy", {"target_agent_id": "other-agent"})
        result = rpc_handler.handle_wait_events(params)
        self.assertEqual(result["events"], [])
        
        # Publish an event matching target-agent
        state.publish_event("dummy", {"target_agent_id": "target-agent"})
        # Re-request wait_events
        result = rpc_handler.handle_wait_events(params)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["target_agent_id"], "target-agent")

    def test_wait_events_cursor_expired_error(self):
        state.events = []
        state.event_sequence_id = 0
        
        # Temporarily cap MAX_EVENTS to 3 to trigger eviction quickly
        old_max = state.MAX_EVENTS
        try:
            state.MAX_EVENTS = 3
            state.publish_event("dummy", {"data": 1})
            state.publish_event("dummy", {"data": 2})
            state.publish_event("dummy", {"data": 3})
            state.publish_event("dummy", {"data": 4})
            state.publish_event("dummy", {"data": 5})
            
            # Oldest event is now seq 3. Cursor 1 is evicted!
            params = {
                "client_id": "client1",
                "cursor": 1,
                "watch_list": ["target-agent"],
                "lease_seconds": 5.0,
                "timeout": 0
            }
            # Calling this should raise CursorExpiredError
            with self.assertRaises(rpc_handler.CursorExpiredError):
                rpc_handler.handle_wait_events(params)
        finally:
            state.MAX_EVENTS = old_max

    def test_wait_events_broad_watch_local_rejection(self):
        old_broad = rpc_handler.REMOTE_BROAD_WATCH_ENABLED
        try:
            # Enforce broad watch is disabled
            rpc_handler.REMOTE_BROAD_WATCH_ENABLED = False
            
            params = {
                "client_id": "client_win_1",
                "cursor": 0,
                "watch_list": ["host2/agent2"],
                "scope": "broad",
                "lease_seconds": 10.0,
                "timeout": 0
            }
            # Should raise ValueError due to local config gate rejection
            with self.assertRaises(ValueError) as ctx:
                rpc_handler.handle_wait_events(params)
            self.assertIn("Broad passive remote observation is disabled", str(ctx.exception))
        finally:
            rpc_handler.REMOTE_BROAD_WATCH_ENABLED = old_broad


    def test_handle_get_group_timeline(self):
        import tempfile, shutil
        temp_cache = tempfile.mkdtemp()
        orig_dir = state.GROUP_TIMELINE_DIR
        state.GROUP_TIMELINE_DIR = temp_cache
        try:
            group_id = "host:local:test-rpc-machine"
            payload = {
                "message_id": "msg-100",
                "sender": "sender-1",
                "recipient": "recipient-1",
                "timestamp": "2026-05-26T23:48:00Z",
                "message": "hello rpc dispatch"
            }
            state.append_to_group_timeline(group_id, payload)
            
            res = rpc_handler.handle_get_group_timeline({
                "group_id": group_id,
                "last_n": 10
            })
            
            self.assertIn("messages", res)
            self.assertEqual(len(res["messages"]), 1)
            self.assertEqual(res["messages"][0]["message_id"], "msg-100")
            
            with self.assertRaises(ValueError) as ctx:
                rpc_handler.handle_get_group_timeline({})
            self.assertIn("group_id is required", str(ctx.exception))
            
            with self.assertRaises(ValueError) as ctx:
                rpc_handler.handle_get_group_timeline({
                    "group_id": 123
                })
            self.assertIn("group_id must be a string", str(ctx.exception))
            
        finally:
            state.GROUP_TIMELINE_DIR = orig_dir
            shutil.rmtree(temp_cache)


    def test_handle_update_watchlist_group_mode(self):
        state.active_group_watches = {}
        params = {
            "watch_id": "my-client-group-watch",
            "mode": "group",
            "group_id": "host:local:test-group-channel",
            "members": ["local-host/agent-1", "local-host/agent-2"],
            "lease_seconds": 60
        }
        res = rpc_handler.handle_update_watchlist(params)
        self.assertTrue(res)
        
        self.assertIn("my-client-group-watch", state.active_group_watches)
        watch = state.active_group_watches["my-client-group-watch"]
        self.assertEqual(watch["group_id"], "host:local:test-group-channel")
        self.assertEqual(watch["members"], {"local-host/agent-1", "local-host/agent-2"})
        
        with self.assertRaises(ValueError) as ctx:
            rpc_handler.handle_update_watchlist({})
        self.assertIn("watch_id is required", str(ctx.exception))
        
        with self.assertRaises(ValueError) as ctx:
            rpc_handler.handle_update_watchlist({
                "watch_id": "my-id",
                "mode": "group"
            })
        self.assertIn("group_id is required for group watch mode", str(ctx.exception))


    @mock.patch("registry_client.fetch_trackers")
    @mock.patch("registry_client.publish_tracker_event")
    def test_remote_delegated_group_watch_roundtrip(self, publish_event, fetch_trackers):
        state.active_group_watches = {}
        
        fetch_trackers.return_value = (200, {
            "trackers": [
                {"hostname": "host2", "tracker_id": "remote-tracker-id-123"}
            ]
        })
        
        params = {
            "watch_id": "mac-electron-active-group",
            "mode": "group",
            "group_id": "host:local:tanmayvijay.c.googlers.com",
            "members": ["local-host/agent-1", "host2/remote-agent-2"],
            "lease_seconds": 60
        }
        
        res = rpc_handler.handle_update_watchlist(params)
        self.assertTrue(res)
        
        import time
        time.sleep(0.05)
        
        publish_event.assert_called_once_with(
            "remote-tracker-id-123",
            "watch_group_request",
            {
                "watch_id": "mac-electron-active-group",
                "group_id": "host:local:tanmayvijay.c.googlers.com",
                "members": ["local-host/agent-1", "host2/remote-agent-2"],
                "include_body": True,
                "lease_seconds": 60.0,
                "reply_to_tracker_id": registry_client.TRACKER_ID
            }
        )
        
        import tempfile, shutil
        temp_cache = tempfile.mkdtemp()
        orig_dir = state.GROUP_TIMELINE_DIR
        state.GROUP_TIMELINE_DIR = temp_cache
        try:
            group_id = "host:local:tanmayvijay.c.googlers.com"
            obs_payload = {
                "message_id": "msg-abc-123",
                "sender": "remote-agent-2",
                "recipient": "agent-1",
                "timestamp": "2026-05-26T23:48:00Z",
                "message": "hello registry roundtrip"
            }
            
            state.append_to_group_timeline(group_id, obs_payload)
            
            entries = state.read_group_timeline(group_id)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["message_id"], "msg-abc-123")
            
        finally:
            state.GROUP_TIMELINE_DIR = orig_dir
            shutil.rmtree(temp_cache)


if __name__ == "__main__":
    unittest.main()

