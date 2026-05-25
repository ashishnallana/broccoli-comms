package main

import (
	"strings"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func (m *model) syncAdvancedTargetToSelection() {
	if m.mode != advancedView || len(m.rows) == 0 {
		return
	}
	messages := m.displayOrderedMessages()
	if m.messageSelected < 0 || m.messageSelected >= len(messages) {
		return
	}
	if idx := m.rowIndexForMessageTarget(messages[m.messageSelected]); idx >= 0 {
		m.selected = idx
	}
}

func (m model) rowIndexForMessageTarget(msg tracker.Message) int {
	for i, row := range m.rows {
		if messageMatchesRowByID(msg, row) {
			return i
		}
	}
	sender := strings.TrimSpace(msg.Sender)
	if sender == "" {
		return -1
	}
	if strings.Contains(sender, "→") {
		parts := strings.Split(sender, "→")
		sender = strings.TrimSpace(parts[len(parts)-1])
	}
	if strings.HasPrefix(sender, "to ") {
		sender = strings.TrimSpace(strings.TrimPrefix(sender, "to "))
	}
	for i, row := range m.rows {
		if rowKeyMatchesSenderString(row, sender) {
			return i
		}
	}
	return -1
}
