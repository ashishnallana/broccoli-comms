import json
import os
import unittest
from unittest import mock

import registry_client


class TestRegistryClientUpdates(unittest.TestCase):
    def test_push_agent_update_fans_out_to_all_configured_registries(self):
        payload = json.dumps([
            {"name": "r1", "url": "https://r1.example", "token": "one"},
            {"name": "r2", "url": "https://r2.example", "token": "two"},
        ])
        clients = []
        def fake_thread(target, daemon=False):
            class FakeThread:
                def start(self_inner):
                    target()
            return FakeThread()
        def fake_request(self, method, path, body=None, timeout=3):
            clients.append((self.name, self.url, method, path, body))
            return 200, {}
        with mock.patch.dict(os.environ, {"AGENT_REGISTRIES_JSON": payload}, clear=True), \
             mock.patch.object(registry_client.threading, "Thread", fake_thread), \
             mock.patch.object(registry_client.RegistryClient, "request", fake_request):
            registry_client.push_agent_update("a1", "working")
        self.assertEqual(clients, [
            ("r1", "https://r1.example", "POST", f"/trackers/{registry_client.TRACKER_ID}/agent-update", {"agent_id": "a1", "status": "working"}),
            ("r2", "https://r2.example", "POST", f"/trackers/{registry_client.TRACKER_ID}/agent-update", {"agent_id": "a1", "status": "working"}),
        ])


if __name__ == "__main__":
    unittest.main()
