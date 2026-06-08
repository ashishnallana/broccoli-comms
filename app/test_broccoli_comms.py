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
    def test_trusted_memory_actor_rejects_spoofed_agent_name(self):
        with mock.patch.dict(os.environ, {"AGENT_NAME": "user"}, clear=False), mock.patch.object(broccoli_comms_app, "get_toml_config", return_value=[]), mock.patch.object(broccoli_comms_app, "tracker_rpc", return_value={"name": "evil"}):
            with self.assertRaises(SystemExit):
                broccoli_comms_app.trusted_memory_actor_from_runtime()

    def test_trusted_memory_actor_rejects_agent_unsetting_name_but_verified_by_pid(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(broccoli_comms_app, "get_toml_config", return_value=[]), mock.patch.object(broccoli_comms_app, "tracker_rpc", return_value={"name": "evil"}):
            with self.assertRaises(SystemExit):
                broccoli_comms_app.trusted_memory_actor_from_runtime()

    def test_trusted_memory_actor_rejects_only_agent_id_when_unverified(self):
        with mock.patch.dict(os.environ, {"AGENT_ID": "evil-id"}, clear=True), mock.patch.object(broccoli_comms_app, "get_toml_config", return_value=[]), mock.patch.object(broccoli_comms_app, "tracker_rpc", side_effect=RuntimeError("not identified")):
            with self.assertRaises(SystemExit):
                broccoli_comms_app.trusted_memory_actor_from_runtime()

    def test_trusted_memory_actor_allows_configured_verified_agent(self):
        with mock.patch.dict(os.environ, {"AGENT_NAME": "spoofed"}, clear=False), mock.patch.object(broccoli_comms_app, "get_toml_config", return_value=["coordinator"]), mock.patch.object(broccoli_comms_app, "tracker_rpc", return_value={"name": "coordinator"}):
            self.assertEqual(broccoli_comms_app.trusted_memory_actor_from_runtime(), "coordinator")

    def test_trusted_memory_actor_allows_local_human_without_agent_identity(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(broccoli_comms_app, "tracker_rpc", side_effect=RuntimeError("not identified")):
            self.assertEqual(broccoli_comms_app.trusted_memory_actor_from_runtime(), "user")

    def test_trusted_memory_actor_rejects_unreachable_tracker_without_agent_identity(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(broccoli_comms_app, "tracker_rpc", return_value=None):
            with self.assertRaises(SystemExit):
                broccoli_comms_app.trusted_memory_actor_from_runtime()

    def test_memory_propose_rejects_unreachable_tracker_without_agent_identity(self):
        args = argparse.Namespace(type="fact", scope="global", subject_agent=None, title="T", body="B", source_task="task-1", trusted_manual=False, tag=None, idempotency_key=None, agent=None, instance=None, metadata_json=None, json=True)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(broccoli_comms_app, "tracker_rpc", return_value=None):
            with self.assertRaises(SystemExit):
                broccoli_comms_app.memory_propose(args)

    def test_memory_propose_uses_verified_identity_for_immutable_check(self):
        args = argparse.Namespace(type="fact", scope="global", subject_agent=None, title="T", body="B", source_task="task-1", trusted_manual=False, tag=None, idempotency_key=None, agent="user", instance=None, metadata_json=None, json=True)
        fake_kernel = mock.Mock()
        fake_kernel.memory_propose.side_effect = ValueError("immutable/non-learning instance cannot propose memory")
        with mock.patch.object(broccoli_comms_app, "tracker_rpc", return_value={"name": "immutable-agent", "agent_id": "immutable-id"}), mock.patch.object(broccoli_comms_app, "get_toml_config", return_value=["immutable-id"]), mock.patch.object(broccoli_comms_app, "learning_kernel", return_value=fake_kernel):
            with self.assertRaises(SystemExit):
                broccoli_comms_app.memory_propose(args)
        self.assertTrue(fake_kernel.memory_propose.call_args.kwargs["non_learning"])
        self.assertEqual(fake_kernel.memory_propose.call_args.kwargs["proposed_by"], "immutable-agent")

    def test_trusted_manual_memory_provenance_uses_verified_actor(self):
        args = argparse.Namespace(type="habit", scope="global", subject_agent=None, title="T", body="B", source_task=None, trusted_manual=True, tag=None, idempotency_key=None, agent="spoofed", instance=None, metadata_json=None, json=True)
        captured = {}
        fake_kernel = mock.Mock()
        fake_kernel.memory_propose.side_effect = lambda **kw: captured.update(kw) or {"memory": {"memory_id": "mem-1"}}
        def fake_config(_section, key, default=None):
            return ["coordinator"] if key == "trusted_memory_actors" else []
        with mock.patch.object(broccoli_comms_app, "tracker_rpc", return_value={"name": "coordinator", "agent_id": "coord-id"}), mock.patch.object(broccoli_comms_app, "get_toml_config", side_effect=fake_config), mock.patch.object(broccoli_comms_app, "learning_kernel", return_value=fake_kernel):
            broccoli_comms_app.memory_propose(args)
        self.assertEqual(captured["proposed_by"], "coordinator")
        self.assertEqual(captured["created_by"] if "created_by" in captured else captured["trusted_actor"], "coordinator")
        self.assertEqual(captured["proposed_by_instance"], "coord-id")

    def test_memory_propose_rejects_agent_id_only_unverified_identity(self):
        args = argparse.Namespace(type="fact", scope="global", subject_agent=None, title="T", body="B", source_task="task-1", trusted_manual=False, tag=None, idempotency_key=None, agent="user", instance=None, metadata_json=None, json=True)
        with mock.patch.dict(os.environ, {"AGENT_ID": "evil-id"}, clear=True), mock.patch.object(broccoli_comms_app, "tracker_rpc", side_effect=RuntimeError("not identified")):
            with self.assertRaises(SystemExit):
                broccoli_comms_app.memory_propose(args)

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
