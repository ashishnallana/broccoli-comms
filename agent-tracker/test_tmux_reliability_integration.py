"""Integration tests for tmux_reliability.py using a real tmux session."""

import os
import subprocess
import sys
import time
import unittest

# Ensure we can import tmux_reliability
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmux_reliability

class TestTmuxReliabilityIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a unique temporary tmux session for testing
        cls.session_name = f"tmux_reliability_test_{int(time.time())}"
        shell = os.getenv("TEST_SHELL", "bash")
        try:
            # Start a detached tmux session
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", cls.session_name, shell],
                check=True,
                capture_output=True
            )
            # Get the pane ID of the spawned window
            out = subprocess.run(
                ["tmux", "list-panes", "-t", cls.session_name, "-F", "#{pane_id}"],
                check=True,
                capture_output=True,
                text=True
            )
            cls.pane_id = out.stdout.strip()
            print(f"Created temp tmux session '{cls.session_name}' with pane '{cls.pane_id}' for testing.")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create test tmux session: {e.stderr}")

    @classmethod
    def tearDownClass(cls):
        # Kill the temporary tmux session
        print(f"Cleaning up temp tmux session '{cls.session_name}'...")
        subprocess.run(["tmux", "kill-session", "-t", cls.session_name], check=False)

    def test_01_is_pane_alive(self):
        # The pane should be alive initially
        self.assertTrue(tmux_reliability.is_pane_alive(self.pane_id))

    def test_02_send_keys_reliable(self):
        # Send a simple echo and verify it appears (we don't execute it, just send keys)
        # Wait, if bash is running, sending "echo hello" followed by Enter will execute it.
        # That's fine, it will appear on screen.
        unique_str = f"UNIQUE_TEST_STRING_{int(time.time())}"
        success = tmux_reliability.send_keys_reliable(self.pane_id, f"echo {unique_str}", timeout=5)
        self.assertTrue(success)

    def test_03_execute_command_reliable_success(self):
        # Execute a successful command
        exit_code = tmux_reliability.execute_command_reliable(self.pane_id, "true", timeout=5)
        self.assertEqual(exit_code, 0)

    def test_04_execute_command_reliable_failure(self):
        # Execute a failing command
        exit_code = tmux_reliability.execute_command_reliable(self.pane_id, "false", timeout=5)
        self.assertEqual(exit_code, 1)

    def test_05_execute_command_reliable_timeout(self):
        # Execute a hanging command with a short timeout
        exit_code = tmux_reliability.execute_command_reliable(self.pane_id, "sleep 10", timeout=2)
        self.assertIsNone(exit_code)
        # Clean up the hanging sleep command in the pane so it doesn't block future tests
        # Send Ctrl-C to abort
        subprocess.run(["tmux", "send-keys", "-t", self.pane_id, "C-c"], check=True)
        time.sleep(0.5)

    def test_06_copy_mode_recovery(self):
        # Put the pane into copy mode
        subprocess.run(["tmux", "copy-mode", "-t", self.pane_id], check=True)
        
        # Verify we can detect and exit copy mode
        # exit_copy_mode_if_needed should return True since it was in copy mode
        was_in_copy_mode = tmux_reliability.exit_copy_mode_if_needed(self.pane_id)
        self.assertTrue(was_in_copy_mode)

        # Verify we can still execute commands after exiting copy mode
        exit_code = tmux_reliability.execute_command_reliable(self.pane_id, "echo 'after copy mode'", timeout=5)
        self.assertEqual(exit_code, 0)

    def test_07_is_pane_alive_dead_pane(self):
        # Create a new pane in our session, then kill it to test dead pane detection
        out = subprocess.run(
            ["tmux", "split-window", "-d", "-t", self.pane_id, "-P", "-F", "#{pane_id}", "sleep 1"],
            check=True,
            capture_output=True,
            text=True
        )
        temp_pane = out.stdout.strip()
        
        # It should be alive initially
        self.assertTrue(tmux_reliability.is_pane_alive(temp_pane))
        
        # Kill it
        subprocess.run(["tmux", "kill-pane", "-t", temp_pane], check=True)
        
        # Now it should be dead
        self.assertFalse(tmux_reliability.is_pane_alive(temp_pane))

if __name__ == "__main__":
    unittest.main()
