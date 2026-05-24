package main

import "github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"

func (m *model) markUnreadFromEvents(result tracker.WaitEventsResult) {
	if m.ownName == "" {
		return
	}
	for _, event := range result.Events {
		if event.TargetAgentName != m.ownName || event.Sender == "" || event.Sender == m.ownName {
			continue
		}
		for _, row := range m.rows {
			if senderMatchesRow(event.Sender, row) {
				m.markUnread(row)
			}
		}
	}
}

func (m *model) markUnread(row agentRow) {
	if m.unreadRows == nil {
		m.unreadRows = map[string]bool{}
	}
	m.unreadRows[conversationKey(row)] = true
}

func (m *model) clearUnread(row agentRow) {
	if m.unreadRows != nil {
		delete(m.unreadRows, conversationKey(row))
	}
}

func (m model) hasUnread(row agentRow) bool {
	return m.unreadRows != nil && m.unreadRows[conversationKey(row)]
}
