import unittest
from unittest import mock
import tempfile
import shutil
import json
import os

import monitor
import state


class TestMonitor(unittest.TestCase):
    def setUp(self):
        state.state = {}
        state.name_index = {}
        state.pane_index = {}
        self.test_dir = tempfile.mkdtemp()
        self.original_inbox_dir = state.INBOX_DIR
        state.INBOX_DIR = self.test_dir

    def tearDown(self):
        state.INBOX_DIR = self.original_inbox_dir
        shutil.rmtree(self.test_dir)


    def test_get_liveness_phase_from_heartbeat(self):
        now = 100.0
        self.assertEqual(monitor.get_liveness_phase({"last_heartbeat": 95.0}, now), "fresh")
        self.assertEqual(monitor.get_liveness_phase({"last_heartbeat": 75.0}, now), "stale")
        self.assertEqual(monitor.get_liveness_phase({"last_heartbeat": 60.0}, now), "expired")

    def test_get_liveness_phase_from_recovered_at(self):
        now = 100.0
        self.assertEqual(monitor.get_liveness_phase({"recovered_at": 95.0}, now), "fresh")
        self.assertEqual(monitor.get_liveness_phase({"recovered_at": 75.0}, now), "stale")
        self.assertEqual(monitor.get_liveness_phase({"recovered_at": 60.0}, now), "expired")

    def test_get_liveness_phase_none(self):
        self.assertEqual(monitor.get_liveness_phase({}, 100.0), "none")

    @mock.patch("tmux_util.list_panes", return_value=[{"pane_id": "%1", "pane_active": False}])
    @mock.patch("state.discover_agent_process", return_value={"pid": 321, "comm": "pi"})
    def test_monitor_once_keeps_expired_agent_with_live_pane_process(self, _discover, _list_panes):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "unknown",
                "tmux_pane": "%1",
                "recovered_at": 60.0,
                "wrapper_pid": 123,
                "agent_cmd": "pi",
            },
        )

        monitor.monitor_once(now=100.0)

        info = state.get_agent("agent1")
        self.assertIsNotNone(info)
        self.assertEqual(info["pid"], 321)
        self.assertIsNone(info["wrapper_pid"])

    @mock.patch("tmux_util.list_panes", return_value=[{"pane_id": "%1", "pane_active": False}])
    @mock.patch("state.discover_agent_process", return_value=None)
    def test_monitor_once_removes_expired_agent_without_live_pane_process(self, _discover, _list_panes):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "unknown",
                "tmux_pane": "%1",
                "recovered_at": 60.0,
                "wrapper_pid": 123,
                "agent_cmd": "pi",
            },
        )

        monitor.monitor_once(now=100.0)

        self.assertIsNone(state.get_agent("agent1"))

    @mock.patch("tmux_util.list_panes", return_value=[{"pane_id": "%1", "pane_active": False}])
    @mock.patch("monitor.is_process_alive", return_value=False)
    @mock.patch("state.discover_agent_process", return_value=None)
    def test_kill_9_wrapper_evicts_agent_after_grace_period(self, _discover, _alive, _list_panes):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "working",
                "tmux_pane": "%1",
                "last_heartbeat": 60.0,
                "wrapper_pid": 999,
                "agent_cmd": "jetski",
            },
        )

        monitor.monitor_once(now=100.0)

        self.assertIsNone(state.get_agent("agent1"))

    @mock.patch("tmux_util.send_keys")
    @mock.patch("tmux_util.list_panes", return_value=[{"pane_id": "%1", "pane_active": False}])
    def test_check_unread_messages_reminds_alive_agent(self, _list_panes, mock_send_keys):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "idle",
                "tmux_pane": "%1",
                "tmux_socket": "/tmp/tmux.sock",
            },
        )

        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        messages = [
            {"sender": "alice", "read": False, "message": "hello"},
            {"sender": "bob", "read": False, "message": "world"},
            {"sender": "alice", "read": True, "message": "old message"},
        ]
        with open(inbox_path, "w") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

        monitor.check_unread_messages_and_remind()

        calls = [
            mock.call("%1", "New message in inbox from alice", "/tmp/tmux.sock"),
            mock.call("%1", "New message in inbox from bob", "/tmp/tmux.sock"),
        ]
        mock_send_keys.assert_has_calls(calls, any_order=True)
        self.assertEqual(mock_send_keys.call_count, 2)

        with open(inbox_path, "r") as f:
            remaining_msgs = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(remaining_msgs, messages)

    @mock.patch("tmux_util.send_keys")
    @mock.patch("tmux_util.list_panes", return_value=[])
    def test_check_unread_messages_cleans_up_gone_agent(self, _list_panes, mock_send_keys):
        state.set_agent(
            "agent1",
            {
                "agent_id": "id-1",
                "status": "idle",
                "tmux_pane": "%1",
            },
        )

        inbox_path = os.path.join(state.INBOX_DIR, "id-1.inbox")
        messages = [
            {"sender": "alice", "read": False, "message": "hello"},
            {"sender": "bob", "read": False, "message": "world"},
            {"sender": "alice", "read": True, "message": "old message"},
        ]
        with open(inbox_path, "w") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

        monitor.check_unread_messages_and_remind()

        mock_send_keys.assert_not_called()

        with open(inbox_path, "r") as f:
            updated_msgs = [json.loads(line) for line in f if line.strip()]

        expected_messages = [
            {"sender": "alice", "read": True, "message": "hello", "status": "no-receiver"},
            {"sender": "bob", "read": True, "message": "world", "status": "no-receiver"},
            {"sender": "alice", "read": True, "message": "old message"},
        ]
        self.assertEqual(updated_msgs, expected_messages)


if __name__ == "__main__":
    unittest.main()

