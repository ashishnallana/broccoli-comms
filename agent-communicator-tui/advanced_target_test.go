package main

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestAdvancedSelectionDoesNotChangeComposerTarget(t *testing.T) {
	m := model{mode: advancedView, selected: 0, rows: []agentRow{{Name: "alice", Scope: "local"}, {Name: "bob", Scope: "local"}}, allMessages: []tracker.Message{{Sender: "bob", Body: "old"}, {Sender: "alice", Body: "new"}}}
	m.selectLatestMessage()
	if m.selected != 0 {
		t.Fatalf("selectLatestMessage changed selected row = %d, want 0", m.selected)
	}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = updated.(model)
	if m.selected != 0 {
		t.Fatalf("message selection changed selected row = %d, want 0", m.selected)
	}
}
