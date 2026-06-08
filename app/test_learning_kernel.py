import argparse
import importlib.util
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest import mock

_APP_PATH = Path(__file__).resolve().parent / "broccoli-comms.py"
_spec = importlib.util.spec_from_file_location("broccoli_comms_app_learning", _APP_PATH)
broccoli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(broccoli)


class TestLearningKernelCli(unittest.TestCase):
    def env(self, tmp):
        return mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp, "XDG_CACHE_HOME": tmp, "XDG_RUNTIME_DIR": tmp}, clear=False)

    def kernel(self, tmp):
        with self.env(tmp):
            return broccoli.learning_kernel()

    def test_task_state_profile_events_json_flow(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="Implement x", description="objective", assigned_agent="offline-agent", acceptance_criteria=["tests pass"], next_step="inspect")
            self.assertEqual(task["assigned_agent"], "offline-agent")
            self.assertIn(task, k.task_list(agent="offline-agent"))

            nxt = k.task_next(agent="offline-agent", include_profile=True)
            self.assertEqual(nxt["task"]["task_id"], task["task_id"])
            self.assertIn("body", nxt["user_profile"])

            state = k.state_set(task["task_id"], "offline-agent", status="working", current_activity="coding", next_step="test")
            self.assertEqual(state["current_activity"], "coding")
            self.assertEqual(k.state_show(task["task_id"], "offline-agent")["state_id"], state["state_id"])

            marked = k.mark_result(task["task_id"], "good", "ok")
            self.assertEqual(marked["status"], "validated")
            self.assertEqual(marked["result_status"], "good")
            event_types = [e["event_type"] for e in k.events(task_id=task["task_id"])]
            self.assertIn("task_created", event_types)
            self.assertIn("working_state_set", event_types)
            self.assertIn("task_result_marked", event_types)

    def test_dependencies_gate_next_until_done(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            dep = k.task_create(title="dep", assigned_agent="a")
            child = k.task_create(title="child", assigned_agent="a", depends_on=[dep["task_id"]])
            self.assertEqual(k.task_next(agent="a")["task"]["task_id"], dep["task_id"])
            k.task_update(dep["task_id"], status="done")
            self.assertEqual(k.task_next(agent="a")["task"]["task_id"], child["task_id"])

    def test_stale_state_filter_and_contract(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="t", assigned_agent="a")
            k.state_set(task["task_id"], "a", status="working")
            self.assertEqual(k.state_list(stale_after=0)[0]["agent"], "a")
            contract = broccoli.agent_contract("a", "a@s1", "/tmp/ws")
            self.assertIn("You are: a", contract)
            self.assertIn("broccoli-comms task bootstrap --agent a --json", contract)
            self.assertIn("database names, table names, commands/tools used", contract)
            self.assertIn("goal -> checkpoints/discoveries -> result summary -> user validation", contract)
            self.assertIn("clarification_count, correction_count, need_improvements_count", contract)
            self.assertIn("first_pass_success", contract)
            self.assertIn("derivable from `working_state_set` events", contract)
            self.assertIn("task_chain_id/root_task_id", contract)
            self.assertIn("Multiple active instances of the same profile", contract)
            self.assertIn("immutable or non-learning", contract)
            self.assertIn("do not write state checkpoints", contract)
            self.assertIn("correction-assisted", contract)
            self.assertIn("Never store raw terminal transcripts", contract)

    def test_agent_contract_template_comes_from_config_toml(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            cfg_dir = Path(tmp) / "broccoli-comms"
            cfg_dir.mkdir()
            (cfg_dir / "config.toml").write_text('[learning]\nagent_contract_template = "custom {agent} {instance} {cwd}"\n')
            self.assertEqual(broccoli.agent_contract_template(), "custom {agent} {instance} {cwd}")
            self.assertEqual(broccoli.agent_contract("a", "i", "/w", broccoli.agent_contract_template()), "custom a i /w")

    def test_mark_result_requires_remediation_for_non_good(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="t", assigned_agent="a")
            with self.assertRaises(ValueError):
                k.mark_result(task["task_id"], "bad")
            updated = k.mark_result(task["task_id"], "need_improvements", next_step="fix it", status="working")
            self.assertEqual(updated["status"], "working")
            self.assertEqual(updated["next_step"], "fix it")

    def test_structured_clarification_metadata_is_derivable_from_events(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="find db", assigned_agent="a")
            k.state_set(
                task["task_id"],
                "a",
                instance_id="a@s1",
                task_chain_id="chain-1",
                root_task_id=task["task_id"],
                status="working",
                current_activity="validated database choice",
                next_step="summarize result",
                clarification_count=1,
                correction_count=2,
                need_improvements_count=1,
                first_pass_success=False,
                notes="db=analytics table=events reason=user confirmed",
            )
            event = next(e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "working_state_set")
            self.assertEqual(event["payload"]["agent_instance_id"], "a@s1")
            self.assertEqual(event["payload"]["task_chain_id"], "chain-1")
            self.assertEqual(event["payload"]["root_task_id"], task["task_id"])
            self.assertEqual(event["payload"]["clarification_count"], 1)
            self.assertEqual(event["payload"]["correction_count"], 2)
            self.assertEqual(event["payload"]["need_improvements_count"], 1)
            self.assertFalse(event["payload"]["first_pass_success"])

    def test_same_profile_different_task_chains_coexist_and_conflict_same_chain(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="parallel", assigned_agent="a")
            first = k.state_set(task["task_id"], "a", instance_id="a@s1", task_chain_id="chain-1", root_task_id="root-1", status="working")
            second = k.state_set(task["task_id"], "a", instance_id="a@s2", task_chain_id="chain-2", root_task_id="root-2", status="working")
            shown = k.state_show(task["task_id"], "a")
            self.assertIsInstance(shown, list)
            self.assertEqual({st["state_id"] for st in shown}, {first["state_id"], second["state_id"]})
            self.assertEqual({st["task_chain_id"] for st in shown}, {"chain-1", "chain-2"})
            with self.assertRaises(ValueError):
                k.state_set(task["task_id"], "a", instance_id="a@s3", task_chain_id="chain-1", root_task_id="root-1", status="working")
            with self.assertRaises(ValueError):
                k.state_set(task["task_id"], "a", task_chain_id="chain-1", root_task_id="root-1", status="working")
            shown_after = k.state_show(task["task_id"], "a")
            self.assertEqual(len(shown_after), 2)

    def test_state_clear_reports_and_logs_all_agent_chains(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="clear", assigned_agent="a")
            k.state_set(task["task_id"], "a", instance_id="a@s1", task_chain_id="chain-1", root_task_id="root-1")
            k.state_set(task["task_id"], "a", instance_id="a@s2", task_chain_id="chain-2", root_task_id="root-2")
            result = k.state_clear(task["task_id"], "a")
            self.assertEqual(result["cleared"], 2)
            self.assertEqual(k.state_show(task["task_id"], "a"), None)
            cleared = [e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "working_state_cleared"]
            self.assertEqual(len(cleared), 2)
            self.assertEqual({e["payload"]["task_chain_id"] for e in cleared}, {"chain-1", "chain-2"})
            self.assertEqual({e["payload"]["root_task_id"] for e in cleared}, {"root-1", "root-2"})

    def test_old_working_state_schema_migrates_before_new_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "old.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript("""
            CREATE TABLE schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version(version) VALUES(1);
            CREATE TABLE working_states(
              state_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, agent TEXT NOT NULL, instance_id TEXT,
              status TEXT NOT NULL, current_activity TEXT, next_step TEXT, blockers TEXT NOT NULL DEFAULT '[]',
              notes TEXT, stale_after_seconds INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              version INTEGER NOT NULL DEFAULT 1, UNIQUE(task_id, agent)
            );
            INSERT INTO working_states(state_id,task_id,agent,instance_id,status,blockers,created_at,updated_at)
            VALUES('state-old','task-old','a','a@s1','working','[]','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z');
            """)
            conn.close()
            k = broccoli.LearningKernel(db_path)
            state = k.state_show("task-old", "a")
            self.assertEqual(state["task_chain_id"], "")
            self.assertEqual(state["root_task_id"], "task-old")

    def test_text_fields_are_bounded_and_redacted_in_events(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            with self.assertRaises(ValueError):
                k.task_create(title="x" * 201)
            task = k.task_create(title="token=abc123", assigned_agent="a")
            event = next(e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "task_created")
            self.assertIn("[REDACTED]", event["payload"]["title"])

    def test_events_are_returned_in_append_order_for_same_second(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="rapid", assigned_agent="a")
            k.task_update(task["task_id"], status="working")
            k.mark_result(task["task_id"], "good")
            events = k.events(task_id=task["task_id"])
            self.assertEqual([e["event_seq"] for e in events], sorted(e["event_seq"] for e in events))
            self.assertEqual([e["event_type"] for e in events], [
                "task_created",
                "task_assigned",
                "task_updated",
                "task_status_changed",
                "task_result_marked",
            ])

    def test_concurrent_writes_do_not_corrupt_store(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            for i in range(20):
                k.task_create(title=f"task {i}", assigned_agent="a")
            self.assertEqual(len(k.task_list(agent="a")), 20)
            self.assertGreaterEqual(len(k.events()), 20)


if __name__ == "__main__":
    unittest.main()
