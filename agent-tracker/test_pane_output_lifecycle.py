import os
import unittest
from unittest import mock

import pane_output_lifecycle
import state


def _unprefixed(args):
    if args[:2] == ["-S", "sock"]:
        return args[2:]
    return args


class TestPaneOutputLifecycle(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(os.environ, {"AGENT_TRACKER_PANE_OUTPUT_ENABLED": "1"}, clear=False)
        self.env_patch.start()
        state.state = {}
        state.name_index = {}
        state.pane_index = {}
        state.set_agent("agent1", {
            "agent_id": "id-1",
            "status": "idle",
            "tmux_pane": "%1",
            "tmux_socket": "sock",
            "agent_type": "pi",
        })

    def tearDown(self):
        self.env_patch.stop()

    def test_tmux_args_uses_socket_prefix_for_run_tmux_cmd_api(self):
        args = pane_output_lifecycle._tmux_args(["display-message", "-p"], "sock")
        self.assertEqual(args, ["-S", "sock", "display-message", "-p"])

    def test_config_disabled_refuses_enable_without_metadata_mutation(self):
        with mock.patch.dict(os.environ, {"AGENT_TRACKER_PANE_OUTPUT_ENABLED": "0"}, clear=False), \
             mock.patch("tmux_util.run_tmux_cmd") as run_tmux:
            with self.assertRaises(RuntimeError):
                pane_output_lifecycle.enable_pane_output("id-1")

        run_tmux.assert_not_called()
        info = state.get_agent("id-1")
        self.assertFalse(info.get("pipe_output_enabled", False))
        self.assertIsNone(info.get("pipe_instance_id"))

    def test_agent_type_gate_refuses_unconfigured_type(self):
        with mock.patch.dict(os.environ, {"AGENT_TRACKER_PANE_OUTPUT_AGENT_TYPES": "codex"}, clear=False), \
             mock.patch("tmux_util.run_tmux_cmd") as run_tmux:
            with self.assertRaises(RuntimeError):
                pane_output_lifecycle.enable_pane_output("id-1")

        run_tmux.assert_not_called()
        self.assertFalse(state.get_agent("id-1").get("pipe_output_enabled", False))

    def test_enable_creates_fresh_instance_token_hash_and_attaches_pipe(self):
        calls = []
        def fake_tmux(args):
            calls.append(args)
            self.assertEqual(args[:2], ["-S", "sock"])
            if _unprefixed(args)[:3] == ["display-message", "-p", "-t"]:
                return "0|"
            return ""

        with mock.patch("tmux_util.run_tmux_cmd", side_effect=fake_tmux):
            result = pane_output_lifecycle.enable_pane_output("id-1")

        self.assertTrue(result["enabled"])
        self.assertTrue(result["attached"])
        info = state.get_agent("id-1")
        self.assertTrue(info["pipe_output_enabled"])
        self.assertEqual(info["pipe_instance_id"], result["pipe_instance_id"])
        self.assertEqual(info["pipe_tmux_pane"], "%1")
        self.assertIsNotNone(info["pipe_token_hash"])
        self.assertNotIn("pipe_token", info)
        pipe_calls = [_unprefixed(args) for args in calls if _unprefixed(args) and _unprefixed(args)[0] == "pipe-pane"]
        self.assertEqual(len(pipe_calls), 1)
        self.assertEqual(pipe_calls[0][:4], ["pipe-pane", "-o", "-t", "%1"])
        self.assertIn("pipe_reader.py", pipe_calls[0][4])
        self.assertIn("--agent-id id-1", pipe_calls[0][4])
        self.assertIn("--tmux-pane %1", pipe_calls[0][4])
        self.assertNotIn("pipe_token", json_safe(result))

    def test_status_response_does_not_expose_token_or_raw_output(self):
        state.configure_pane_output("id-1", pipe_instance_id="pipe-1", pipe_token="secret-token", tmux_pane="%1")

        result = pane_output_lifecycle.pane_output_status("id-1")

        combined = json_safe(result)
        self.assertIn("pipe-1", combined)
        self.assertNotIn("secret-token", combined)
        self.assertNotIn("pipe_token", combined)
        self.assertNotIn("raw", combined.lower())

    def test_enable_refuses_existing_non_broccoli_pipe(self):
        with mock.patch("tmux_util.run_tmux_cmd", return_value="1|"):
            with self.assertRaises(RuntimeError):
                pane_output_lifecycle.enable_pane_output("id-1")
        self.assertFalse(state.get_agent("id-1").get("pipe_output_enabled", False))

    def test_duplicate_enable_rotates_matching_broccoli_pipe_without_duplicate(self):
        state.configure_pane_output("id-1", pipe_instance_id="old-pipe", pipe_token="old-token", tmux_pane="%1")
        calls = []
        def fake_tmux(args):
            calls.append(args)
            if _unprefixed(args)[:3] == ["display-message", "-p", "-t"]:
                return "1|old-pipe"
            return ""

        with mock.patch("tmux_util.run_tmux_cmd", side_effect=fake_tmux):
            result = pane_output_lifecycle.enable_pane_output("id-1")

        self.assertNotEqual(result["pipe_instance_id"], "old-pipe")
        pipe_calls = [_unprefixed(args) for args in calls if _unprefixed(args) and _unprefixed(args)[0] == "pipe-pane"]
        self.assertEqual(pipe_calls[0], ["pipe-pane", "-t", "%1"])
        self.assertEqual(pipe_calls[1][:4], ["pipe-pane", "-o", "-t", "%1"])

    def test_enable_refuses_mismatched_broccoli_marker_without_detach(self):
        state.configure_pane_output("id-1", pipe_instance_id="stored-pipe", pipe_token="token", tmux_pane="%1")
        calls = []
        def fake_tmux(args):
            calls.append(args)
            if _unprefixed(args)[:3] == ["display-message", "-p", "-t"]:
                return "1|other-pipe"
            return ""

        with mock.patch("tmux_util.run_tmux_cmd", side_effect=fake_tmux):
            with self.assertRaises(RuntimeError):
                pane_output_lifecycle.enable_pane_output("id-1")

        pipe_calls = [_unprefixed(args) for args in calls if _unprefixed(args) and _unprefixed(args)[0] == "pipe-pane"]
        self.assertEqual(pipe_calls, [])
        self.assertEqual(state.get_agent("id-1")["pipe_instance_id"], "stored-pipe")

    def test_disable_clears_metadata_and_detaches_only_owned_pipe(self):
        state.configure_pane_output("id-1", pipe_instance_id="pipe-1", pipe_token="token", tmux_pane="%1")
        calls = []
        def fake_tmux(args):
            calls.append(args)
            if _unprefixed(args)[:3] == ["display-message", "-p", "-t"]:
                return "1|pipe-1"
            return ""

        with mock.patch("tmux_util.run_tmux_cmd", side_effect=fake_tmux):
            result = pane_output_lifecycle.disable_pane_output("id-1")

        self.assertFalse(result["enabled"])
        self.assertTrue(result["detached"])
        info = state.get_agent("id-1")
        self.assertFalse(info["pipe_output_enabled"])
        self.assertIsNone(info["pipe_instance_id"])
        self.assertIn(["pipe-pane", "-t", "%1"], [_unprefixed(args) for args in calls])
        self.assertTrue(all(args[:2] == ["-S", "sock"] for args in calls))

    def test_disable_does_not_detach_non_matching_broccoli_pipe(self):
        state.configure_pane_output("id-1", pipe_instance_id="pipe-1", pipe_token="token", tmux_pane="%1")
        calls = []
        def fake_tmux(args):
            calls.append(args)
            if _unprefixed(args)[:3] == ["display-message", "-p", "-t"]:
                return "1|other-pipe"
            return ""

        with mock.patch("tmux_util.run_tmux_cmd", side_effect=fake_tmux):
            result = pane_output_lifecycle.disable_pane_output("id-1")

        self.assertFalse(result["detached"])
        self.assertNotIn(["pipe-pane", "-t", "%1"], [_unprefixed(args) for args in calls])
        self.assertFalse(state.get_agent("id-1")["pipe_output_enabled"])

    def test_remote_address_cannot_be_piped_locally(self):
        with self.assertRaises(ValueError):
            pane_output_lifecycle.enable_pane_output("remote-host/agent1")
        with self.assertRaises(ValueError):
            pane_output_lifecycle.enable_pane_output("registry:agent1")

    def test_recovery_reattaches_enabled_pipe_with_fresh_instance(self):
        calls = []
        def fake_tmux(args):
            calls.append(args)
            unprefixed = _unprefixed(args)
            if unprefixed[:3] == ["display-message", "-p", "-t"]:
                fmt = unprefixed[4]
                if pane_output_lifecycle.BROCCOLI_PIPE_DESIRED_OPTION in fmt:
                    return "1"
                if pane_output_lifecycle.BROCCOLI_PIPE_MARKER_OPTION in fmt:
                    return "1|stale-pipe"
            return ""

        with mock.patch("tmux_util.run_tmux_cmd", side_effect=fake_tmux):
            result = pane_output_lifecycle.recover_enabled_pane_outputs()

        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["reattached"], 1)
        info = state.get_agent("id-1")
        self.assertTrue(info["pipe_output_enabled"])
        self.assertNotEqual(info["pipe_instance_id"], "stale-pipe")
        self.assertIsNotNone(info["pipe_token_hash"])
        pipe_calls = [_unprefixed(args) for args in calls if _unprefixed(args) and _unprefixed(args)[0] == "pipe-pane"]
        self.assertEqual(pipe_calls[0], ["pipe-pane", "-t", "%1"])
        self.assertEqual(pipe_calls[1][:4], ["pipe-pane", "-o", "-t", "%1"])

    def test_recovery_refuses_non_broccoli_pipe_without_metadata(self):
        calls = []
        def fake_tmux(args):
            calls.append(args)
            unprefixed = _unprefixed(args)
            if unprefixed[:3] == ["display-message", "-p", "-t"]:
                fmt = unprefixed[4]
                if pane_output_lifecycle.BROCCOLI_PIPE_DESIRED_OPTION in fmt:
                    return "1"
                if pane_output_lifecycle.BROCCOLI_PIPE_MARKER_OPTION in fmt:
                    return "1|"
            return ""

        with mock.patch("tmux_util.run_tmux_cmd", side_effect=fake_tmux):
            result = pane_output_lifecycle.recover_enabled_pane_outputs()

        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["reattached"], 0)
        self.assertEqual(result["errors"], 1)
        self.assertFalse(state.get_agent("id-1").get("pipe_output_enabled", False))
        self.assertNotIn(["pipe-pane", "-t", "%1"], [_unprefixed(args) for args in calls])


def json_safe(value):
    import json
    return json.dumps(value, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
