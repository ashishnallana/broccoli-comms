import json
import os
import unittest
from unittest import mock

import registry_client


class TestRegistryClientRouting(unittest.TestCase):
    def test_unqualified_send_uses_single_json_configured_registry(self):
        client = registry_client.RegistryClient("r1", "https://r1.example")
        sent = []
        def fake_send(*args):
            sent.append(args)
            return 202, {"sent_by": "r1"}
        with mock.patch.object(registry_client, "load_registry_clients", return_value=[client]), \
             mock.patch.object(client, "send_remote_message", fake_send):
            status, body = registry_client.send_remote_message("sender", "s1", "t1", "host1", "agent1", "hello")
        self.assertEqual((status, body), (202, {"sent_by": "r1"}))
        self.assertEqual(sent, [("sender", "s1", "t1", "host1", "agent1", "hello", None, None, None)])

    def test_unqualified_send_routes_to_single_matching_registry(self):
        clients = [
            registry_client.RegistryClient("r1", "https://r1.example"),
            registry_client.RegistryClient("r2", "https://r2.example"),
        ]
        def fake_request(self, method, path, payload=None, timeout=3):
            if path == "/agents":
                agents = [] if self.name == "r1" else [{"hostname": "host2", "name": "agent2", "agent_id": "a2"}]
                return 200, {"agents": agents}
            return 202, {"sent_by": self.name}
        with mock.patch.object(registry_client, "load_registry_clients", return_value=clients), \
             mock.patch.object(registry_client.RegistryClient, "request", fake_request):
            status, body = registry_client.send_remote_message("sender", "s1", "t1", "host2", "agent2", "hello")
        self.assertEqual((status, body), (202, {"sent_by": "r2"}))

    def test_unqualified_send_errors_when_hostname_is_ambiguous(self):
        clients = [
            registry_client.RegistryClient("r1", "https://r1.example"),
            registry_client.RegistryClient("r2", "https://r2.example"),
        ]
        def fake_request(self, method, path, payload=None, timeout=3):
            if path == "/agents":
                return 200, {"agents": [{"hostname": "shared", "name": "agent", "agent_id": self.name}]}
            return 202, {}
        with mock.patch.object(registry_client, "load_registry_clients", return_value=clients), \
             mock.patch.object(registry_client.RegistryClient, "request", fake_request):
            status, body = registry_client.send_remote_message("sender", "s1", "t1", "shared", "agent", "hello")
        self.assertEqual(status, 409)
        self.assertIn("Ambiguous", body["message"])
        self.assertIn("r1:shared/agent", body["message"])

    def test_remote_pane_input_uses_pane_inputs_endpoint_and_ids(self):
        client = registry_client.RegistryClient("r1", "https://r1.example")
        sent = []
        def fake_request(method, path, payload=None, timeout=3):
            sent.append((method, path, payload))
            return 202, {"pane_input_id": payload["pane_input_id"], "request_id": payload["request_id"]}
        with mock.patch.object(registry_client, "load_registry_clients", return_value=[client]), \
             mock.patch.object(client, "request", fake_request):
            status, body = registry_client.send_remote_pane_input("sender", "s1", "t1", "host1", "agent1", "text", text="hello", submit=False, pane_input_id="pi-1", request_id="req-1")
        self.assertEqual(status, 202)
        self.assertEqual(body["pane_input_id"], "pi-1")
        self.assertEqual(sent[0][0:2], ("POST", "/pane-inputs"))
        self.assertEqual(sent[0][2]["target_agent_name"], "agent1")
        self.assertEqual(sent[0][2]["target_hostname"], "host1")
        self.assertEqual(sent[0][2]["submit"], False)

    def test_remote_pane_input_routes_to_matching_registry(self):
        clients = [
            registry_client.RegistryClient("r1", "https://r1.example"),
            registry_client.RegistryClient("r2", "https://r2.example"),
        ]
        def fake_request(self, method, path, payload=None, timeout=3):
            if path == "/agents":
                agents = [] if self.name == "r1" else [{"hostname": "host2", "name": "agent2", "agent_id": "a2"}]
                return 200, {"agents": agents}
            return 202, {"sent_by": self.name}
        with mock.patch.object(registry_client, "load_registry_clients", return_value=clients), \
             mock.patch.object(registry_client.RegistryClient, "request", fake_request):
            status, body = registry_client.send_remote_pane_input("sender", "s1", "t1", "host2", "agent2", "keys", keys=["Enter"], pane_input_id="pi-1")
        self.assertEqual((status, body), (202, {"sent_by": "r2"}))


if __name__ == "__main__":
    unittest.main()
