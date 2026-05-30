package main

import (
	"strings"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type AgentView struct {
	Row          agentRow
	Name         string
	Scope        string
	Status       string
	StatusLabel  string
	ModelBadge   string
	MachineLabel string
	GroupHeader  string
	CWD          string
	Hidden       bool
	Unread       bool
}

type MachineGroup struct {
	Header string
	Hidden bool
	Agents []AgentView
}

type MessageView struct {
	Message tracker.Message
	Sender  string
	Sent    bool
	Saved   bool
}

type UIError struct {
	Message   string
	Operation string
	Retryable bool
}

func newAgentView(row agentRow, hidden, unread bool) AgentView {
	machine := rowMachineLabel(row)
	scope := strings.Title(fallback(row.Scope, "local"))
	group := scope
	if machine != "" {
		group += " · " + machine
	}
	return AgentView{
		Row:          row,
		Name:         row.Name,
		Scope:        fallback(row.Scope, "local"),
		Status:       row.Status,
		StatusLabel:  statusLabel(row.Status),
		ModelBadge:   modelBadge(row),
		MachineLabel: machine,
		GroupHeader:  group,
		CWD:          compactCWD(row.CWD),
		Hidden:       hidden,
		Unread:       unread,
	}
}

func deriveAgentViews(rows []agentRow, hiddenFn func(agentRow) bool, unreadFn func(agentRow) bool) []AgentView {
	views := make([]AgentView, 0, len(rows))
	for _, row := range rows {
		hidden := hiddenFn != nil && hiddenFn(row)
		unread := unreadFn != nil && unreadFn(row)
		views = append(views, newAgentView(row, hidden, unread))
	}
	return views
}

func groupAgentViews(views []AgentView) []MachineGroup {
	groups := []MachineGroup{}
	for _, view := range views {
		if len(groups) == 0 || groups[len(groups)-1].Header != view.GroupHeader || groups[len(groups)-1].Hidden != view.Hidden {
			groups = append(groups, MachineGroup{Header: view.GroupHeader, Hidden: view.Hidden})
		}
		groups[len(groups)-1].Agents = append(groups[len(groups)-1].Agents, view)
	}
	return groups
}

func hiddenAgentCount(rows []agentRow, hiddenFn func(agentRow) bool) int {
	if hiddenFn == nil {
		return 0
	}
	count := 0
	for _, row := range rows {
		if hiddenFn(row) {
			count++
		}
	}
	return count
}

func (m model) agentView(row agentRow) AgentView {
	return newAgentView(row, m.isHiddenAgent(row), m.hasUnread(row))
}

func (m model) agentViews() []AgentView {
	return deriveAgentViews(m.rows, m.isHiddenAgent, m.hasUnread)
}

func (m model) hiddenCount() int {
	return hiddenAgentCount(m.rows, m.isHiddenAgent)
}

func messageViewFromMessage(msg tracker.Message, saved bool) MessageView {
	return MessageView{Message: msg, Sender: fallback(msg.Sender, "unknown"), Sent: isSentMessage(msg), Saved: saved}
}

func splitHost(target string) string {
	host, _ := splitRemoteTarget(target)
	return host
}

func rowMachineLabel(row agentRow) string {
	if row.Hostname != "" {
		return shortHost(row.Hostname)
	}
	if host := splitHost(row.TargetAddress); host != "" {
		return shortHost(host)
	}
	if row.Scope == "remote" {
		return "remote"
	}
	return shortHost(localHostname())
}

func modelBadge(row agentRow) string {
	modelType := strings.ToLower(strings.TrimSpace(row.ModelType))
	if modelType == "" || modelType == "unknown" {
		modelType = inferredModelType(row.AgentCmd)
	}
	switch modelType {
	case "claude":
		return "Cl"
	case "codex":
		return "Cx"
	case "pi":
		return "Pi"
	default:
		return "??"
	}
}

func inferredModelType(agentCmd string) string {
	cmd := strings.ToLower(strings.TrimSpace(agentCmd))
	switch {
	case strings.Contains(cmd, "claude"):
		return "claude"
	case strings.Contains(cmd, "codex"):
		return "codex"
	case strings.Contains(cmd, "pi"):
		return "pi"
	default:
		return "unknown"
	}
}

func statusLabel(status string) string {
	return fallback(strings.TrimSpace(status), "unknown")
}

func nonEmpty(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			out = append(out, value)
		}
	}
	return out
}
