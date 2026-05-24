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

func TestCtrlEnterAttemptsPaneSwitchForSelectedAgent(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlJ})
	if cmd == nil {
		t.Fatal("ctrl+enter should attempt pane switch")
	}
	msg := cmd().(paneSwitched)
	if msg.Err == nil || !strings.Contains(msg.Err.Error(), "no tmux pane") {
		t.Fatalf("pane switch msg = %#v", msg)
	}
}

func TestCtrlEnterRejectsRemoteSelectedAgent(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "remote"}}}
	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlJ})
	if cmd == nil {
		t.Fatal("ctrl+enter should return error command")
	}
	msg := cmd().(paneSwitched)
	if msg.Err == nil || !strings.Contains(msg.Err.Error(), "remote agent") {
		t.Fatalf("pane switch msg = %#v", msg)
	}
}
