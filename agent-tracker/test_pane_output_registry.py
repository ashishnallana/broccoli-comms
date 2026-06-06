import json
import unittest

import pane_output_registry


class TestPaneOutputRegistry(unittest.TestCase):
    def _local_event(self):
        return {
            "seq": 7,
            "type": "agent_output_event",
            "agent_id": "agent-1",
            "agent_name": "agent1",
            "target_agent_id": "agent-1",
            "target_agent_name": "agent1",
            "source": "pipe-pane",
            "event_type": "progress",
            "confidence": 0.9,
            "payload": {"summary": "safe"},
            "state_patch": {"current_task": "reviewing"},
        }

    def test_from_local_event_builds_safe_registry_shape(self):
        event = pane_output_registry.from_local_event(
            self._local_event(),
            source_tracker_id="tracker-1",
            source_hostname="host1",
            ttl_seconds=60,
            now=1000.0,
        )

        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["source_tracker_id"], "tracker-1")
        self.assertEqual(event["source_hostname"], "host1")
        self.assertEqual(event["agent_id"], "agent-1")
        self.assertEqual(event["event_type"], "progress")
        self.assertEqual(event["payload"], {"summary": "safe"})
        self.assertEqual(event["state_patch"], {"current_task": "reviewing"})
        self.assertEqual(event["created_at"], 1000.0)
        self.assertEqual(event["expires_at"], 1060.0)
        encoded = json.dumps(event).lower()
        for forbidden in ("raw", "pipe_token", "token_hash", "tmux_pane", "tmux_socket", "cwd", "aliases", "swarms"):
            self.assertNotIn(forbidden, encoded)

    def test_event_id_is_deterministic_for_local_sequence(self):
        first = pane_output_registry.from_local_event(self._local_event(), source_tracker_id="tracker-1", source_hostname="host1", now=1000.0)
        second = pane_output_registry.from_local_event(self._local_event(), source_tracker_id="tracker-1", source_hostname="host1", now=1001.0)
        self.assertEqual(first["event_id"], second["event_id"])

    def test_forbidden_payload_and_top_level_keys_rejected_without_echo(self):
        malicious_value = "RAW_SECRET_VALUE"
        bad_payload = self._local_event()
        bad_payload["payload"] = {"raw_output": malicious_value}
        with self.assertRaises(pane_output_registry.RegistryEventValidationError) as payload_ctx:
            pane_output_registry.from_local_event(bad_payload, source_tracker_id="tracker-1", source_hostname="host1")
        self.assertEqual(payload_ctx.exception.code, "forbidden_event_key")
        self.assertNotIn(malicious_value, str(payload_ctx.exception))

        bad_top = self._local_event()
        bad_top["pipe_token_hash"] = malicious_value
        with self.assertRaises(pane_output_registry.RegistryEventValidationError) as top_ctx:
            pane_output_registry.from_local_event(bad_top, source_tracker_id="tracker-1", source_hostname="host1")
        self.assertEqual(top_ctx.exception.code, "forbidden_event_key")
        self.assertNotIn(malicious_value, str(top_ctx.exception))

    def test_validate_rejects_expired_event(self):
        event = pane_output_registry.from_local_event(self._local_event(), source_tracker_id="tracker-1", source_hostname="host1", ttl_seconds=5, now=1000.0)
        with self.assertRaises(pane_output_registry.RegistryEventValidationError) as ctx:
            pane_output_registry.validate_registry_event(event, now=1006.0)
        self.assertEqual(ctx.exception.code, "event_expired")

    def test_validate_clamps_far_future_expiry_to_max_ttl(self):
        event = pane_output_registry.from_local_event(
            self._local_event(),
            source_tracker_id="tracker-1",
            source_hostname="host1",
            ttl_seconds=60,
            now=1000.0,
        )
        event["expires_at"] = event["created_at"] + 10_000_000

        normalized = pane_output_registry.validate_registry_event(event, now=1001.0)

        self.assertEqual(normalized["ttl_seconds"], float(pane_output_registry.MAX_TTL_SECONDS))
        self.assertEqual(normalized["expires_at"], normalized["created_at"] + pane_output_registry.MAX_TTL_SECONDS)

    def test_validate_clamped_expiry_can_make_old_event_expired(self):
        event = pane_output_registry.from_local_event(
            self._local_event(),
            source_tracker_id="tracker-1",
            source_hostname="host1",
            ttl_seconds=60,
            now=1000.0,
        )
        event["expires_at"] = event["created_at"] + 10_000_000
        with self.assertRaises(pane_output_registry.RegistryEventValidationError) as ctx:
            pane_output_registry.validate_registry_event(event, now=1000.0 + pane_output_registry.MAX_TTL_SECONDS + 1)
        self.assertEqual(ctx.exception.code, "event_expired")

    def test_to_remote_observer_event_is_safe_and_watchable(self):
        registry_event = pane_output_registry.from_local_event(self._local_event(), source_tracker_id="tracker-1", source_hostname="host1")
        observer = pane_output_registry.to_remote_observer_event(registry_event)

        self.assertEqual(observer["source"], "registry-pane-output")
        self.assertEqual(observer["target_agent_id"], "host1/agent-1")
        self.assertEqual(observer["target_agent_name"], "host1/agent1")
        self.assertEqual(observer["registry_event_id"], registry_event["event_id"])
        self.assertNotIn("raw", json.dumps(observer).lower())
        self.assertNotIn("token", json.dumps(observer).lower())


if __name__ == "__main__":
    unittest.main()
