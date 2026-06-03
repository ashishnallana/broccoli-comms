package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"
)

func TestBroccoliAgentTrackerCommandPrefersBroccoliWrapperEnv(t *testing.T) {
	config.ResetForTest()
	t.Cleanup(config.ResetForTest)
	t.Setenv("BROCCOLI_COMMS_CLI", "/nix/store/bin/broccoli-comms")
	cmd := broccoliAgentTrackerCommandContext(context.Background(), "list")
	want := []string{"/nix/store/bin/broccoli-comms", "agent-tracker", "list"}
	if !equalStrings(cmd.Args, want) {
		t.Fatalf("cmd.Args = %#v, want %#v", cmd.Args, want)
	}
}

func TestBroccoliAgentTrackerCommandIgnoresConfiguredExecutablePaths(t *testing.T) {
	dir := t.TempDir()
	configDir := filepath.Join(dir, "broccoli-comms")
	if err := os.MkdirAll(configDir, 0o755); err != nil {
		t.Fatal(err)
	}
	configText := "[executables]\n" +
		"agent_tracker_ctl = \"/nix/store/example/bin/agent-tracker-ctl\"\n" +
		"agent_tracker_ctl_py = \"/nix/store/example/agent-tracker-ctl.py\"\n"
	if err := os.WriteFile(filepath.Join(configDir, "config.toml"), []byte(configText), 0o644); err != nil {
		t.Fatal(err)
	}
	config.ResetForTest()
	t.Cleanup(config.ResetForTest)
	t.Setenv("XDG_CONFIG_HOME", dir)
	t.Setenv("BROCCOLI_COMMS_CLI", "")

	cmd := broccoliAgentTrackerCommandContext(context.Background(), "list")
	want := []string{"broccoli-comms", "agent-tracker", "list"}
	if !equalStrings(cmd.Args, want) {
		t.Fatalf("cmd.Args = %#v, want %#v", cmd.Args, want)
	}
}

func TestBroccoliAgentTrackerCommandDefaultsToWrapperStyle(t *testing.T) {
	config.ResetForTest()
	t.Cleanup(config.ResetForTest)
	t.Setenv("XDG_CONFIG_HOME", t.TempDir())
	t.Setenv("BROCCOLI_COMMS_CLI", "")
	cmd := broccoliAgentTrackerCommandContext(context.Background(), "list")
	want := []string{"broccoli-comms", "agent-tracker", "list"}
	if !equalStrings(cmd.Args, want) {
		t.Fatalf("cmd.Args = %#v, want %#v", cmd.Args, want)
	}
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
