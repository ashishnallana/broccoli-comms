import json
import unittest
from unittest import mock

import registry_client


class TestRegistryClientStatus(unittest.TestCase):
    def test_record_sync_result_preserves_other_registry_entries(self):
        existing = {
            "registries": {
                "lab": {
                    "connected": True,
                    "registry_url": "https://lab.example",
                    "last_success": 100.0,
                }
            }
        }
        client = registry_client.RegistryClient(name="corp", url="https://corp.example")
        with mock.patch.object(registry_client.time, "time", return_value=120.0):
            payload = registry_client._registry_status_payload(200, "heartbeat", existing, client)
        self.assertIn("lab", payload["registries"])
        self.assertIn("corp", payload["registries"])
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["last_success"], 120.0)

    def test_record_sync_result_uses_file_lock(self):
        opened = mock.mock_open(read_data=json.dumps({"registries": {}}))
        fake_file = opened()
        client = registry_client.RegistryClient(name="corp", url="https://corp.example")
        with mock.patch.object(registry_client, "STATUS_PATH", "/tmp/status.json"), \
             mock.patch("os.makedirs"), \
             mock.patch("builtins.open", opened), \
             mock.patch.object(registry_client.fcntl, "flock") as flock:
            registry_client._record_sync_result(200, "heartbeat", client)
        flock.assert_any_call(fake_file.fileno(), registry_client.fcntl.LOCK_EX)
        flock.assert_any_call(fake_file.fileno(), registry_client.fcntl.LOCK_UN)


if __name__ == "__main__":
    unittest.main()
