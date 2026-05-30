import argparse
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("demo-agent")
loader = importlib.machinery.SourceFileLoader("demo_agent_script", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
demo_agent = importlib.util.module_from_spec(spec)
loader.exec_module(demo_agent)


def args(**overrides):
    base = {
        "role": "generic",
        "name": "demo-pi",
        "peer_coder": "demo-coder",
        "peer_reviewer": "demo-reviewer",
        "poll_interval": 0.2,
        "state_dir": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class CapturingAgent(demo_agent.DemoAgent):
    def __init__(self, parsed_args):
        self.sent = []
        super().__init__(parsed_args)

    def send(self, target, message):
        if self.outbound_count >= demo_agent.MAX_OUTBOUND_PER_INBOX_MESSAGE:
            return False
        self.sent.append((target, message))
        self.outbound_count += 1
        return True

    def send_sequence(self, target, messages, delay=0.0):
        for message in messages:
            self.send(target, message)


class DemoAgentTests(unittest.TestCase):
    def test_rejects_remote_looking_names(self):
        self.assertTrue(demo_agent.is_safe_local_name("demo-coder_1.ok"))
        self.assertFalse(demo_agent.is_safe_local_name("host/demo-coder"))
        self.assertFalse(demo_agent.is_safe_local_name("http://demo"))
        self.assertFalse(demo_agent.is_safe_local_name("demo coder"))

    def test_state_dir_must_be_under_broccoli_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            old_cache = os.environ.get("BROCCOLI_COMMS_CACHE_DIR")
            os.environ["BROCCOLI_COMMS_CACHE_DIR"] = root
            try:
                with self.assertRaises(SystemExit):
                    demo_agent.choose_state_dir(outside, "demo")
            finally:
                if old_cache is None:
                    os.environ.pop("BROCCOLI_COMMS_CACHE_DIR", None)
                else:
                    os.environ["BROCCOLI_COMMS_CACHE_DIR"] = old_cache

    def test_ui_markdown_reply_instruction_is_stripped_from_commands(self):
        self.assertEqual(demo_agent.normalize_message("hello\n\n(PS: Reply in markdown format.)"), "hello")
        self.assertEqual(demo_agent.normalize_message("HELP (ps: reply in markdown format.)"), "help")

    def test_send_uses_tracker_rpc_send_message(self):
        with tempfile.TemporaryDirectory() as root:
            old_env = {key: os.environ.get(key) for key in ("BROCCOLI_COMMS_CACHE_DIR", "AGENT_TRACKER_SOCKET", "AGENT_ID", "AGENT_NAME")}
            os.environ["BROCCOLI_COMMS_CACHE_DIR"] = root
            os.environ["AGENT_TRACKER_SOCKET"] = str(Path(root) / "tracker.sock")
            os.environ["AGENT_ID"] = "demo-id"
            os.environ["AGENT_NAME"] = "demo-pi"
            try:
                agent = demo_agent.DemoAgent(args(role="generic", name="demo-pi"))
                calls = []
                agent.rpc = lambda method, params: calls.append((method, params)) or True
                self.assertTrue(agent.send("agent-communicator", "hello"))
                self.assertEqual(calls, [("send_message", {"sender_name": "demo-pi", "agent_name": "agent-communicator", "message": "hello", "sender_id": "demo-id"})])
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_configure_tracker_identity_disables_tmux_notifications(self):
        with tempfile.TemporaryDirectory() as root:
            old_env = {key: os.environ.get(key) for key in ("BROCCOLI_COMMS_CACHE_DIR", "AGENT_TRACKER_SOCKET", "AGENT_ID", "AGENT_NAME")}
            os.environ["BROCCOLI_COMMS_CACHE_DIR"] = root
            os.environ["AGENT_TRACKER_SOCKET"] = str(Path(root) / "tracker.sock")
            os.environ["AGENT_ID"] = "demo-id"
            try:
                agent = demo_agent.DemoAgent(args(role="generic", name="demo-pi"))
                calls = []
                agent.rpc = lambda method, params: calls.append((method, params)) or True
                agent.configure_tracker_identity()
                agent.configure_tracker_identity()
                self.assertEqual(calls, [("update_agent", {"no_notify_with_send_keys": True, "agent_id": "demo-id"})])
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_coder_implement_feature_is_bounded_and_targets_reviewer(self):
        with tempfile.TemporaryDirectory() as root:
            old_env = {key: os.environ.get(key) for key in ("BROCCOLI_COMMS_CACHE_DIR", "AGENT_TRACKER_SOCKET", "AGENT_ID", "AGENT_NAME")}
            os.environ["BROCCOLI_COMMS_CACHE_DIR"] = root
            os.environ["AGENT_TRACKER_SOCKET"] = str(Path(root) / "tracker.sock")
            os.environ["AGENT_NAME"] = "demo-coder"
            os.environ.pop("AGENT_ID", None)
            try:
                agent = CapturingAgent(args(role="coder", name="demo-coder"))
                agent.implement_feature("agent-communicator")
                self.assertEqual(len(agent.sent), demo_agent.MAX_OUTBOUND_PER_INBOX_MESSAGE)
                self.assertEqual(agent.sent[-1][0], "demo-reviewer")
                task = agent.state.task("task-001")
                self.assertEqual(task["origin_sender"], "agent-communicator")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
