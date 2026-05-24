package main

import (
	"fmt"
	"os/exec"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type paneSwitched struct{ Err error }

func switchToAgentPane(row agentRow) tea.Cmd {
	return func() tea.Msg {
		if row.Scope != "local" {
			return paneSwitched{Err: fmt.Errorf("cannot switch to remote agent %s", row.Name)}
		}
		if row.TmuxPane == "" {
			return paneSwitched{Err: fmt.Errorf("agent %s has no tmux pane", row.Name)}
		}
		return paneSwitched{Err: exec.Command("tmux", "switch-client", "-t", row.TmuxPane).Run()}
	}
}

func messageIDExists(messages []tracker.Message, id string) bool {
	if id == "" {
		return false
	}
	for _, msg := range messages {
		if msg.MessageID == id {
			return true
		}
	}
	return false
}

func (m *model) applyStatusEvents(result tracker.WaitEventsResult) {
	changed := false
	for _, event := range result.Events {
		if event.Sender != m.ownName || event.MessageID == "" {
			continue
		}
		for i := range m.outbox {
			if m.outbox[i].ID != event.MessageID {
				continue
			}
			switch event.Type {
			case "message_delivered":
				if !m.outbox[i].Delivered {
					m.outbox[i].Delivered = true
					changed = true
				}
			case "message_notified":
				if !m.outbox[i].Notified {
					m.outbox[i].Delivered = true
					m.outbox[i].Notified = true
					changed = true
				}
			case "message_read":
				if !m.outbox[i].Read {
					m.outbox[i].Delivered = true
					m.outbox[i].Notified = true
					m.outbox[i].Read = true
					changed = true
				}
			}
		}
	}
	if changed {
		if err := writeOutbox(m.outbox); err != nil {
			m.err = err
		}
		m.refreshMergedMessages()
	}
}

func appendOrReplaceOutbox(records []outboxRecord, rec outboxRecord) []outboxRecord {
	for i, existing := range records {
		if existing.ID == rec.ID {
			records[i] = rec
			return records
		}
	}
	return append(records, rec)
}
