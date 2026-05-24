package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestIncomingEventHighlightsAgentListRow(t *testing.T) {
	m := model{ownName: "coding-agent", rows: []agentRow{{Name: "alice", Scope: "local"}}}
	m.markUnreadFromEvents(tracker.WaitEventsResult{Events: []tracker.Event{{TargetAgentName: "coding-agent", Sender: "alice"}}})
	if !m.hasUnread(m.rows[0]) {
		t.Fatal("incoming event did not mark row unread")
	}
	if view := m.agentList(40, 10); !strings.Contains(view, "●") {
		t.Fatalf("agent list missing unread badge:\n%s", view)
	}
}

func TestSendingMessageClearsUnreadForRow(t *testing.T) {
	row := agentRow{Name: "alice", Scope: "local"}
	m := model{unreadRows: map[string]bool{conversationKey(row): true}}
	m.clearUnread(row)
	if m.hasUnread(row) {
		t.Fatal("send should clear unread highlight")
	}
}

func TestCtrlAClearsUnreadForSelectedConversation(t *testing.T) {
	row := agentRow{Name: "alice", Scope: "local"}
	m := model{rows: []agentRow{row}, unreadRows: map[string]bool{conversationKey(row): true}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlA})
	if cmd != nil {
		t.Fatal("ack should not send or reload")
	}
	if updated.(model).hasUnread(row) {
		t.Fatal("ctrl-a should clear unread highlight")
	}
}

func TestRemoteIncomingEventHighlightsMatchingHostRow(t *testing.T) {
	row := agentRow{Name: "dawns/alice", Scope: "remote", Hostname: "dawnstar", AgentName: "alice", TargetAddress: "dawnstar/alice"}
	m := model{ownName: "coding-agent", rows: []agentRow{row}}
	m.markUnreadFromEvents(tracker.WaitEventsResult{Events: []tracker.Event{{TargetAgentName: "coding-agent", Sender: "alice (via dawnstar)"}}})
	if !m.hasUnread(row) {
		t.Fatal("remote incoming event did not mark row unread")
	}
}
