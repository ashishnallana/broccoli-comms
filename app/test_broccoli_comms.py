import argparse
import importlib.util
import json
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

    def test_agent_add_persists_normalized_swarms(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp, "XDG_CACHE_HOME": tmp, "XDG_RUNTIME_DIR": tmp}, clear=False):
            broccoli_comms_app.agent_add(argparse.Namespace(
                name="planner",
                cwd=tmp,
                command="pi",
                autostart=True,
                force=False,
                swarm=["s1"],
                role=["main"],
            ))
            cfg = json.loads((Path(tmp) / "broccoli-comms" / "config.json").read_text())

        self.assertEqual(cfg["agents"]["planner"]["swarms"], [{"name": "s1", "role": "main"}])

    def test_invalid_swarm_role_is_rejected(self):
        with self.assertRaises(SystemExit):
            broccoli_comms_app.parse_swarm_args(argparse.Namespace(swarm=["s1"], role=["worker"]))

    def test_repeated_swarm_role_pairs_are_normalized(self):
        swarms = broccoli_comms_app.parse_swarm_args(argparse.Namespace(
            swarm=["backend-fix", "review"],
            role=["main", "subagent"],
        ))
        self.assertEqual(swarms, [
            {"name": "backend-fix", "role": "main"},
            {"name": "review", "role": "subagent"},
        ])

    def test_normalize_config_accepts_top_level_swarms(self):
        cfg = broccoli_comms_app.normalize_config({
            "agents": {"planner": {"cwd": "/repo", "command": "pi"}},
            "swarms": {"backend-fix": {"members": [{"agent": "planner", "role": "main"}]}},
        })
        self.assertEqual(cfg["swarms"]["backend-fix"]["members"], [{"agent": "planner", "role": "main"}])

    def test_normalize_config_rejects_invalid_top_level_swarm_role(self):
        with self.assertRaises(ValueError):
            broccoli_comms_app.normalize_config({
                "agents": {"planner": {}},
                "swarms": {"backend-fix": {"members": [{"agent": "planner", "role": "worker"}]}},
            })

    def test_managed_launch_command_includes_swarm_flags(self):
        with mock.patch.object(broccoli_comms_app, "broccoli_comms_launcher_argv", return_value=["broccoli-comms"]), \
             mock.patch.object(broccoli_comms_app, "managed_track_env_assignments", return_value=[]):
            command = broccoli_comms_app.managed_agent_launch_command(
                "planner",
                "/work tree",
                "pi --flag",
                [{"name": "backend-fix", "role": "main"}],
            )

        self.assertIn("--swarm backend-fix --role main", command)
        self.assertIn("BROCCOLI_COMMS_SOURCE_CWD='/work tree'", command)
        self.assertIn("-- pi --flag", command)

    def test_ephemeral_agent_workspace_writes_agents_md_from_config_template(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}, clear=False):
            cfg_dir = Path(tmp) / "broccoli-comms"
            cfg_dir.mkdir(parents=True)
            (cfg_dir / "config.toml").write_text('[learning]\nagent_contract_template = "hello {agent} {cwd}"\n')
            workspace = broccoli_comms_app.ephemeral_agent_workspace("planner")
        body = (Path(workspace) / "AGENTS.md").read_text()
        self.assertEqual(body, f"hello planner {workspace}")
        self.assertIn("/broccoli-agents/planner/", workspace)


if __name__ == "__main__":
    unittest.main()
