package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestIncomingEventHighlightsAgentListRow(t *testing.T) {
	m := model{ownName: "coding-agent", selected: 1, rows: []agentRow{{Name: "alice", Scope: "local"}, {Name: "bob", Scope: "local"}}}
	m.markUnreadFromEvents(tracker.WaitEventsResult{Events: []tracker.Event{{TargetAgentName: "coding-agent", Sender: "alice"}}})
	if !m.hasUnread(m.rows[0]) {
		t.Fatal("incoming event did not mark row unread")
	}
	if view := m.agentList(40, 10); !strings.Contains(view, "1") {
		t.Fatalf("agent list missing unread count badge:\n%s", view)
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

func TestUnreadCountsUseStableLocalAndRemoteKeys(t *testing.T) {
	local := agentRow{Name: "alice", Scope: "local", AgentID: "same-id"}
	remote := agentRow{Name: "host/alice", Scope: "remote", AgentID: "same-id", TrackerID: "remote-tracker", Hostname: "host", AgentName: "alice", TargetAddress: "host/alice"}
	m := model{unreadCounts: map[string]int{
		conversationKey(local):  2,
		conversationKey(remote): 3,
	}}
	if got := m.unreadCount(local); got != 2 {
		t.Fatalf("local unread count = %d, want 2", got)
	}
	if got := m.unreadCount(remote); got != 3 {
		t.Fatalf("remote unread count = %d, want 3", got)
	}
}

func TestNextUnreadSelectsNextCountBadgeWithoutChangingCtrlN(t *testing.T) {
	rows := []agentRow{{Name: "alpha", Scope: "local", AgentID: "a"}, {Name: "beta", Scope: "local", AgentID: "b"}, {Name: "gamma", Scope: "local", AgentID: "c"}}
	m := model{rows: rows, selected: 0, unreadCounts: map[string]int{conversationKey(rows[2]): 1}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}})
	if got := updated.(model).selected; got != 2 {
		t.Fatalf("n selected row %d, want 2", got)
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	if got := updated.(model).selected; got != 1 {
		t.Fatalf("ctrl-n selected row %d, want 1", got)
	}
}
