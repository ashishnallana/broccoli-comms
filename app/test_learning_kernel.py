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

    def test_legacy_assigned_agent_appears_as_assignee_participant(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="legacy", assigned_agent="coder")
            participants = k.task_participant_list(task["task_id"])
            self.assertEqual([(p["agent"], p["role"]) for p in participants], [("coder", "assignee")])
            shown = k.task_show(task["task_id"], include_participants=True)
            self.assertEqual(shown["participants"][0]["agent"], "coder")
            self.assertEqual(k.task_next(agent="coder")["task"]["task_id"], task["task_id"])

    def test_task_participant_crud_is_audited(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="review", assigned_agent="coder")
            participant = k.task_participant_add(task["task_id"], "reviewer", "reviewer", actor="tester")
            self.assertEqual(participant["status"], "active")
            updated = k.task_participant_update(participant["participant_id"], status="inactive", actor="tester")
            self.assertEqual(updated["status"], "inactive")
            removed = k.task_participant_remove(participant["participant_id"], actor="tester")
            self.assertEqual(removed["agent"], "reviewer")
            self.assertNotIn("reviewer", [p["agent"] for p in k.task_participant_list(task["task_id"])])
            event_types = [e["event_type"] for e in k.events(task_id=task["task_id"])]
            self.assertIn("task_participant_added", event_types)
            self.assertIn("task_participant_updated", event_types)
            self.assertIn("task_participant_removed", event_types)

    def test_multiple_participants_roles_on_one_task_chain(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="chain", assigned_agent="coder")
            chain = "chain-1"
            k.task_participant_add(task["task_id"], "reviewer", "reviewer", task_chain_id=chain)
            k.task_participant_add(task["task_id"], "reviewer", "verifier", task_chain_id=chain)
            k.task_participant_add(task["task_id"], "coord", "coordinator", task_chain_id=chain)
            participants = k.task_participant_list(task["task_id"])
            pairs = {(p["agent"], p["role"], p["task_chain_id"]) for p in participants}
            self.assertIn(("coder", "assignee", ""), pairs)
            self.assertIn(("reviewer", "reviewer", chain), pairs)
            self.assertIn(("reviewer", "verifier", chain), pairs)
            self.assertIn(("coord", "coordinator", chain), pairs)

    def test_task_create_accepts_default_participants(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="defaults", assigned_agent="coder", participants=[{"agent": "reviewer", "role": "reviewer"}, {"agent": "verifier", "role": "verifier"}])
            participants = {(p["agent"], p["role"]) for p in k.task_participant_list(task["task_id"])}
            self.assertIn(("coder", "assignee"), participants)
            self.assertIn(("reviewer", "reviewer"), participants)
            self.assertIn(("verifier", "verifier"), participants)
            event_types = [e["event_type"] for e in k.events(task_id=task["task_id"])]
            self.assertGreaterEqual(event_types.count("task_participant_added"), 2)

    def test_chain_default_participants_are_inherited_and_explicit_roles_override(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            root = k.task_create(title="root", assigned_agent="coder")
            chain = root["task_id"]
            default = k.task_chain_default_participant_set(chain, "reviewer", "reviewer", root_task_id=root["task_id"], actor="tester")
            self.assertEqual(default["status"], "active")
            child = k.task_create(title="child", assigned_agent="coder", task_chain_id=chain, root_task_id=root["task_id"])
            participants = {(p["agent"], p["role"], p["task_chain_id"]) for p in k.task_participant_list(child["task_id"])}
            self.assertIn(("reviewer", "reviewer", chain), participants)
            override = k.task_create(title="override", assigned_agent="coder", task_chain_id=chain, root_task_id=root["task_id"], participants=[{"agent": "other-reviewer", "role": "reviewer"}])
            override_pairs = {(p["agent"], p["role"]) for p in k.task_participant_list(override["task_id"])}
            self.assertIn(("other-reviewer", "reviewer"), override_pairs)
            self.assertNotIn(("reviewer", "reviewer"), override_pairs)
            event_types = [e["event_type"] for e in k.events(task_id=root["task_id"])]
            self.assertIn("task_chain_default_participant_added", event_types)

    def test_default_participant_cli_parser_supports_role_flags(self):
        args = argparse.Namespace(reviewer=["reviewer"], verifier=["verifier"], coordinator=["coord"], participant=["observer:watcher"])
        self.assertEqual(
            broccoli._default_task_participants(args),
            [
                {"agent": "reviewer", "role": "reviewer"},
                {"agent": "verifier", "role": "verifier"},
                {"agent": "coord", "role": "coordinator"},
                {"agent": "watcher", "role": "observer"},
            ],
        )

    def test_task_status_notification_routes_done_review_to_reviewer_roles(self):
        task = {"task_id": "task-1", "title": "Notify", "status": "review", "assigned_agent": "coder", "participants": [{"agent": "coder", "role": "assignee", "status": "active"}, {"agent": "reviewer", "role": "reviewer", "status": "active"}, {"agent": "verifier", "role": "verifier", "status": "active"}, {"agent": "old-reviewer", "role": "reviewer", "status": "inactive"}]}
        calls = []
        with mock.patch.object(broccoli, "tracker_rpc", side_effect=lambda method, payload, **kw: calls.append((method, payload)) or {"ok": True}):
            notice = broccoli.notify_task_update(task, "coder", {"status": "review"})
        self.assertTrue(notice["sent"])
        self.assertEqual([payload["agent_name"] for _method, payload in calls], [broccoli.UI_AGENT_NAME, "reviewer", "verifier"])
        for _method, payload in calls:
            self.assertNotIn("\n", payload["message"])
            self.assertIn("Task task-1 needs your attention", payload["message"])
            self.assertIn("title=Notify", payload["message"])
            self.assertIn("status=review", payload["message"])
        def flaky_tracker(_method, payload, **_kw):
            if payload["agent_name"] == "reviewer":
                raise RuntimeError("offline")
            return {"ok": True}
        with mock.patch.object(broccoli, "tracker_rpc", side_effect=flaky_tracker):
            notice = broccoli.notify_task_update(task, "coder", {"status": "review"})
        self.assertTrue(notice["sent"])
        self.assertFalse(notice["participant_notifications"][0]["sent"])
        self.assertTrue(notice["participant_notifications"][1]["sent"])

    def test_task_result_notifications_route_bad_to_assignee_and_good_to_ready_dependents(self):
        task = {"task_id": "task-1", "title": "Notify", "status": "working", "assigned_agent": "coder", "participants": [{"agent": "coder", "role": "assignee", "status": "active"}]}
        self.assertEqual(broccoli._task_update_notification_recipients(task, "reviewer", {"result_status": "need_improvements"}), ["coder"])
        task["ready_dependents"] = [{"task_id": "task-2", "assigned_agent": "next", "participants": [{"agent": "coord", "role": "coordinator", "status": "active"}]}]
        self.assertEqual(broccoli._task_update_notification_recipients(task, "reviewer", {"result_status": "good", "status": "validated"}), ["next", "coord"])

    def test_ready_dependents_excludes_already_active_or_done_dependents(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            root = k.task_create(title="root", assigned_agent="coder")
            ready = k.task_create(title="ready", assigned_agent="next", depends_on=[root["task_id"]], status="ready")
            for status in ("working", "review", "done", "validated"):
                k.task_create(title=status, assigned_agent="skip", depends_on=[root["task_id"]], status=status)
            k.task_update(root["task_id"], status="done")
            self.assertEqual([t["task_id"] for t in k.task_ready_dependents(root["task_id"])], [ready["task_id"]])

    def test_task_update_validated_notifies_ready_dependent_assignee_and_coordinator(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            root = k.task_create(title="root", assigned_agent="coder")
            child = k.task_create(title="child", assigned_agent="next", depends_on=[root["task_id"]], status="ready")
            k.task_participant_add(child["task_id"], "coord", "coordinator")
            args = argparse.Namespace(task_id=root["task_id"], status="validated", next_step=None, blocked_reason=None, result_summary=None, assign_agent=None, json=True)
            calls = []
            with mock.patch.object(broccoli, "learning_kernel", return_value=k), mock.patch.object(broccoli, "tracker_rpc", side_effect=lambda method, payload, **kw: calls.append((method, payload)) or {"ok": True}):
                broccoli.task_update(args)
            self.assertEqual([payload["agent_name"] for _method, payload in calls], [broccoli.UI_AGENT_NAME, "next", "coord"])

    def test_ui_notification_failure_still_attempts_participant_notifications(self):
        task = {"task_id": "task-1", "title": "Notify", "status": "review", "participants": [{"agent": "reviewer", "role": "reviewer", "status": "active"}]}
        calls = []
        def flaky_tracker(_method, payload, **_kw):
            calls.append(payload["agent_name"])
            if payload["agent_name"] == broccoli.UI_AGENT_NAME:
                raise RuntimeError("ui offline")
            return {"ok": True}
        with mock.patch.object(broccoli, "tracker_rpc", side_effect=flaky_tracker):
            notice = broccoli.notify_task_update(task, "coder", {"status": "review"})
        self.assertFalse(notice["sent"])
        self.assertEqual(calls, [broccoli.UI_AGENT_NAME, "reviewer"])
        self.assertTrue(notice["participant_notifications"][0]["sent"])

    def test_task_mark_result_sends_role_aware_notification(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="review", assigned_agent="coder")
            k.task_participant_add(task["task_id"], "reviewer", "reviewer")
            args = argparse.Namespace(task_id=task["task_id"], result="need_improvements", notes=None, next_step="fix", status=None, json=True)
            calls = []
            with mock.patch.object(broccoli, "learning_kernel", return_value=k), mock.patch.object(broccoli, "tracker_rpc", side_effect=lambda method, payload, **kw: calls.append((method, payload)) or {"ok": True}):
                broccoli.task_mark_result(args)
            self.assertEqual([payload["agent_name"] for _method, payload in calls], [broccoli.UI_AGENT_NAME, "coder"])

    def test_assigned_agent_update_upserts_assignee_participant(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="reassign", assigned_agent="old")
            updated = k.task_update(task["task_id"], assigned_agent="new")
            self.assertEqual(updated["assigned_agent"], "new")
            participants = k.task_participant_list(task["task_id"])
            self.assertTrue(any(p["agent"] == "new" and p["role"] == "assignee" for p in participants))
            self.assertEqual(k.task_next(agent="new")["task"]["task_id"], task["task_id"])

    def test_role_aware_task_list_and_next_preserve_legacy_default(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            assignee_task = k.task_create(title="assignee", assigned_agent="coder")
            review_task = k.task_create(title="review", assigned_agent="other", status="review")
            k.task_participant_add(review_task["task_id"], "coder", "reviewer")

            self.assertEqual([t["task_id"] for t in k.task_list(agent="coder")], [assignee_task["task_id"]])
            reviewer_tasks = k.task_list(agent="coder", statuses=["review"], participant_roles=["reviewer"])
            self.assertEqual([t["task_id"] for t in reviewer_tasks], [review_task["task_id"]])
            self.assertEqual(k.task_next(agent="coder")["task"]["task_id"], assignee_task["task_id"])
            self.assertEqual(k.task_next(agent="coder", participant_roles=["reviewer"])["task"]["task_id"], review_task["task_id"])

    def test_reviewer_task_next_uses_review_handoff_statuses_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            ready_review = k.task_create(title="ready but not review handoff", assigned_agent="other", status="ready")
            review_task = k.task_create(title="review handoff", assigned_agent="other", status="review")
            for task in (ready_review, review_task):
                k.task_participant_add(task["task_id"], "reviewer", "reviewer")

            self.assertEqual(k.task_next(agent="reviewer", participant_roles=["reviewer"])["task"]["task_id"], review_task["task_id"])
            self.assertNotEqual(k.task_next(agent="reviewer", participant_roles=["reviewer"])["task"]["task_id"], ready_review["task_id"])

    def test_reviewer_task_next_includes_done_handoff_status(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            done_task = k.task_create(title="done handoff", assigned_agent="other", status="done")
            k.task_participant_add(done_task["task_id"], "reviewer", "reviewer")
            self.assertEqual(k.task_next(agent="reviewer", participant_roles=["reviewer"])["task"]["task_id"], done_task["task_id"])

    def test_default_assignee_next_remains_ready_only_even_with_review_tasks(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            review_task = k.task_create(title="review assigned", assigned_agent="coder", status="review")
            ready_task = k.task_create(title="ready assigned", assigned_agent="coder", status="ready")
            self.assertEqual(k.task_next(agent="coder")["task"]["task_id"], ready_task["task_id"])
            self.assertNotEqual(k.task_next(agent="coder")["task"]["task_id"], review_task["task_id"])

    def test_assignee_participant_role_includes_legacy_assigned_agent(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="legacy queue", assigned_agent="coder")
            self.assertEqual(k.task_list(agent="coder", participant_roles=["assignee"])[0]["task_id"], task["task_id"])

    def test_stale_state_filter_and_contract(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="t", assigned_agent="a")
            k.state_set(task["task_id"], "a", status="working")
            self.assertEqual(k.state_list(stale_after=0)[0]["agent"], "a")
            contract = broccoli.agent_contract("a", "a@s1", "/tmp/ws")
            self.assertIn("Critical persona: plan-first for non-specific work", contract)
            self.assertIn("Historical evidence must come from memory only", contract)
            self.assertIn("For file/project queries not related to agent memory", contract)
            self.assertIn("Treat the ephemeral cwd as the source directory", contract)
            self.assertIn("Ephemeral cwd: /tmp/ws", contract)
            self.assertIn("Launch/source cwd: /tmp/ws", contract)
            self.assertIn("You are: a", contract)
            self.assertIn("broccoli-comms task bootstrap --agent a --json", contract)
            self.assertIn("check whether any pending/ready task is assigned", contract)
            self.assertIn("then start working on that task unless it is blocked or requires clarification", contract)
            self.assertIn("database names, table names, commands/tools used", contract)
            self.assertIn("goal -> checkpoints/discoveries -> result summary -> user validation", contract)
            self.assertIn("task submit-completion <task_id>", contract)
            self.assertIn("task summarize-chain <task_chain_id>", contract)
            self.assertIn("Anything that requires investigation must be created and tracked as a task first", contract)
            self.assertIn("ask the user/coordinator which collaborator agents should participate", contract)
            self.assertIn("task chain-defaults set <chain> --agent <agent> --role <role>", contract)
            self.assertIn("Do not prompt for every subtask when active chain defaults already capture", contract)
            self.assertIn("Do not abandon current work for ad-hoc tasks", contract)
            self.assertIn("queue/order it after the current task or at the end of the current chain", contract)
            self.assertIn("Only switch immediately for priority/urgent work", contract)
            self.assertIn("clarification_count, correction_count, need_improvements_count", contract)
            self.assertIn("first_pass_success", contract)
            self.assertIn("derivable from `working_state_set` events", contract)
            self.assertIn("task_chain_id/root_task_id", contract)
            self.assertIn("Multiple active instances of the same profile", contract)
            self.assertIn("immutable or non-learning", contract)
            self.assertIn("do not write state checkpoints", contract)
            self.assertIn("correction-assisted", contract)
            self.assertIn("Never store raw terminal transcripts", contract)
            self.assertIn("When doing a memory audit, inspect bounded task logs/events", contract)
            self.assertIn("working state, task results, task-chain summaries", contract)
            self.assertIn("existing approved memories", contract)
            self.assertIn("propose concise memory additions, edits, or removals only", contract)
            self.assertIn("memory propose <memory-id>", contract)
            self.assertIn("memory propose <memory-id> --archive --reason", contract)
            self.assertIn("memory decide <memory-id> approve|reject", contract)
            self.assertIn("must not self-approve memory", contract)
            self.assertIn("Active memory changes require trusted user/coordinator approval", contract)

    def test_task_chain_summary_creation_retrieval_and_lineage(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            root = k.task_create(title="root", assigned_agent="a")
            k.state_set(root["task_id"], "a", instance_id="a@s1", task_chain_id="chain-1", root_task_id=root["task_id"], status="working", current_activity="coding", next_step="validate")
            approval = k.submit_completion(root["task_id"], agent="a", task_chain_id="chain-1", root_task_id=root["task_id"], result_summary="implemented feature")
            k.review_completion(approval["approval"]["approval_id"], "good", task_version_at_submission=approval["approval"]["task_version_at_submission"])

            summary = k.summarize_chain("chain-1", next_task_chain_id="chain-2", actor="a")
            self.assertEqual(summary["task_chain_id"], "chain-1")
            self.assertEqual(summary["root_task_id"], root["task_id"])
            self.assertEqual(summary["next_task_chain_id"], "chain-2")
            self.assertIn("implemented feature", summary["summary"])
            self.assertLessEqual(len(summary["summary"]), 4000)
            self.assertEqual(k.latest_chain_summary(root["task_id"])["summary_id"], summary["summary_id"])
            events = [e for e in k.events(task_id=root["task_id"]) if e["event_type"] == "task_chain_summarized"]
            self.assertEqual(events[0]["payload"]["next_task_chain_id"], "chain-2")

            follow = k.task_create(title="follow", assigned_agent="a")
            k.state_set(follow["task_id"], "a", instance_id="a@s2", task_chain_id="chain-2", root_task_id=root["task_id"], status="working")
            second = k.summarize_chain("chain-2", actor="a")
            self.assertEqual(second["root_task_id"], root["task_id"])
            self.assertEqual(second["previous_summary_id"], summary["summary_id"])

    def test_agent_contract_template_comes_from_config_toml(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            cfg_dir = Path(tmp) / "broccoli-comms"
            cfg_dir.mkdir()
            (cfg_dir / "config.toml").write_text('[learning]\nagent_contract_template = "custom {agent} {instance} {cwd}"\n')
            self.assertEqual(broccoli.agent_contract_template(), "custom {agent} {instance} {cwd}")
            self.assertEqual(broccoli.agent_contract("a", "i", "/w", broccoli.agent_contract_template(), source_cwd="/src"), "custom a i /w")

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

    def test_submit_completion_creates_pending_approval_and_ordered_events(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            payload = k.submit_completion(
                task["task_id"],
                agent="a",
                agent_instance_id="a@s1",
                task_chain_id="chain-1",
                root_task_id=task["task_id"],
                result_summary="implemented safely",
                acceptance_summary="tests pass",
                reusable_discoveries=[{"label": "database", "value": "analytics", "reason": "bounded"}],
                clarification_count=1,
                correction_count=0,
                need_improvements_count=0,
                first_pass_success=True,
                idempotency_key="idem-1",
            )
            approval = payload["approval"]
            self.assertEqual(approval["status"], "pending")
            self.assertEqual(payload["task"]["status"], "review")
            self.assertEqual(k.list_approvals(status="pending")[0]["approval_id"], approval["approval_id"])
            relevant = [e for e in k.events(task_id=task["task_id"]) if e["event_type"] in {"task_completion_submitted", "task_approval_requested"}]
            self.assertEqual([e["event_type"] for e in relevant], ["task_completion_submitted", "task_approval_requested"])
            self.assertLess(relevant[0]["event_seq"], relevant[1]["event_seq"])

    def test_submit_completion_idempotency_and_duplicate_pending_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            first = k.submit_completion(task["task_id"], agent="a", task_chain_id="chain", result_summary="done", idempotency_key="same")
            retry = k.submit_completion(task["task_id"], agent="a", task_chain_id="chain", result_summary="done", idempotency_key="same")
            self.assertTrue(retry["idempotent"])
            self.assertEqual(retry["approval"]["approval_id"], first["approval"]["approval_id"])
            events = [e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "task_approval_requested"]
            self.assertEqual(len(events), 1)
            with self.assertRaisesRegex(ValueError, "different completion payload"):
                k.submit_completion(task["task_id"], agent="a", task_chain_id="chain", result_summary="changed", idempotency_key="same")
            with self.assertRaisesRegex(ValueError, "pending approval already exists"):
                k.submit_completion(task["task_id"], agent="b", task_chain_id="chain", result_summary="other")

    def test_review_completion_decides_once_and_reuses_mark_result_validation(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            approval = k.submit_completion(task["task_id"], agent="a", result_summary="done")["approval"]
            decided = k.review_completion(approval["approval_id"], "good", task_version_at_submission=approval["task_version_at_submission"])
            self.assertEqual(decided["approval"]["status"], "decided")
            self.assertEqual(decided["task"]["status"], "validated")
            result_events = [e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "task_result_marked"]
            self.assertEqual(len(result_events), 1)
            self.assertEqual(result_events[0]["payload"]["result_status"], "good")
            repeat = k.review_completion(approval["approval_id"], "good")
            self.assertTrue(repeat["idempotent"])
            self.assertEqual(len([e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "task_result_marked"]), 1)

    def test_review_completion_requires_remediation_and_detects_stale_cards(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            approval = k.submit_completion(task["task_id"], agent="a", result_summary="done")["approval"]
            with self.assertRaises(ValueError):
                k.review_completion(approval["approval_id"], "need_improvements")
            k.task_update(task["task_id"], next_step="external change")
            with self.assertRaisesRegex(ValueError, "refresh required"):
                k.review_completion(approval["approval_id"], "bad", next_step="fix", task_version_at_submission=approval["task_version_at_submission"])

    def test_non_learning_and_unsafe_payloads_cannot_submit_completion(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            with self.assertRaisesRegex(ValueError, "non-learning"):
                k.submit_completion(task["task_id"], agent="a", result_summary="done", non_learning=True)
            with self.assertRaisesRegex(ValueError, "exceeds"):
                k.submit_completion(task["task_id"], agent="a", result_summary="x" * 2001)
            redacted = k.submit_completion(task["task_id"], agent="a", task_chain_id="safe", result_summary="token=abc123")
            self.assertIn("[REDACTED]", redacted["approval"]["result_summary"])

    def test_approval_notification_metadata_and_offline_store(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp), mock.patch.object(broccoli, "tracker_rpc", side_effect=RuntimeError("offline")):
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            approval = k.submit_completion(task["task_id"], agent="a", result_summary="done")["approval"]
            notice = broccoli.notify_approval_request(k, approval)
            self.assertFalse(notice["sent"])
            self.assertEqual(k.show_approval(approval["approval_id"])["status"], "pending")
            self.assertEqual(k.list_approvals()[0]["approval_id"], approval["approval_id"])
            failed = [e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "task_approval_notification_failed"]
            self.assertEqual(len(failed), 1)
            md = broccoli.approval_fallback_markdown(approval)
            self.assertIn("Approval required", md)
            self.assertIn(f"Task {task['task_id']} needs your attention", md)
            self.assertNotIn("\n", md)
            self.assertLessEqual(len(md), 4000)

    def test_approval_notification_falsy_rpc_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp), mock.patch.object(broccoli, "tracker_rpc", return_value=None):
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            approval = k.submit_completion(task["task_id"], agent="a", result_summary="done")["approval"]
            notice = broccoli.notify_approval_request(k, approval)
            self.assertFalse(notice["sent"])
            failed = [e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "task_approval_notification_failed"]
            sent = [e for e in k.events(task_id=task["task_id"]) if e["event_type"] == "task_approval_notification_sent"]
            self.assertEqual(len(failed), 1)
            self.assertEqual(sent, [])

    def test_approval_notification_uses_structured_metadata_and_task_kernel_sender(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp), mock.patch.object(broccoli, "tracker_rpc", return_value=True) as tracker_rpc:
            k = broccoli.learning_kernel()
            task = k.task_create(title="approval", assigned_agent="a")
            approval = k.submit_completion(task["task_id"], agent="a", result_summary="done")["approval"]
            notice = broccoli.notify_approval_request(k, approval)
            self.assertTrue(notice["sent"])
            method, params = tracker_rpc.call_args.args
            self.assertEqual(method, "send_message")
            self.assertEqual(params["sender_name"], "task-kernel")
            self.assertEqual(params["metadata"]["content_type"], "application/vnd.broccoli.task-approval+json")
            self.assertEqual(params["metadata"]["approval_id"], approval["approval_id"])
            self.assertEqual(params["metadata"]["task_version_at_submission"], approval["task_version_at_submission"])
            self.assertEqual(params["metadata"]["created_event_seq"], approval["created_event_seq"])
            self.assertEqual(params["metadata"]["event_seq_at_submission"], approval["event_seq_at_submission"])
            self.assertEqual(params["metadata"]["source"], "system/task-kernel")

    def test_memory_edit_proposal_applies_to_target_on_approval(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="validated", assigned_agent="a")
            k.mark_result(task["task_id"], "good")
            proposed = k.memory_propose(type="habit", scope="global", subject_agent="a", title="Old", body="old", source_task_id=task["task_id"], proposed_by="a")
            active = k.memory_approve(proposed["memory"]["memory_id"], expected_version=proposed["memory"]["version"])

            edit = k.memory_propose_edit(active["memory"]["memory_id"], expected_version=active["memory"]["version"], body="new", proposed_by="a", source_task_id=task["task_id"], metadata={"user_key": "keep"})
            self.assertEqual(edit["memory"]["status"], "pending")
            self.assertEqual(edit["memory"]["metadata"]["proposal_kind"], "edit")
            self.assertEqual(edit["memory"]["metadata"]["target_memory_id"], active["memory"]["memory_id"])

            approved = k.memory_approve(edit["memory"]["memory_id"], expected_version=edit["memory"]["version"])
            self.assertEqual(approved["memory"]["memory_id"], active["memory"]["memory_id"])
            self.assertEqual(approved["memory"]["body"], "new")
            self.assertEqual(approved["memory"]["metadata"], {"user_key": "keep"})
            self.assertNotIn("proposal_kind", approved["memory"]["metadata"])
            self.assertNotIn("target_memory_id", approved["memory"]["metadata"])
            self.assertNotIn("target_expected_version", approved["memory"]["metadata"])
            self.assertEqual(approved["proposal"]["status"], "superseded")
            event_types = [e["event_type"] for e in k.events(subject_id=active["memory"]["memory_id"])]
            self.assertIn("memory_edited", event_types)

    def test_memory_archive_proposal_revokes_active_target_on_approval(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="validated", assigned_agent="a")
            k.mark_result(task["task_id"], "good")
            proposed = k.memory_propose(type="fact", scope="global", subject_agent="a", title="Old", body="old", source_task_id=task["task_id"], proposed_by="a")
            active = k.memory_approve(proposed["memory"]["memory_id"], expected_version=proposed["memory"]["version"])

            archive = k.memory_propose_archive(active["memory"]["memory_id"], expected_version=active["memory"]["version"], reason="obsolete", proposed_by="a")
            self.assertEqual(archive["memory"]["status"], "pending")
            self.assertEqual(archive["memory"]["metadata"]["proposal_kind"], "archive")
            self.assertEqual(archive["memory"]["metadata"]["target_memory_id"], active["memory"]["memory_id"])

            approved = k.memory_approve(archive["memory"]["memory_id"], expected_version=archive["memory"]["version"])
            self.assertEqual(approved["memory"]["memory_id"], active["memory"]["memory_id"])
            self.assertEqual(approved["memory"]["status"], "revoked")
            self.assertEqual(approved["proposal"]["status"], "superseded")
            event_types = [e["event_type"] for e in k.events(subject_id=active["memory"]["memory_id"])]
            self.assertIn("memory_revoked", event_types)

    def test_memory_archive_proposal_rejects_pending_target_on_approval(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            target = k.memory_propose(type="habit", scope="global", subject_agent="a", title="Pending", body="pending", proposed_by="a")
            archive = k.memory_propose_archive(target["memory"]["memory_id"], expected_version=target["memory"]["version"], reason="duplicate", proposed_by="a")
            approved = k.memory_approve(archive["memory"]["memory_id"], expected_version=archive["memory"]["version"])
            self.assertEqual(approved["memory"]["memory_id"], target["memory"]["memory_id"])
            self.assertEqual(approved["memory"]["status"], "rejected")
            self.assertEqual(approved["proposal"]["status"], "superseded")

    def test_memory_validated_task_lifecycle_idempotency_and_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="memory", assigned_agent="a", scope="project:x")
            k.mark_result(task["task_id"], "good")
            first = k.memory_propose(type="fact", scope="project:x", subject_agent="a", title="Endpoint", body="Use /latest", source_task_id=task["task_id"], proposed_by="a", idempotency_key="m1")
            retry = k.memory_propose(type="fact", scope="project:x", subject_agent="a", title="Endpoint", body="Use /latest", source_task_id=task["task_id"], proposed_by="a", idempotency_key="m1")
            self.assertTrue(retry["idempotent"])
            events = [e for e in k.events(subject_id=first["memory"]["memory_id"]) if e["event_type"] == "memory_proposed"]
            self.assertEqual(len(events), 1)
            approved = k.memory_approve(first["memory"]["memory_id"], expected_version=first["memory"]["version"])
            self.assertEqual(approved["memory"]["status"], "active")
            self.assertIsNotNone(approved["memory"].get("source_event_seq"))
            updated = k.memory_edit(first["memory"]["memory_id"], body="Use /v2/latest", expected_version=approved["memory"]["version"])
            self.assertEqual(updated["memory"]["status"], "active")
            self.assertEqual(updated["memory"]["body"], "Use /v2/latest")
            rolled_back = k.memory_rollback(first["memory"]["memory_id"], target_version=approved["memory"]["version"], expected_version=updated["memory"]["version"])
            self.assertEqual(rolled_back["memory"]["status"], "active")
            self.assertEqual(rolled_back["memory"]["body"], "Use /latest")
            self.assertEqual(rolled_back["memory"]["version"], updated["memory"]["version"] + 1)
            history = k.memory_history(first["memory"]["memory_id"])
            self.assertEqual(history["memory"]["memory_id"], first["memory"]["memory_id"])
            self.assertIn("memory_approved", [event["event_type"] for event in history["events"]])
            self.assertIn("memory_rolled_back", [event["event_type"] for event in history["events"]])
            self.assertEqual(k.memory_list(status="approved")[0]["memory_id"], first["memory"]["memory_id"])
            boot = k.memory_for_bootstrap(agent="a", scope="project:x")
            self.assertEqual([m["memory_id"] for m in boot["records"]], [first["memory"]["memory_id"]])
            self.assertEqual(boot["records"][0]["body"], "Use /latest")

    def test_memory_unvalidated_immutable_stale_and_hidden_statuses(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="memory", assigned_agent="a", scope="project:x")
            mem = k.memory_propose(type="habit", scope="project:x", subject_agent="a", title="Tests", body="Run tests", source_task_id=task["task_id"], proposed_by="a")
            edited = k.memory_edit(mem["memory"]["memory_id"], title="Tests first", body="Run focused tests", expected_version=mem["memory"]["version"])
            self.assertEqual(edited["memory"]["title"], "Tests first")
            with self.assertRaisesRegex(ValueError, "immutable"):
                k.memory_propose(type="fact", title="No", body="No", source_task_id=task["task_id"], proposed_by="imm", non_learning=True)
            with self.assertRaisesRegex(ValueError, "trusted memory actor"):
                k.memory_propose(type="habit", title="Manual", body="Manual", trusted_manual=True, proposed_by="agent")
            with self.assertRaisesRegex(ValueError, "trusted memory actor"):
                k.memory_approve(mem["memory"]["memory_id"], actor="agent")
            rejected = k.memory_reject(mem["memory"]["memory_id"], expected_version=edited["memory"]["version"])
            self.assertEqual(rejected["memory"]["status"], "rejected")
            self.assertEqual(k.memory_for_bootstrap(agent="a", scope="project:x")["records"], [])
            active_task = k.task_create(title="good", assigned_agent="a", scope="project:x")
            k.mark_result(active_task["task_id"], "good")
            active = k.memory_propose(type="fact", scope="project:x", subject_agent="a", title="A", body="A", source_task_id=active_task["task_id"], proposed_by="a")
            with self.assertRaisesRegex(ValueError, "stale"):
                k.memory_approve(active["memory"]["memory_id"], expected_version=99)

    def test_memory_budget_limit_and_revoke_cleanup_flow(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp), mock.patch.object(broccoli.learning_kernel_module, "MEMORY_LIMITS", {**broccoli.learning_kernel_module.MEMORY_LIMITS, "max_active_per_agent_fact": 1}):
            k = broccoli.learning_kernel()
            task = k.task_create(title="good", assigned_agent="a")
            k.mark_result(task["task_id"], "good")
            one = k.memory_propose(type="fact", subject_agent="a", title="one", body="one", source_task_id=task["task_id"], proposed_by="a")
            two = k.memory_propose(type="fact", subject_agent="a", title="two", body="two", source_task_id=task["task_id"], proposed_by="a")
            k.memory_approve(one["memory"]["memory_id"], expected_version=one["memory"]["version"])
            blocked = k.memory_approve(two["memory"]["memory_id"], expected_version=two["memory"]["version"])
            self.assertTrue(blocked["limit_exceeded"])
            self.assertEqual(blocked["stale_candidates"][0]["memory_id"], one["memory"]["memory_id"])
            k.memory_revoke(one["memory"]["memory_id"], expected_version=2)
            approved = k.memory_approve(two["memory"]["memory_id"], expected_version=two["memory"]["version"])
            self.assertEqual(approved["memory"]["status"], "active")

    def test_memory_expertise_constraints_and_bootstrap_limits(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp), mock.patch.object(broccoli.learning_kernel_module, "MEMORY_LIMITS", {**broccoli.learning_kernel_module.MEMORY_LIMITS, "bootstrap_max_records": 1, "bootstrap_max_body_chars_per_record": 5, "bootstrap_max_total_chars": 100}):
            k = broccoli.learning_kernel()
            task = k.task_create(title="good", assigned_agent="a", scope="project:x")
            k.mark_result(task["task_id"], "good")
            with self.assertRaisesRegex(ValueError, "expertise requires"):
                k.memory_propose(type="expertise", scope="global", title="Expert", body="bounded", source_task_id=task["task_id"], proposed_by="a")
            with self.assertRaisesRegex(ValueError, "score"):
                k.memory_propose(type="expertise", scope="project:x", subject_agent="a", title="Expert", body="bounded", source_task_id=task["task_id"], proposed_by="a", metadata={"score": 10})
            mem = k.memory_propose(type="expertise", scope="project:x", subject_agent="a", title="Expert", body="abcdef", source_task_id=task["task_id"], proposed_by="a")
            k.memory_approve(mem["memory"]["memory_id"], expected_version=mem["memory"]["version"])
            boot = k.memory_for_bootstrap(agent="a", scope="project:x")
            self.assertEqual(len(boot["records"]), 1)
            self.assertEqual(boot["records"][0]["body"], "abcde")
            self.assertTrue(boot["truncated"])

    def test_memory_stale_idempotent_transition_and_expertise_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(tmp):
            k = broccoli.learning_kernel()
            task = k.task_create(title="good", assigned_agent="a", scope="project:x")
            k.mark_result(task["task_id"], "good")
            mem = k.memory_propose(type="fact", subject_agent="a", title="A", body="A", source_task_id=task["task_id"], proposed_by="a")
            active = k.memory_approve(mem["memory"]["memory_id"], expected_version=mem["memory"]["version"])
            with self.assertRaisesRegex(ValueError, "stale"):
                k.memory_approve(mem["memory"]["memory_id"], expected_version=mem["memory"]["version"])
            revoked = k.memory_revoke(active["memory"]["memory_id"], reason="old", expected_version=active["memory"]["version"])
            self.assertTrue(k.memory_revoke(active["memory"]["memory_id"], reason="old", expected_version=revoked["memory"]["version"])["idempotent"])
            with self.assertRaisesRegex(ValueError, "stale"):
                k.memory_revoke(active["memory"]["memory_id"], expected_version=active["memory"]["version"])
            with self.assertRaisesRegex(ValueError, "conflict"):
                k.memory_revoke(active["memory"]["memory_id"], reason="different", expected_version=revoked["memory"]["version"])
            bad_task = k.task_create(title="bad", assigned_agent="a", scope="project:x")
            exp = k.memory_propose(type="expertise", scope="project:x", subject_agent="a", title="E", body="E", source_task_id=task["task_id"], proposed_by="a", metadata={"evidence_task_ids": [bad_task["task_id"]]})
            self.assertEqual(exp["memory"]["type"], "expertise")
            with self.assertRaisesRegex(ValueError, "metadata"):
                k.memory_propose(type="expertise", scope="project:x", subject_agent="a", title="E", body="E", source_task_id=task["task_id"], proposed_by="a", metadata={"nested": {"Score": 1}})
            with self.assertRaisesRegex(ValueError, "unsupported"):
                k.memory_propose(type="expertise", scope="project:x", subject_agent="a", title="E", body="E", source_task_id=task["task_id"], proposed_by="a", metadata={"extra": "no"})


if __name__ == "__main__":
    unittest.main()
