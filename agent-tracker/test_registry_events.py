import unittest
from unittest import mock

import registry_client
import state


class TestRegistryEvents(unittest.TestCase):
    def setUp(self):
        state.state = {}
        state.name_index = {}
        state.pane_index = {}

    def test_event_loop_publishes_local_message_read_and_acks(self):
        event = {
            "event_id": "e1",
            "event_type": "message_read",
            "payload": {"message_id": "m1", "sender_agent_id": "s1", "reader_agent_id": "r1", "reader_agent_name": "remote"},
        }
        state.set_agent("agent-communicator", {"agent_id": "s1"})
        with mock.patch.object(registry_client, "fetch_events", side_effect=[(200, {"events": [event]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_event", return_value=200) as ack, \
             mock.patch.object(state, "publish_event") as publish:
            with self.assertRaises(SystemExit):
                registry_client._event_loop()
        publish.assert_called_once_with("message_read", {"target_agent_id": "r1", "target_agent_name": "remote", "sender": "agent-communicator", "message_id": "m1"})
        ack.assert_called_once_with("e1")

    def test_event_loop_publishes_remote_delivered_and_notified(self):
        events = [
            {"event_id": "e1", "event_type": "message_delivered", "payload": {"message_id": "m1", "sender_agent_id": "s1", "receiver_agent_id": "r1", "receiver_agent_name": "remote"}},
            {"event_id": "e2", "event_type": "message_notified", "payload": {"message_id": "m1", "sender_agent_id": "s1", "receiver_agent_id": "r1", "receiver_agent_name": "remote"}},
        ]
        state.set_agent("agent-communicator", {"agent_id": "s1"})
        with mock.patch.object(registry_client, "fetch_events", side_effect=[(200, {"events": events}), SystemExit]), \
             mock.patch.object(registry_client, "ack_event", return_value=200) as ack, \
             mock.patch.object(state, "publish_event") as publish:
            with self.assertRaises(SystemExit):
                registry_client._event_loop()
        publish.assert_any_call("message_delivered", {"target_agent_id": "r1", "target_agent_name": "remote", "sender": "agent-communicator", "message_id": "m1"})
        publish.assert_any_call("message_notified", {"target_agent_id": "r1", "target_agent_name": "remote", "sender": "agent-communicator", "message_id": "m1"})
        self.assertEqual(ack.call_count, 2)

    @mock.patch("registry_client._handle_remote_pane_capture")
    def test_event_loop_handles_pane_capture_request(self, mock_handler):
        event = {
            "event_id": "e3",
            "event_type": "pane_capture_request",
            "payload": {
                "request_id": "req-123",
                "source": "alice",
                "target": "host-b/bob",
                "format": "markdown",
                "last": 150,
                "include_ansi": False,
                "note": "Please review"
            }
        }
        
        with mock.patch.object(registry_client, "fetch_events", side_effect=[(200, {"events": [event]}), SystemExit]), \
             mock.patch.object(registry_client, "ack_event", return_value=200) as mock_ack:
            with self.assertRaises(SystemExit):
                registry_client._event_loop()
                
        mock_handler.assert_called_once_with({
            "request_id": "req-123",
            "source": "alice",
            "target": "host-b/bob",
            "format": "markdown",
            "last": 150,
            "include_ansi": False,
            "note": "Please review"
        })
        mock_ack.assert_called_once_with("e3")

    @mock.patch("rpc_handler.handle_capture_pane")
    @mock.patch("rpc_handler.handle_send_message")
    def test_handle_remote_pane_capture_success(self, mock_send, mock_capture):
        mock_capture.return_value = {
            "agent_name": "alice",
            "agent_id": "id-alice",
            "tmux_pane": "%1",
            "session": "sess-alice",
            "copy_mode": False,
            "captured_at": "2026-05-23T12:00:00Z",
            "lines_requested": 150,
            "content": "Alice Screen Content"
        }
        mock_send.return_value = True
        
        payload = {
            "request_id": "req-123",
            "source": "alice",
            "target": "host-b/bob",
            "format": "markdown",
            "last": 150,
            "include_ansi": False,
            "note": "Please review"
        }
        
        registry_client._handle_remote_pane_capture(payload)
        
        mock_capture.assert_called_once_with({
            "last_lines": 150,
            "include_ansi": False,
            "agent_name": "alice"
        })
        
        expected_msg = (
            "### Pane Capture Snapshot from alice (id-alice)\n"
            "- **Pane:** %1\n"
            "- **Session:** sess-alice\n"
            "- **Copy Mode:** Inactive\n"
            "- **Captured At:** 2026-05-23T12:00:00Z\n"
            "- **User Note:** Please review\n"
            "\n```\n"
            "Alice Screen Content\n"
            "```\n"
        )
        mock_send.assert_called_once_with({
            "target_address": "host-b/bob",
            "message": expected_msg,
            "sender_id": "id-alice",
            "sender_name": "alice"
        })


if __name__ == "__main__":
    unittest.main()
