package main

import (
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var systemEventTypes = map[string]bool{
	"agent_registered":     true,
	"agent_unregistered":   true,
	"agent_status_changed": true,
	"message_delivered":    true,
	"message_read":         true,
	"remote_agent_event":   true,
}

func isSystemEvent(event tracker.Event) bool {
	return systemEventTypes[event.Type]
}

func (m *model) appendSystemEvents(result tracker.WaitEventsResult) {
	for _, event := range result.Events {
		if isSystemEvent(event) {
			m.systemEvents = append(m.systemEvents, event)
		}
	}
	if len(m.systemEvents) > 100 {
		m.systemEvents = append([]tracker.Event(nil), m.systemEvents[len(m.systemEvents)-100:]...)
	}
}

func (m model) displayOrderedSystemEvents() []tracker.Event {
	if m.mode != advancedView || len(m.systemEvents) == 0 {
		return nil
	}
	return m.systemEvents
}

func systemEventMatchesRow(event tracker.Event, row agentRow) bool {
	if event.TargetAgentID != "" && row.AgentID != "" && event.TargetAgentID == row.AgentID {
		if row.Scope == "remote" {
			return row.TrackerID == "" || event.TrackerID == "" || event.TrackerID == row.TrackerID
		}
		return event.TrackerID == "" || row.TrackerID == "" || event.TrackerID == row.TrackerID
	}
	name := event.TargetAgentName
	return name != "" && rowKeyMatchesSenderString(row, name)
}

func (m model) systemEventLine(event tracker.Event, width int) string {
	label := systemEventLabel(event)
	if label == "" {
		return ""
	}
	if event.Timestamp > 0 {
		label += " · " + time.Unix(int64(event.Timestamp), 0).In(displayLocation).Format("15:04")
	}
	inner := truncateCells(label, max(1, width-8))
	lineWidth := max(0, width-lipgloss.Width(inner)-2)
	left := strings.Repeat("╌", lineWidth/2)
	right := strings.Repeat("╌", lineWidth-lineWidth/2)
	return mutedStyle.Render(left + " " + inner + " " + right)
}

func systemEventLabel(event tracker.Event) string {
	name := fallback(event.TargetAgentName, event.Sender)
	switch event.Type {
	case "agent_registered":
		return fmt.Sprintf("%s joined", fallback(name, "agent"))
	case "agent_unregistered":
		return fmt.Sprintf("%s left", fallback(name, "agent"))
	case "agent_status_changed":
		if event.OldStatus != "" && event.Status != "" {
			return fmt.Sprintf("%s status %s → %s", fallback(name, "agent"), event.OldStatus, event.Status)
		}
		return fmt.Sprintf("%s status %s", fallback(name, "agent"), fallback(event.Status, "changed"))
	case "message_delivered":
		return fmt.Sprintf("message delivered to %s", fallback(name, "agent"))
	case "message_read":
		return fmt.Sprintf("message read by %s", fallback(name, "agent"))
	case "remote_agent_event":
		if event.Message != "" {
			return event.Message
		}
		return fmt.Sprintf("remote activity from %s", fallback(name, "agent"))
	default:
		return ""
	}
}
