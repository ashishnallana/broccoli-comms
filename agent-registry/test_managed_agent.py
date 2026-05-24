import importlib.util
import os
import unittest
from unittest import mock

_MOD_PATH = os.path.join(os.path.dirname(__file__), "managed_agent.py")
_spec = importlib.util.spec_from_file_location("managed_agent", _MOD_PATH)
managed_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(managed_agent)


class TestManagedAgent(unittest.TestCase):
    def test_default_tmux_socket_uses_runtime_dir(self):
        with mock.patch.dict(managed_agent.os.environ, {"XDG_RUNTIME_DIR": "/run/user/1234"}, clear=False), \
             mock.patch.object(managed_agent.os, "getuid", return_value=1234):
            self.assertEqual(managed_agent.default_tmux_socket(), "/run/user/1234/tmux-1234/default")

    def test_build_launch_command_includes_wrapper_and_env(self):
        cmd = managed_agent.build_launch_command("nixos-expert", "pi --help", "agent-wrapper", "/tmp/tracker.sock")
        self.assertIn("SUGGESTED_AGENT_NAME=nixos-expert", cmd)
        self.assertIn("AGENT_TRACKER_SOCKET=/tmp/tracker.sock", cmd)
        self.assertIn("agent-wrapper", cmd)
        self.assertIn("pi --help", cmd)

    @mock.patch.object(managed_agent, "ensure_requirements")
    @mock.patch.object(managed_agent, "session_exists", return_value=True)
    @mock.patch.object(managed_agent, "list_panes", return_value=[{"pane_id": "%1", "pane_dead": False, "pane_current_command": "pi", "agent_name": "nixos-expert"}])
    def test_reconcile_agent_noop_when_named_agent_exists(self, _panes, _exists, _reqs):
        self.assertEqual(
            managed_agent.reconcile_agent("nixos-expert", "sess", "/tmp", "pi"),
            "already-running",
        )

    @mock.patch.object(managed_agent, "ensure_requirements")
    @mock.patch.object(managed_agent, "tmux_cmd")
    @mock.patch.object(managed_agent, "session_exists", return_value=False)
    def test_reconcile_agent_starts_new_session_when_missing(self, _exists, tmux_cmd, _reqs):
        tmux_cmd.return_value.stdout = "%9\n"
        self.assertEqual(
            managed_agent.reconcile_agent("nixos-expert", "sess", "/tmp", "pi"),
            "session-created-started",
        )
        args = tmux_cmd.call_args_list[0][0][0]
        self.assertEqual(args[:8], ["new-session", "-d", "-P", "-F", "#{pane_id}", "-s", "sess", "-n"])

    @mock.patch.object(managed_agent, "ensure_requirements")
    @mock.patch.object(managed_agent, "tmux_cmd")
    @mock.patch.object(managed_agent, "session_exists", return_value=True)
    @mock.patch.object(managed_agent, "list_panes", return_value=[{"pane_id": "%1", "pane_dead": True, "pane_current_command": "bash", "agent_name": "nixos-expert"}])
    def test_reconcile_agent_respawns_dead_named_pane(self, _panes, _exists, tmux_cmd, _reqs):
        self.assertEqual(
            managed_agent.reconcile_agent("nixos-expert", "sess", "/tmp", "pi"),
            "respawned",
        )
        args = tmux_cmd.call_args_list[0][0][0]
        self.assertEqual(args[:4], ["respawn-pane", "-k", "-t", "%1"])

    @mock.patch.object(managed_agent.time, "sleep")
    @mock.patch.object(managed_agent, "ensure_requirements")
    @mock.patch.object(managed_agent, "tmux_cmd")
    @mock.patch.object(managed_agent, "session_exists", return_value=True)
    @mock.patch.object(managed_agent, "list_panes", side_effect=[
        [{"pane_id": "%1", "pane_dead": False, "pane_current_command": "pi", "agent_name": "nixos-expert"}],
        [{"pane_id": "%1", "pane_dead": False, "pane_current_command": "pi", "agent_name": "nixos-expert"}],
    ])
    def test_restart_agent_warns_then_respawns(self, _panes, _exists, tmux_cmd, _reqs, _sleep):
        self.assertEqual(
            managed_agent.restart_agent("nixos-expert", "sess", "/tmp", "pi", warning_lead_time_seconds=300),
            "restarted",
        )
        first = tmux_cmd.call_args_list[0][0][0]
        second = tmux_cmd.call_args_list[1][0][0]
        self.assertEqual(first[:3], ["send-keys", "-t", "%1"])
        self.assertEqual(second[:4], ["respawn-pane", "-k", "-t", "%1"])


if __name__ == "__main__":
    unittest.main()
