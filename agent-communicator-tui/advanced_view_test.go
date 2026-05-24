package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestCtrlTTogglesAdvancedViewAndLoadsAllInbox(t *testing.T) {
	local := &fakeLocal{inbox: []tracker.Message{{Sender: "alpha", Body: "a"}, {Sender: "beta", Body: "b"}}}
	m := model{ownName: "agent-communicator", rows: []agentRow{{Name: "alpha", Scope: "local"}}, local: local}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlT})
	m = updated.(model)
	if m.mode != advancedView || cmd == nil {
		t.Fatalf("mode=%v cmd=%v", m.mode, cmd)
	}
	updated, _ = m.Update(cmd())
	m = updated.(model)
	if len(m.allMessages) != 2 {
		t.Fatalf("allMessages = %+v", m.allMessages)
	}
	if local.lastLimit != advancedInboxFetchLimit {
		t.Fatalf("ReadInbox limit = %d, want %d", local.lastLimit, advancedInboxFetchLimit)
	}
}

func TestAdvancedComposerShowsSelectedReceiverName(t *testing.T) {
	m := model{mode: advancedView, rows: []agentRow{{Name: "alpha"}}}
	view := m.composerView(80)
	if !strings.Contains(view, "@alpha") || !strings.Contains(view, ": ") {
		t.Fatalf("composer should show receiver name: %q", view)
	}
	if !strings.Contains(view, "type message") {
		t.Fatalf("composer = %q", view)
	}
	if strings.Index(view, "█") > strings.Index(view, "type message") {
		t.Fatalf("cursor should appear before placeholder: %q", view)
	}
}

func TestAdvancedViewUsesAgentListAndConversationPanels(t *testing.T) {
	m := model{mode: advancedView, width: 100, height: 20, rows: []agentRow{{Name: "alpha", Scope: "local"}}, allMessages: []tracker.Message{{Sender: "beta", Body: "hello"}}}
	view := m.View()
	for _, want := range []string{"Agents", "Conversation", "alpha", "hello"} {
		if !strings.Contains(view, want) {
			t.Fatalf("advanced view missing %q:\n%s", want, view)
		}
	}
	if strings.Contains(view, "Simple View") || strings.Contains(view, "Advanced View") {
		t.Fatalf("advanced view should not show old mode heading:\n%s", view)
	}
}

func TestAdvancedViewAggregatesInboundAndSentMessages(t *testing.T) {
	m := model{mode: advancedView, width: 100, height: 20, ownName: "agent-communicator", rows: []agentRow{{Name: "alpha", TargetAddress: "alpha"}}, sentMessages: map[string][]tracker.Message{
		"alpha": {{Sender: "You", Body: "out", Timestamp: "2026-05-19T12:01:00Z"}},
	}}
	m.allMessages = m.mergeAllMessages([]tracker.Message{{Sender: "beta", Body: "in", Timestamp: "2026-05-19T12:00:00Z"}})
	view := m.messageView(100)
	for _, want := range []string{"beta → agent-communicator", "to alpha", "in", "out"} {
		if !strings.Contains(view, want) {
			t.Fatalf("advanced view missing %q:\n%s", want, view)
		}
	}
}
