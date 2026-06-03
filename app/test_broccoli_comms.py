import argparse
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


_APP_PATH = Path(__file__).resolve().parent / "broccoli-comms.py"
_spec = importlib.util.spec_from_file_location("broccoli_comms_app", _APP_PATH)
broccoli_comms_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(broccoli_comms_app)


class TestBroccoliCommsApp(unittest.TestCase):
    def test_base_env_strips_agent_identity_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
            "BROCCOLI_COMMS_RUNTIME_DIR": os.path.join(tmp, "runtime"),
            "BROCCOLI_COMMS_CACHE_DIR": os.path.join(tmp, "cache"),
            "BROCCOLI_COMMS_CONFIG_DIR": os.path.join(tmp, "config"),
            "BROCCOLI_COMMS_DISABLE_CONFIG_REGISTRIES": "1",
            "AGENT_ID": "agent-id",
            "AGENT_NAME": "agent-name",
            "AGENT_UUID": "agent-id",
            "SUGGESTED_AGENT_NAME": "suggested",
            "TMUX": "tmux-env",
            "TMUX_PANE": "%1",
            "PATH": "/bin",
        }, clear=False):
            env = broccoli_comms_app.base_env()

        self.assertNotIn("AGENT_ID", env)
        self.assertNotIn("AGENT_NAME", env)
        self.assertNotIn("AGENT_UUID", env)
        self.assertNotIn("SUGGESTED_AGENT_NAME", env)
        self.assertNotIn("TMUX", env)
        self.assertNotIn("TMUX_PANE", env)

    def test_base_env_can_preserve_agent_identity_for_passthrough(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
            "BROCCOLI_COMMS_RUNTIME_DIR": os.path.join(tmp, "runtime"),
            "BROCCOLI_COMMS_CACHE_DIR": os.path.join(tmp, "cache"),
            "BROCCOLI_COMMS_CONFIG_DIR": os.path.join(tmp, "config"),
            "BROCCOLI_COMMS_DISABLE_CONFIG_REGISTRIES": "1",
            "AGENT_ID": "agent-id",
            "AGENT_NAME": "agent-name",
            "AGENT_UUID": "agent-id",
            "SUGGESTED_AGENT_NAME": "suggested",
            "TMUX": "tmux-env",
            "TMUX_PANE": "%1",
            "PATH": "/bin",
        }, clear=False):
            env = broccoli_comms_app.base_env(preserve_agent_identity=True)

        self.assertEqual(env["AGENT_ID"], "agent-id")
        self.assertEqual(env["AGENT_NAME"], "agent-name")
        self.assertEqual(env["AGENT_UUID"], "agent-id")
        self.assertNotIn("SUGGESTED_AGENT_NAME", env)
        self.assertNotIn("TMUX", env)
        self.assertNotIn("TMUX_PANE", env)

    def test_executable_resolution_uses_environment_not_config(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": tmp,
            "BROCCOLI_COMMS_AGENT_TRACKER": "/env/agent-tracker",
            "BROCCOLI_COMMS_AGENT_TRACKER_CTL": "/env/agent-tracker-ctl.py",
            "BROCCOLI_COMMS_AGENT_WRAPPER": "/env/agent-wrapper",
            "BROCCOLI_COMMS_AGENT_REGISTRY": "/env/agent-registry",
            "BROCCOLI_COMMS_AGENT_COMMUNICATOR_TUI": "/env/agent-communicator",
        }, clear=False):
            cfg_dir = Path(tmp) / "broccoli-comms"
            cfg_dir.mkdir(parents=True)
            (cfg_dir / "config.toml").write_text("""
[executables]
agent_tracker = "/config/agent-tracker"
agent_tracker_ctl_py = "/config/agent-tracker-ctl.py"
agent_wrapper = "/config/agent-wrapper"
agent_registry = "/config/agent-registry"
agent_communicator_tui = "/config/agent-communicator"
""")
            self.assertEqual(broccoli_comms_app.tracker_script(), "/env/agent-tracker")
            self.assertEqual(broccoli_comms_app.tracker_ctl_script(), "/env/agent-tracker-ctl.py")
            self.assertEqual(broccoli_comms_app.wrapper_path(), "/env/agent-wrapper")
            self.assertEqual(broccoli_comms_app.registry_script(), "/env/agent-registry")
            self.assertEqual(broccoli_comms_app.tui_path(), "/env/agent-communicator")

    def test_agent_tracker_passthrough_preserves_agent_identity(self):
        env = {"AGENT_ID": "agent-id"}
        with mock.patch.object(broccoli_comms_app, "ensure_tracker"), \
             mock.patch.object(broccoli_comms_app, "ensure_tmux"), \
             mock.patch.object(broccoli_comms_app, "tracker_ctl_script", return_value="/ctl.py"), \
             mock.patch.object(broccoli_comms_app, "base_env", return_value=env) as base_env, \
             mock.patch.object(broccoli_comms_app.os, "execvpe") as execvpe:
            broccoli_comms_app.agent_tracker(argparse.Namespace(tracker_args=["send-message", "target", "hello"]))

        base_env.assert_called_once_with(preserve_agent_identity=True)
        execvpe.assert_called_once_with(
            broccoli_comms_app.sys.executable,
            [broccoli_comms_app.sys.executable, "/ctl.py", "send-message", "target", "hello"],
            env,
        )


if __name__ == "__main__":
    unittest.main()
