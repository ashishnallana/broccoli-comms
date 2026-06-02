import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

_CTL_PATH = os.path.join(os.path.dirname(__file__), "agent-tracker-ctl.py")
_spec = importlib.util.spec_from_file_location("agent_tracker_ctl", _CTL_PATH)
ctl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctl)


class TestSaveCommand(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patcher = mock.patch.dict(os.environ, {"HOME": self.temp_dir.name})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    @mock.patch("test_save_command.ctl.ensure_tracker_running", return_value=True)
    @mock.patch("ctl_commands.save.call_rpc", return_value={})
    @mock.patch("ctl_commands.save.query_tmux_option", return_value="my-agent")
    @mock.patch("ctl_commands.save.query_tmux_path", return_value="/tmp/active-project")
    @mock.patch("subprocess.run")
    def test_save_autodetects_from_tmux_environment(self, mock_run, mock_tmux_path, mock_tmux_option, mock_rpc, mock_ensure):
        with mock.patch.dict(os.environ, {"TMUX_PANE": "%99"}):
            with mock.patch.object(ctl.sys, "argv", ["agent-tracker-ctl", "save"]):
                ctl.main()

        # Verify config directory and config.json were successfully created
        config_path = os.path.join(self.temp_dir.name, ".config", "agent-tracker", "agents", "my-agent", "config.json")
        self.assertTrue(os.path.isfile(config_path))

        with open(config_path, "r") as f:
            cfg = json.load(f)

        self.assertEqual(cfg["directory"], "/tmp/active-project")
        self.assertEqual(cfg["agent-command"], "my-agent")
        self.assertEqual(cfg["agent-args"], [])

    @mock.patch("test_save_command.ctl.ensure_tracker_running", return_value=True)
    @mock.patch("ctl_commands.save.call_rpc")
    def test_save_running_agent_queries_local_daemon_by_name(self, mock_rpc, mock_ensure):
        mock_rpc.return_value = {
            "zv2-billing-fix-agent-1": {
                "cwd": "/google/src/cloud/tanmayvijay/zv2-billing-fix/google3",
                "agent_cmd": "jetski -p hello",
            }
        }

        # Run save matching the prefix name
        with mock.patch.object(ctl.sys, "argv", ["agent-tracker-ctl", "save", "-a", "zv2-billing-fix"]):
            ctl.main()

        config_path = os.path.join(self.temp_dir.name, ".config", "agent-tracker", "agents", "zv2-billing-fix", "config.json")
        self.assertTrue(os.path.isfile(config_path))

        with open(config_path, "r") as f:
            cfg = json.load(f)

        self.assertEqual(cfg["directory"], "/google/src/cloud/tanmayvijay/zv2-billing-fix/google3")
        self.assertEqual(cfg["agent-command"], "jetski")
        self.assertEqual(cfg["agent-args"], ["-p", "hello"])
        self.assertEqual(cfg["description"], "Auto-saved configuration for agent zv2-billing-fix in /google/src/cloud/tanmayvijay/zv2-billing-fix/google3")

    @mock.patch("test_save_command.ctl.ensure_tracker_running", return_value=True)
    @mock.patch("ctl_commands.save.call_rpc", return_value={})
    def test_save_manual_overrides_persist_correctly(self, mock_rpc, mock_ensure):
        with mock.patch.object(
            ctl.sys, "argv", [
                "agent-tracker-ctl", "save",
                "-a", "custom-agent",
                "-w", "/tmp/my-custom-project",
                "-c", "python3 my_script.py --flag",
                "-d", "Manually overridden config"
            ]
        ):
            ctl.main()

        config_path = os.path.join(self.temp_dir.name, ".config", "agent-tracker", "agents", "custom-agent", "config.json")
        self.assertTrue(os.path.isfile(config_path))

        with open(config_path, "r") as f:
            cfg = json.load(f)

        self.assertEqual(cfg["directory"], "/tmp/my-custom-project")
        self.assertEqual(cfg["agent-command"], "python3")
        self.assertEqual(cfg["agent-args"], ["my_script.py", "--flag"])
        self.assertEqual(cfg["description"], "Manually overridden config")


if __name__ == "__main__":
    unittest.main()
