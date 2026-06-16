package main

import "github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"

func (m *model) markUnreadFromEvents(result tracker.WaitEventsResult) {
	if m.ownName == "" {
		return
	}
	for _, event := range result.Events {
		if !eventCountsAsUnread(event) || event.TargetAgentName != m.ownName || event.Sender == "" || event.Sender == m.ownName {
			continue
		}
		for _, row := range m.rows {
			if senderMatchesRow(event.Sender, row) {
				m.markUnread(row)
			}
		}
	}
}

func eventCountsAsUnread(event tracker.Event) bool {
	if event.Type != "message_delivered" && event.Type != "message_notified" {
		return false
	}
	return event.ContentType != taskUpdateContentType && event.Kind != "task_update" && event.Kind != "task_status_changed"
}

func (m *model) markUnread(row agentRow) {
	if m.unreadRows == nil {
		m.unreadRows = map[string]bool{}
	}
	m.unreadRows[conversationKey(row)] = true
}

func (m *model) clearUnread(row agentRow) {
	key := conversationKey(row)
	if m.unreadRows != nil {
		delete(m.unreadRows, key)
	}
	if m.unreadCounts != nil {
		delete(m.unreadCounts, key)
		for _, fallbackKey := range rowUnreadFallbackKeys(row) {
			delete(m.unreadCounts, fallbackKey)
		}
	}
}

func (m model) hasUnread(row agentRow) bool {
	return m.unreadCount(row) > 0
}

func (m model) unreadCount(row agentRow) int {
	key := conversationKey(row)
	if m.unreadCounts != nil {
		if count := m.unreadCounts[key]; count > 0 {
			return count
		}
		for _, fallbackKey := range rowUnreadFallbackKeys(row) {
			if count := m.unreadCounts[fallbackKey]; count > 0 {
				return count
			}
		}
	}
	if m.unreadRows != nil && m.unreadRows[key] {
		return 1
	}
	return 0
}

func rowUnreadFallbackKeys(row agentRow) []string {
	keys := []string{}
	for _, value := range []string{row.Name, row.AgentName, rowTarget(row)} {
		if value != "" {
			keys = append(keys, "sender:"+value)
		}
	}
	return keys
}

func (m *model) selectNextUnread() bool {
	if len(m.rows) == 0 {
		return false
	}
	start := m.selected
	if start < 0 || start >= len(m.rows) {
		start = 0
	}
	for offset := 1; offset <= len(m.rows); offset++ {
		idx := (start + offset) % len(m.rows)
		if m.hasUnread(m.rows[idx]) {
			m.selected = idx
			return true
		}
	}
	return false
}
