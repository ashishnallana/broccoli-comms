import json
import unittest

import pane_output_parser


class TestPaneOutputParser(unittest.TestCase):
    def test_structured_event_valid_path(self):
        line = pane_output_parser.STRUCTURED_PREFIX + " " + json.dumps({
            "event_type": "status_update",
            "confidence": 0.95,
            "payload": {"reason": "structured"},
            "state_patch": {"status": "working", "waiting_approval": False, "last_activity": True},
        }) + "\n"

        parser_state, events, errors = pane_output_parser.parse_chunk(
            None, line, agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["agent_id"], "id-1")
        self.assertEqual(event["agent_name"], "agent1")
        self.assertEqual(event["source"], "pipe-pane")
        self.assertEqual(event["event_type"], "status_update")
        self.assertEqual(event["state_patch"]["status"], "working")
        self.assertEqual(event["state_patch"]["last_activity"], 1000.0)
        self.assertNotIn("buffer", event)
        self.assertEqual(parser_state["buffer"], "")

    def test_malformed_structured_event_rejected_without_events(self):
        _state, events, errors = pane_output_parser.parse_chunk(
            None,
            pane_output_parser.STRUCTURED_PREFIX + " {bad json}\n",
            agent_id="id-1",
            agent_name="agent1",
            pipe_instance_id="pipe-1",
            now=1000.0,
        )
        self.assertEqual(events, [])
        self.assertTrue(errors)

    def test_raw_chunk_never_appears_in_event(self):
        secret = "RAW_SECRET_CHUNK"
        line = pane_output_parser.STRUCTURED_PREFIX + " " + json.dumps({
            "event_type": "safe_event",
            "payload": {"kind": "safe"},
        }) + "\n" + secret

        _state, events, errors = pane_output_parser.parse_chunk(
            None, line, agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(events), 1)
        self.assertNotIn(secret, json.dumps(events))

    def test_state_patch_allowlist_rejects_identity_and_pipe_fields(self):
        for forbidden in ["agent_id", "uuid", "aliases", "swarms", "cwd", "tmux_socket", "tmux_pane", "pipe_token", "pipe_instance_id"]:
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(pane_output_parser.ParserValidationError):
                    pane_output_parser.validate_state_patch({forbidden: "evil"}, now=1000.0)

    def test_status_enum_validation(self):
        self.assertEqual(pane_output_parser.validate_state_patch({"status": "idle"}, now=1000.0), {"status": "idle"})
        with self.assertRaises(pane_output_parser.ParserValidationError):
            pane_output_parser.validate_state_patch({"status": "pwned"}, now=1000.0)

    def test_bounded_string_validation(self):
        patch = pane_output_parser.validate_state_patch({"current_task": "short task", "last_permission_prompt": "prompt"}, now=1000.0)
        self.assertEqual(patch["current_task"], "short task")
        with self.assertRaises(pane_output_parser.ParserValidationError):
            pane_output_parser.validate_state_patch({"current_task": "x" * (pane_output_parser.MAX_CURRENT_TASK + 1)}, now=1000.0)

    def test_permission_status_and_current_task_examples(self):
        line = pane_output_parser.STRUCTURED_PREFIX + " " + json.dumps({
            "event_type": "permission_request",
            "payload": {"hint": "approval_needed"},
            "state_patch": {
                "status": "waiting",
                "waiting_approval": True,
                "last_permission_prompt": "permission prompt detected",
                "current_task": "awaiting approval",
            },
        }) + "\n"
        _state, events, errors = pane_output_parser.parse_chunk(None, line, agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0)
        self.assertEqual(errors, [])
        self.assertEqual(events[0]["state_patch"]["status"], "waiting")
        self.assertTrue(events[0]["state_patch"]["waiting_approval"])

    def test_parser_handles_partial_line_boundaries(self):
        state1, events1, errors1 = pane_output_parser.parse_chunk(None, "@@BROCCOLI_EVENT@@ {\"event_type\"", agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0)
        self.assertEqual(events1, [])
        self.assertEqual(errors1, [])
        state2, events2, errors2 = pane_output_parser.parse_chunk(state1, ": \"done\", \"payload\": {}}\n", agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1001.0)
        self.assertEqual(errors2, [])
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0]["event_type"], "done")
        self.assertEqual(state2["buffer"], "")

    def test_structured_event_priority_over_heuristic(self):
        line = pane_output_parser.STRUCTURED_PREFIX + " " + json.dumps({
            "event_type": "explicit",
            "payload": {"note": "status: idle permission approval"},
            "state_patch": {"status": "working"},
        }) + "\n"
        _state, events, errors = pane_output_parser.parse_chunk(None, line, agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0)
        self.assertEqual(errors, [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "explicit")
        self.assertEqual(events[0]["state_patch"]["status"], "working")

    def test_heuristic_debounce(self):
        parser_state, events1, _errors1 = pane_output_parser.parse_chunk(None, "status: working\n", agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0)
        parser_state, events2, _errors2 = pane_output_parser.parse_chunk(parser_state, "status: idle\n", agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1001.0)
        parser_state, events3, _errors3 = pane_output_parser.parse_chunk(parser_state, "status: idle\n", agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1006.0)
        self.assertEqual(len(events1), 1)
        self.assertEqual(events2, [])
        self.assertEqual(len(events3), 1)

    def test_payload_rejects_raw_chunk_keys(self):
        with self.assertRaises(pane_output_parser.ParserValidationError):
            pane_output_parser.validate_output_event({"event_type": "bad", "payload": {"chunk": "raw"}}, agent_id="id-1", agent_name="agent1", now=1000.0)

    def test_malicious_state_patch_key_and_value_not_echoed_in_errors(self):
        secret_key = "RAW_SECRET_CHUNK"
        secret_value = "TOKEN_SECRET_VALUE"
        line = pane_output_parser.STRUCTURED_PREFIX + " " + json.dumps({
            "event_type": "bad_patch",
            "payload": {"safe": "ok"},
            "state_patch": {secret_key: secret_value},
        }) + "\n"

        _state, events, errors = pane_output_parser.parse_chunk(
            None, line, agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0
        )

        self.assertEqual(events, [])
        self.assertEqual(errors, ["state_patch_field_not_allowed"])
        self.assertNotIn(secret_key, json.dumps(errors))
        self.assertNotIn(secret_value, json.dumps(errors))

    def test_forbidden_payload_key_variants_are_rejected_without_echo(self):
        forbidden_keys = [
            "raw_output", "rawOutput", "raw-output", "rawChunk", "pane_output",
            "paneOutput", "output", "pipe_token_hash", "pipeTokenHash",
            "token_hash", "tokenHash", "pipe_token_sha256", "pipeTokenSha256",
        ]
        secret_value = "RAW_SECRET_VALUE"
        for key in forbidden_keys:
            with self.subTest(key=key):
                line = pane_output_parser.STRUCTURED_PREFIX + " " + json.dumps({
                    "event_type": "bad_payload",
                    "payload": {key: secret_value},
                }) + "\n"
                _state, events, errors = pane_output_parser.parse_chunk(
                    None, line, agent_id="id-1", agent_name="agent1", pipe_instance_id="pipe-1", now=1000.0
                )
                self.assertEqual(events, [])
                self.assertEqual(errors, ["forbidden_event_key"])
                self.assertNotIn(key, json.dumps(errors))
                self.assertNotIn(secret_value, json.dumps(errors))

    def test_valid_non_raw_payload_keys_still_work(self):
        event = pane_output_parser.validate_output_event(
            {"event_type": "ok", "payload": {"summary": "safe", "status_code": 200}},
            agent_id="id-1",
            agent_name="agent1",
            now=1000.0,
        )
        self.assertEqual(event["payload"]["summary"], "safe")
        self.assertEqual(event["payload"]["status_code"], 200)


if __name__ == "__main__":
    unittest.main()
