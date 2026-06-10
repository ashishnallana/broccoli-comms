import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

_TRACKER_DIR = os.path.dirname(__file__)
if _TRACKER_DIR not in sys.path:
    sys.path.insert(0, _TRACKER_DIR)
_SCHED_PATH = os.path.join(_TRACKER_DIR, "scheduled_jobs.py")
_spec = importlib.util.spec_from_file_location("scheduled_jobs", _SCHED_PATH)
scheduled_jobs = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = scheduled_jobs
_spec.loader.exec_module(scheduled_jobs)


class TestScheduledJobs(unittest.TestCase):
    def test_agent_task_nudge_only_nudges_local_non_blocked_agents(self):
        agents = {
            "local-worker": {"scope": "local", "tmux_pane": "%1", "tmux_socket": "/tmp/tmux.sock", "agent_type": "pi"},
            "remote-worker": {"scope": "remote", "tmux_pane": "%2", "tmux_socket": "/tmp/tmux.sock", "agent_type": "pi"},
            "blocked-worker": {"scope": "local", "tmux_pane": "%3", "tmux_socket": "/tmp/tmux.sock", "agent_type": "pi"},
            "mailbox": {"scope": "local", "is_mailbox": True, "direct_input_disabled": True, "agent_type": "agent-communicator-ui"},
            "no-task": {"scope": "local", "tmux_pane": "%4", "tmux_socket": "/tmp/tmux.sock", "agent_type": "pi"},
        }
        task_fields = {
            "local-worker": {"current_task_id": "task-1", "current_task": "Build feature", "current_task_status": "working", "current_task_next_step": "run tests"},
            "remote-worker": {"current_task_id": "task-2", "current_task": "Remote feature", "current_task_status": "working", "current_task_next_step": "ship"},
            "blocked-worker": {"current_task_id": "task-3", "current_task": "Blocked feature", "current_task_status": "blocked", "current_task_next_step": "wait"},
            "mailbox": {"current_task_id": "task-4", "current_task": "UI", "current_task_status": "working", "current_task_next_step": "none"},
            "no-task": {"current_task_id": "", "current_task": "", "current_task_status": "", "current_task_next_step": ""},
        }

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(scheduled_jobs.config, "load_config", return_value={"scheduled_jobs": {"agent_task_nudge": {"state_path": os.path.join(tmp, "nudges.json")}}}), \
             mock.patch.object(scheduled_jobs.state, "get_all_agents", return_value=agents), \
             mock.patch.object(scheduled_jobs.state, "durable_current_tasks_by_agent", return_value={}), \
             mock.patch.object(scheduled_jobs.state, "current_task_fields_for_agent", side_effect=lambda name, info, durable: task_fields[name]), \
             mock.patch.object(scheduled_jobs.tmux_util, "send_symbolic_keys") as send_keys, \
             mock.patch.object(scheduled_jobs.tmux_util, "send_literal_text") as send_text:
            counts = scheduled_jobs.run_agent_task_nudge_once()

        self.assertEqual(counts, {"checked": 5, "nudged": 1, "skipped": 4, "backoff_skipped": 0, "max_skipped": 0, "errors": 0})
        send_keys.assert_called_once_with("%1", ["Escape"], socket_path="/tmp/tmux.sock")
        send_text.assert_called_once()
        self.assertEqual(send_text.call_args.args[0], "%1")
        self.assertIn("task `task-1`", send_text.call_args.args[1])
        self.assertIn("mark the current task blocked", send_text.call_args.args[1])
        self.assertEqual(send_text.call_args.kwargs, {"submit": True, "socket_path": "/tmp/tmux.sock"})

    def test_job_config_reads_per_job_frequency_from_config(self):
        cfg = {"scheduled_jobs": {"agent_task_nudge": {"enabled": True, "interval_seconds": 42}}}
        with mock.patch.object(scheduled_jobs.config, "load_config", return_value=cfg):
            self.assertEqual(scheduled_jobs._job_config("agent_task_nudge"), (True, 42.0))

    def test_task_nudges_use_persistent_backoff_and_max_nudges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nudges.json")
            cfg = {"scheduled_jobs": {"agent_task_nudge": {"interval_seconds": 10, "backoff_multiplier": 2, "max_nudges": 2, "state_path": path}}}
            nudge_state = {}
            nudge_cfg = {"interval_seconds": 10.0, "backoff_multiplier": 2.0, "max_nudges": 2, "state_path": path}
            self.assertEqual(scheduled_jobs._agent_task_nudge_config.__name__, "_agent_task_nudge_config")
            with mock.patch.object(scheduled_jobs.config, "load_config", return_value=cfg):
                self.assertEqual(scheduled_jobs._agent_task_nudge_config()["state_path"], path)
            self.assertEqual(scheduled_jobs._task_nudge_allowed("task-1", nudge_state, nudge_cfg, now=100), (True, "ok"))
            scheduled_jobs._record_task_nudge("task-1", nudge_state, now=100)
            self.assertEqual(scheduled_jobs._task_nudge_allowed("task-1", nudge_state, nudge_cfg, now=119), (False, "backoff"))
            self.assertEqual(scheduled_jobs._task_nudge_allowed("task-1", nudge_state, nudge_cfg, now=120), (True, "ok"))
            scheduled_jobs._record_task_nudge("task-1", nudge_state, now=120)
            self.assertEqual(scheduled_jobs._task_nudge_allowed("task-1", nudge_state, nudge_cfg, now=1000), (False, "max_nudges"))
            scheduled_jobs._save_nudge_state(path, nudge_state)
            self.assertEqual(scheduled_jobs._load_nudge_state(path)["task-1"]["count"], 2)

    def test_job_config_supports_global_disable_and_interval_minutes(self):
        with mock.patch.object(scheduled_jobs.config, "load_config", return_value={"scheduled_jobs": {"enabled": False}}):
            self.assertEqual(scheduled_jobs._job_config("agent_task_nudge"), (False, scheduled_jobs.DEFAULT_AGENT_TASK_NUDGE_INTERVAL_SECONDS))
        with mock.patch.object(scheduled_jobs.config, "load_config", return_value={"scheduled_jobs": {"agent_task_nudge": {"interval_minutes": 2}}}):
            self.assertEqual(scheduled_jobs._job_config("agent_task_nudge"), (True, 120.0))

    def test_scheduler_registry_uses_named_jobs_for_future_extension(self):
        jobs = scheduled_jobs.scheduled_jobs()
        self.assertEqual([job.name for job in jobs], ["agent_task_nudge"])
        self.assertEqual(jobs[0].default_interval_seconds, 600)
        self.assertTrue(callable(jobs[0].run_once))


if __name__ == "__main__":
    unittest.main()
