package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestRowFromTrackerAgentKeepsLocalTmuxPane(t *testing.T) {
	row := rowFromTrackerAgent("alpha", tracker.Agent{Scope: "local", TmuxPane: "%7"})
	if row.TmuxPane != "%7" {
		t.Fatalf("row = %+v", row)
	}
}

func TestFocusSelectedPaneCommandAttemptsPaneSwitchForSelectedAgent(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	cmd := focusSelectedPaneCommand(t, &m)
	if cmd == nil {
		t.Fatal("focus selected pane should attempt pane switch")
	}
	msg := cmd().(paneSwitched)
	if msg.Err == nil || !strings.Contains(msg.Err.Error(), "no tmux pane") {
		t.Fatalf("pane switch msg = %#v", msg)
	}
}

func TestFocusSelectedPaneCommandRejectsRemoteSelectedAgent(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "remote"}}}
	cmd := focusSelectedPaneCommand(t, &m)
	if cmd == nil {
		t.Fatal("focus selected pane should return error command")
	}
	msg := cmd().(paneSwitched)
	if msg.Err == nil || !strings.Contains(msg.Err.Error(), "remote agent") {
		t.Fatalf("pane switch msg = %#v", msg)
	}
}

func TestNewTmuxCommandUsesPrivateSocketAndStripsInheritedTmux(t *testing.T) {
	t.Setenv("AGENT_TRACKER_TMUX_SOCKET", "/tmp/private-tmux.sock")
	t.Setenv("TMUX", "/tmp/default.sock,1,0")
	t.Setenv("TMUX_PANE", "%1")
	cmd := newTmuxCommand("switch-client", "-t", "%7")
	want := "tmux -S /tmp/private-tmux.sock switch-client -t %7"
	if strings.Join(cmd.Args, " ") != want {
		t.Fatalf("tmux command = %#v, want %s", cmd.Args, want)
	}
	for _, entry := range cmd.Env {
		if strings.HasPrefix(entry, "TMUX=") || strings.HasPrefix(entry, "TMUX_PANE=") {
			t.Fatalf("tmux command env leaked inherited tmux env: %q", entry)
		}
	}
}

func TestFocusSelectedPaneCommandUsesPaneSwitchCommand(t *testing.T) {
	oldRun := runTmuxCommand
	var got []string
	runTmuxCommand = func(args ...string) error {
		got = append([]string{}, args...)
		return nil
	}
	defer func() { runTmuxCommand = oldRun }()

	m := model{rows: []agentRow{{Name: "alpha", Scope: "local", TmuxPane: "%7"}}}
	cmd := focusSelectedPaneCommand(t, &m)
	if cmd == nil {
		t.Fatal("focus selected pane should return pane switch command")
	}
	if msg := cmd().(paneSwitched); msg.Err != nil {
		t.Fatalf("pane switch err = %v", msg.Err)
	}
	if strings.Join(got, " ") != "switch-client -t %7" {
		t.Fatalf("runTmuxCommand args = %#v", got)
	}
}

func focusSelectedPaneCommand(t *testing.T, m *model) tea.Cmd {
	t.Helper()
	for _, action := range commandPaletteActions() {
		if action.ID == "focus-selected-pane" {
			return action.Run(m)
		}
	}
	t.Fatal("focus-selected-pane command not found")
	return nil
}
