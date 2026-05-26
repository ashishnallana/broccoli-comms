import unittest
from unittest import mock
import state

class TestState(unittest.TestCase):
    def setUp(self):
        state.state = {}  # Reset state
        state.name_index = {}
        state.pane_index = {}

    def test_set_get_agent(self):
        state.set_agent("agent1", {"status": "idle", "agent_id": "id-1"})
        info = state.get_agent("agent1")
        self.assertEqual(info["status"], "idle")
        self.assertEqual(info["agent_id"], "id-1")
        self.assertEqual(state.get_agent("id-1")["status"], "idle")

    def test_update_agent(self):
        state.set_agent("agent1", {"status": "idle"})
        self.assertTrue(state.update_agent("agent1", status="working"))
        self.assertEqual(state.get_agent("agent1")["status"], "working")

    def test_rename_agent(self):
        state.set_agent("agent1", {"status": "idle", "agent_id": "id-1"})
        self.assertTrue(state.rename_agent("agent1", "agent2"))
        self.assertIsNotNone(state.get_agent("agent1"))
        self.assertEqual(state.get_agent("agent2")["status"], "idle")
        self.assertEqual(state.get_agent("agent2")["agent_id"], "id-1")
        self.assertEqual(state.get_agent("agent2")["aliases"], ["agent1"])
        self.assertEqual(state.get_agent_name_by_id("id-1"), "agent2")

    def test_delete_agent(self):
        state.set_agent("agent1", {"status": "idle", "agent_id": "id-1"})
        state.rename_agent("agent1", "agent2")
        state.delete_agent("id-1")
        self.assertIsNone(state.get_agent("agent2"))
        self.assertIsNone(state.get_agent("agent1"))
        self.assertIsNone(state.get_agent("id-1"))

    def test_upsert_by_agent_id_replaces_old_name(self):
        state.set_agent("agent1", {"status": "idle", "agent_id": "id-1", "tmux_pane": "%1"})
        state.set_agent("agent2", {"status": "working", "agent_id": "id-1", "tmux_pane": "%2"})
        self.assertIsNotNone(state.get_agent("agent1"))
        self.assertEqual(state.get_agent("agent2")["status"], "working")
        self.assertEqual(state.get_agent("agent2")["aliases"], ["agent1"])
        self.assertEqual(state.get_agent_name_by_id("id-1"), "agent2")
        self.assertIsNone(state.get_agent_name_by_pane("%1"))
        self.assertEqual(state.get_agent_name_by_pane("%2"), "agent2")

    def test_name_reuse_evicts_old_agent_id(self):
        state.set_agent("agent1", {"status": "spawning", "agent_id": "spawn-id", "tmux_pane": "%1"})
        state.set_agent("agent1", {"status": "idle", "agent_id": "real-id", "tmux_pane": "%3"})
        self.assertIsNone(state.get_agent("spawn-id"))
        self.assertEqual(state.get_agent("agent1")["agent_id"], "real-id")
        self.assertEqual(state.get_agent_name_by_id("real-id"), "agent1")
        self.assertIsNone(state.get_agent_name_by_pane("%1"))
        self.assertEqual(state.get_agent_name_by_pane("%3"), "agent1")

    def test_update_agent_moves_pane_index(self):
        state.set_agent("agent1", {"status": "idle", "agent_id": "id-1", "tmux_pane": "%1"})
        self.assertTrue(state.update_agent("agent1", tmux_pane="%2"))
        self.assertIsNone(state.get_agent_name_by_pane("%1"))
        self.assertEqual(state.get_agent_name_by_pane("%2"), "agent1")

    def test_delete_agent_clears_pane_index(self):
        state.set_agent("agent1", {"status": "idle", "agent_id": "id-1", "tmux_pane": "%1"})
        state.delete_agent("agent1")
        self.assertIsNone(state.get_agent_name_by_pane("%1"))

    @mock.patch("state.discover_agent_process", return_value=None)
    @mock.patch("tmux_util.get_pane_info", return_value={"tty": "/dev/pts/1", "session": "sess", "pid": 101})
    @mock.patch("tmux_util.list_panes", return_value=[{
        "pane_id": "%1",
        "agent_name": "agent1",
        "agent_id": "id-1",
        "agent_uuid": "id-1",
        "agent_type": "pi",
        "agent_cmd": "pi",
        "pane_active": False,
    }])
    def test_init_state_recovers_without_live_process(self, _list_panes, _get_pane_info, _discover_agent_process):
        state.init_state()
        info = state.get_agent("agent1")
        self.assertIsNotNone(info)
        self.assertEqual(info["agent_id"], "id-1")
        self.assertEqual(info["status"], "unknown")
        self.assertIsNone(info["pid"])

    def test_get_agents_for_registry_omits_local_fields(self):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "tmux_pane": "%1", "session": "s", "cwd": "/work/project"})
        self.assertEqual(state.get_agents_for_registry(), [{
            "agent_id": "id-1", "name": "agent1", "aliases": [], "status": "idle", "agent_type": "unknown", "agent_cmd": "unknown", "cwd": "/work/project"
        }])

    def test_get_agents_for_registry_skips_no_registry_agents(self):
        state.set_agent("agent1", {"agent_id": "id-1", "status": "idle", "no_registry": True})
        state.set_agent("agent2", {"agent_id": "id-2", "status": "working"})
        self.assertEqual(state.get_agents_for_registry(), [{
            "agent_id": "id-2", "name": "agent2", "aliases": [], "status": "working", "agent_type": "unknown", "agent_cmd": "unknown", "cwd": None
        }])

    def test_event_buffer_bounds_and_eviction(self):
        state.events = []
        state.event_sequence_id = 0
        # Publish 550 events
        for i in range(550):
            state.publish_event("dummy_event", {"data": i})
        # Check events length is capped at MAX_EVENTS (500)
        self.assertEqual(len(state.events), 500)
        # Oldest event seq should be 51
        self.assertEqual(state.events[0]["seq"], 51)
        # Newest event seq should be 550
        self.assertEqual(state.events[-1]["seq"], 550)

    def test_watchlist_lease_and_sweeping(self):
        state.active_watchlists = {}
        # Register a lease for client1 expiring in 0.1 seconds, and client2 expiring in 10 seconds
        state.update_watchlist_lease("client1", ["agent1"], 0.1)
        state.update_watchlist_lease("client2", ["agent2"], 10.0)
        
        self.assertIn("client1", state.active_watchlists)
        self.assertIn("client2", state.active_watchlists)
        
        # Sweep immediately - nothing should be swept
        state.sweep_expired_watchlists()
        self.assertIn("client1", state.active_watchlists)
        self.assertIn("client2", state.active_watchlists)
        
        # Sleep 0.15 seconds and sweep - client1 should be swept, client2 remains
        import time
        time.sleep(0.15)
        state.sweep_expired_watchlists()
        self.assertNotIn("client1", state.active_watchlists)
        self.assertIn("client2", state.active_watchlists)

    def test_group_timeline_persistence_and_deduplication(self):
        import shutil, tempfile
        temp_cache = tempfile.mkdtemp()
        orig_dir = state.GROUP_TIMELINE_DIR
        state.GROUP_TIMELINE_DIR = temp_cache
        try:
            group_id = "host:local:my-test-machine"
            payload_1 = {
                "message_id": "msg-1",
                "sender": "agent-1",
                "recipient": "agent-2",
                "timestamp": "2026-05-26T23:45:00Z",
                "message": "hello local"
            }
            payload_2 = {
                "message_id": "msg-2",
                "sender": "agent-2",
                "recipient": "agent-1",
                "timestamp": "2026-05-26T23:46:00Z",
                "message": "reply"
            }
            
            state.append_to_group_timeline(group_id, payload_1)
            state.append_to_group_timeline(group_id, payload_2)
            state.append_to_group_timeline(group_id, payload_1)
            
            entries = state.read_group_timeline(group_id)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["message_id"], "msg-1")
            self.assertEqual(entries[1]["message_id"], "msg-2")
            
        finally:
            state.GROUP_TIMELINE_DIR = orig_dir
            shutil.rmtree(temp_cache)

if __name__ == '__main__':
    unittest.main()
