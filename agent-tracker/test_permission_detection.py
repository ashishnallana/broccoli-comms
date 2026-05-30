import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import permission_detection


class PermissionDetectionConfigTests(unittest.TestCase):
    def setUp(self):
        self.old_config_env = os.environ.get(permission_detection.CONFIG_ENV)
        permission_detection._config_cache = None
        permission_detection._last_scan_by_agent.clear()
        permission_detection._recent_notifications.clear()
        permission_detection._status_by_agent.clear()

    def tearDown(self):
        if self.old_config_env is None:
            os.environ.pop(permission_detection.CONFIG_ENV, None)
        else:
            os.environ[permission_detection.CONFIG_ENV] = self.old_config_env
        permission_detection._config_cache = None
        permission_detection._last_scan_by_agent.clear()
        permission_detection._recent_notifications.clear()
        permission_detection._status_by_agent.clear()

    def test_missing_config_disables_detection(self):
        os.environ[permission_detection.CONFIG_ENV] = "/tmp/does-not-exist-agent-tracker-detection.json"
        cfg = permission_detection.load_detection_config()
        self.assertFalse(cfg.enabled)

    def test_config_clamps_capture_lines_to_ten(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "detection.json"
            path.write_text(json.dumps({
                "enabled": True,
                "providers": {
                    "claude": {
                        "capture_lines": 100,
                        "keywords": ["allow"]
                    }
                }
            }))
            os.environ[permission_detection.CONFIG_ENV] = str(path)
            cfg = permission_detection.load_detection_config()
            self.assertTrue(cfg.providers["claude"].enabled)
            self.assertEqual(cfg.providers["claude"].capture_lines, 10)

    def test_agent_detection_config_uses_provider_type(self):
        provider_cfg = permission_detection.AgentDetectionConfig(
            enabled=True,
            capture_lines=10,
            scan_interval_seconds=1,
            notify_cooldown_seconds=300,
            keyword_matches_required=2,
            max_excerpt_chars=2000,
            keywords=("type something", "chat about this"),
        )
        config = permission_detection.DetectionConfig(
            enabled=True,
            notify_target="agent-communicator",
            sender_name="permission-monitor",
            providers={"claude": provider_cfg},
            agents={},
            default=None,
        )
        self.assertIs(permission_detection.agent_detection_config(config, "any-claude-name", {"agent_type": "claude", "agent_cmd": "claude"}), provider_cfg)

    def test_detect_requires_configured_keyword_count(self):
        cfg = permission_detection.AgentDetectionConfig(
            enabled=True,
            capture_lines=10,
            scan_interval_seconds=1,
            notify_cooldown_seconds=300,
            keyword_matches_required=2,
            max_excerpt_chars=2000,
            keywords=("wants to use bash", "do you want to allow", "decline"),
        )
        info = {"agent_id": "a1", "tmux_pane": "%1"}
        miss = permission_detection.detect_blocking_prompt("claude-1", info, "Claude wants to use Bash", cfg)
        self.assertIsNone(miss)
        hit = permission_detection.detect_blocking_prompt(
            "claude-1",
            info,
            "Claude wants to use Bash\nDo you want to allow this?",
            cfg,
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.capture_lines, 10)
        self.assertEqual(hit.matched_keywords, ("wants to use bash", "do you want to allow"))

    def test_notification_does_not_recreate_existing_communicator(self):
        calls = []
        fake_rpc = types.SimpleNamespace(
            handle_ensure_mailbox=lambda params: calls.append(("ensure", params)),
            handle_send_message=lambda params: calls.append(("send", params)),
        )
        cfg = permission_detection.DetectionConfig(
            enabled=True,
            notify_target="agent-communicator",
            sender_name="permission-monitor",
            providers={},
            agents={},
            default=None,
        )
        detection = permission_detection.BlockingDetection(
            agent_name="claude-1",
            agent_id="a1",
            pane_id="%1",
            capture_lines=10,
            matched_keywords=("allow",),
            excerpt="allow?",
            fingerprint="fp",
        )
        with mock.patch.dict(sys.modules, {"rpc_handler": fake_rpc}), \
             mock.patch.object(permission_detection.state, "get_agent", return_value={"tmux_pane": "%9"}):
            permission_detection._send_detection_notification(cfg, detection)
        self.assertEqual(calls[0][0], "send")
        self.assertIn("/text", calls[0][1]["message"])
        self.assertIn("/keys", calls[0][1]["message"])

    def test_notification_creates_missing_communicator_mailbox(self):
        calls = []
        fake_rpc = types.SimpleNamespace(
            handle_ensure_mailbox=lambda params: calls.append(("ensure", params)),
            handle_send_message=lambda params: calls.append(("send", params)),
        )
        cfg = permission_detection.DetectionConfig(
            enabled=True,
            notify_target="agent-communicator",
            sender_name="permission-monitor",
            providers={},
            agents={},
            default=None,
        )
        detection = permission_detection.BlockingDetection(
            agent_name="claude-1",
            agent_id="a1",
            pane_id="%1",
            capture_lines=10,
            matched_keywords=("allow",),
            excerpt="allow?",
            fingerprint="fp",
        )
        with mock.patch.dict(sys.modules, {"rpc_handler": fake_rpc}), \
             mock.patch.object(permission_detection.state, "get_agent", return_value=None):
            permission_detection._send_detection_notification(cfg, detection)
        self.assertEqual(calls[0], ("ensure", {"agent_name": "agent-communicator"}))
        self.assertEqual(calls[1][0], "send")

    def test_real_claude_approval_prompt_is_detected(self):
        cfg = permission_detection.AgentDetectionConfig(
            enabled=True,
            capture_lines=10,
            scan_interval_seconds=1,
            notify_cooldown_seconds=300,
            keyword_matches_required=2,
            max_excerpt_chars=2000,
            keywords=("bash command", "requires approval", "do you want to proceed"),
        )
        prompt = """─────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Bash command

   agent-tracker-ctl send-message agent-communicator "Acknowledged. Hi! I'm Claude Code, working in the
   nix-config repository. How can I help you?"
   Acknowledge and reply to agent-communicator

 This command requires approval

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don’t ask again for: agent-tracker-ctl send-message *
   3. No"""
        hit = permission_detection.detect_blocking_prompt("claude-1", {"agent_id": "a1", "tmux_pane": "%1"}, prompt, cfg)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.matched_keywords, ("bash command", "requires approval", "do you want to proceed"))

    def test_real_codex_command_prompt_is_detected_by_generic_keywords(self):
        cfg = permission_detection.AgentDetectionConfig(
            enabled=True,
            capture_lines=10,
            scan_interval_seconds=1,
            notify_cooldown_seconds=300,
            keyword_matches_required=2,
            max_excerpt_chars=2000,
            keywords=(
                "would you like to run the following command",
                "yes, proceed",
                "don't ask again",
                "no, and tell codex",
            ),
        )
        prompt = """Would you like to run the following command?

  Reason: Allow ICMP ping to check whether 8.8.8.8 is reachable from this machine?

  $ ping -c 4 8.8.8.8

› 1. Yes, proceed (y)
  2. Yes, and don't ask again for commands that start with `ping` (p)
  3. No, and tell Codex what to do differently (esc)"""
        hit = permission_detection.detect_blocking_prompt("codex-1", {"agent_id": "a1", "tmux_pane": "%1"}, prompt, cfg)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.matched_keywords, (
            "would you like to run the following command",
            "yes, proceed",
            "don't ask again",
            "no, and tell codex",
        ))

    def test_real_claude_web_search_prompt_is_detected(self):
        cfg = permission_detection.AgentDetectionConfig(
            enabled=True,
            capture_lines=10,
            scan_interval_seconds=1,
            notify_cooldown_seconds=300,
            keyword_matches_required=2,
            max_excerpt_chars=2000,
            keywords=("tool use", "web search", "claude wants to search the web", "do you want to proceed"),
        )
        prompt = """────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Tool use

   Web Search("IPL 2026 standings points table")
   Claude wants to search the web for: IPL 2026 standings points table

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for Web Search commands in /home/tanmay/projects/nix/broccoli-comms
   3. No"""
        hit = permission_detection.detect_blocking_prompt("claude-1", {"agent_id": "a1", "tmux_pane": "%1"}, prompt, cfg)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.matched_keywords, ("tool use", "web search", "claude wants to search the web", "do you want to proceed"))

    def test_real_claude_task_prompt_is_detected_by_type_something(self):
        cfg = permission_detection.AgentDetectionConfig(
            enabled=True,
            capture_lines=10,
            scan_interval_seconds=1,
            notify_cooldown_seconds=300,
            keyword_matches_required=2,
            max_excerpt_chars=2000,
            keywords=("what would you like to work on today", "type something"),
        )
        prompt = """☐ Task

What would you like to work on today?

  1. Bug fix
     Track down and fix an existing issue in the codebase
  2. New feature
     Implement something new
  3. Refactor
     Clean up or restructure existing code
❯ 4. Code review
     Review recent changes or a pull request
  5. Type something.
────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  6. Chat about this"""
        hit = permission_detection.detect_blocking_prompt("claude-1", {"agent_id": "a1", "tmux_pane": "%1"}, prompt, cfg)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.matched_keywords, ("what would you like to work on today", "type something"))

    def test_pane_title_contributes_to_detection(self):
        cfg = permission_detection.AgentDetectionConfig(
            enabled=True,
            capture_lines=10,
            scan_interval_seconds=1,
            notify_cooldown_seconds=300,
            keyword_matches_required=2,
            max_excerpt_chars=2000,
            keywords=("codex", "approval required"),
        )
        hit = permission_detection.detect_blocking_prompt(
            "codex-1",
            {"agent_id": "a1", "tmux_pane": "%100"},
            "ordinary pane text",
            cfg,
            pane_title="Codex approval required",
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.pane_title, "Codex approval required")
        self.assertEqual(hit.matched_keywords, ("codex", "approval required"))
        self.assertIn("Pane title: `Codex approval required`", permission_detection._format_detection_message(hit))

    def test_monitor_can_detect_from_pane_title(self):
        cfg = permission_detection.DetectionConfig(
            enabled=True,
            notify_target="agent-communicator",
            sender_name="permission-monitor",
            default=None,
            providers={
                "codex": permission_detection.AgentDetectionConfig(
                    enabled=True,
                    capture_lines=10,
                    scan_interval_seconds=1,
                    notify_cooldown_seconds=300,
                    keyword_matches_required=2,
                    max_excerpt_chars=2000,
                    keywords=("codex", "approval required"),
                )
            },
            agents={},
        )
        with mock.patch.object(permission_detection, "load_detection_config", return_value=cfg), \
             mock.patch.object(permission_detection.state, "get_all_agents", return_value={"codex-1": {"agent_id": "a1", "tmux_pane": "%100", "agent_type": "codex", "agent_cmd": "codex"}}), \
             mock.patch.object(permission_detection.tmux_util, "capture_pane_visible_text", return_value="ordinary pane text"), \
             mock.patch.object(permission_detection.tmux_util, "get_pane_title", return_value="Codex approval required"), \
             mock.patch.object(permission_detection, "_send_detection_notification") as send:
            self.assertEqual(permission_detection.detection_monitor_once(now=1000.0), 1)
            detection = send.call_args.args[1]
            self.assertEqual(detection.pane_title, "Codex approval required")
            self.assertEqual(detection.matched_keywords, ("codex", "approval required"))

    def test_detection_status_snapshot_reports_countdown_and_result(self):
        cfg = permission_detection.DetectionConfig(
            enabled=True,
            notify_target="agent-communicator",
            sender_name="permission-monitor",
            default=None,
            providers={
                "claude": permission_detection.AgentDetectionConfig(
                    enabled=True,
                    capture_lines=10,
                    scan_interval_seconds=5,
                    notify_cooldown_seconds=300,
                    keyword_matches_required=2,
                    max_excerpt_chars=2000,
                    keywords=("wants to use bash", "do you want to allow"),
                )
            },
            agents={},
        )
        with mock.patch.object(permission_detection, "load_detection_config", return_value=cfg), \
             mock.patch.object(permission_detection.state, "get_all_agents", return_value={"claude-1": {"agent_id": "a1", "tmux_pane": "%1", "agent_type": "claude", "agent_cmd": "claude"}}), \
             mock.patch.object(permission_detection.tmux_util, "capture_pane_visible_text", return_value="ordinary pane text"), \
             mock.patch.object(permission_detection.tmux_util, "get_pane_title", return_value=""):
            self.assertEqual(permission_detection.detection_monitor_once(now=1000.0), 0)
        status = permission_detection.detection_status_snapshot(now=1002.0)["claude-1"]
        self.assertTrue(status["enabled"])
        self.assertEqual(status["provider"], "claude")
        self.assertEqual(status["last_result"], "no_match")
        self.assertEqual(status["seconds_until_next_scan"], 3)

    def test_monitor_sends_notification_once_with_cooldown(self):
        cfg = permission_detection.DetectionConfig(
            enabled=True,
            notify_target="agent-communicator",
            sender_name="permission-monitor",
            default=None,
            providers={
                "claude": permission_detection.AgentDetectionConfig(
                    enabled=True,
                    capture_lines=10,
                    scan_interval_seconds=1,
                    notify_cooldown_seconds=300,
                    keyword_matches_required=2,
                    max_excerpt_chars=2000,
                    keywords=("wants to use bash", "do you want to allow"),
                )
            },
            agents={},
        )
        with mock.patch.object(permission_detection, "load_detection_config", return_value=cfg), \
             mock.patch.object(permission_detection.state, "get_all_agents", return_value={"claude-1": {"agent_id": "a1", "tmux_pane": "%1", "agent_type": "claude", "agent_cmd": "claude"}}), \
             mock.patch.object(permission_detection.tmux_util, "capture_pane_visible_text", return_value="Claude wants to use Bash\nDo you want to allow this?"), \
             mock.patch.object(permission_detection.tmux_util, "get_pane_title", return_value=""), \
             mock.patch.object(permission_detection, "_send_detection_notification") as send:
            self.assertEqual(permission_detection.detection_monitor_once(now=1000.0), 1)
            self.assertEqual(permission_detection.detection_monitor_once(now=1001.1), 0)
            send.assert_called_once()
            detection = send.call_args.args[1]
            self.assertIn("wants to use bash", detection.matched_keywords)


if __name__ == "__main__":
    unittest.main()
