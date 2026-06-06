package main

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type swarmRow struct {
	Name        string
	Main        agentRow
	Members     []agentRow
	MainMissing bool
	Warning     string
}

func loadSwarms(local localClient) tea.Cmd {
	return func() tea.Msg {
		if local == nil {
			return swarmsLoaded{}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		result, err := local.ListSwarms(ctx)
		return swarmsLoaded{Rows: swarmRowsFromTracker(result.Swarms), Err: err}
	}
}

func loadSelectedSwarmTimeline(local localClient, swarmName string) tea.Cmd {
	return func() tea.Msg {
		if local == nil || strings.TrimSpace(swarmName) == "" {
			return swarmTimelineLoaded{Swarm: swarmName}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		result, err := local.GetSwarmTimeline(ctx, swarmName, advancedInboxFetchLimit)
		return swarmTimelineLoaded{Swarm: swarmName, Messages: result.Messages, Err: err}
	}
}

func swarmRowsFromTracker(swarms []tracker.Swarm) []swarmRow {
	rows := make([]swarmRow, 0, len(swarms))
	for _, swarm := range swarms {
		row := swarmRow{Name: swarm.Name, Warning: strings.Join(swarm.Warnings, " · ")}
		row.Main = swarmMemberToAgentRow(swarm.Main)
		row.MainMissing = row.Main.Name == ""
		for _, member := range swarm.Members {
			row.Members = append(row.Members, swarmMemberToAgentRow(member))
		}
		if row.MainMissing && row.Warning == "" {
			row.Warning = "No main agent configured/running"
		}
		rows = append(rows, row)
	}
	return rows
}

func swarmMemberToAgentRow(member tracker.SwarmMember) agentRow {
	name := fallback(member.Name, member.AgentName)
	return agentRow{
		Name:          name,
		AgentName:     fallback(member.AgentName, name),
		TargetAddress: fallback(member.TargetAddress, name),
		Scope:         fallback(member.Scope, "local"),
		Status:        member.Status,
		Hostname:      member.Hostname,
		AgentID:       member.AgentID,
		TrackerID:     member.TrackerID,
		RegistryName:  member.RegistryName,
		ModelType:     member.ModelType,
		AgentType:     member.AgentType,
		AgentCmd:      member.AgentCmd,
	}
}

func (m model) selectedSwarmRow() (swarmRow, bool) {
	if len(m.swarms) == 0 || m.selectedSwarm < 0 || m.selectedSwarm >= len(m.swarms) {
		return swarmRow{}, false
	}
	return m.swarms[m.selectedSwarm], true
}

func (m model) selectedSwarmName() string {
	if swarm, ok := m.selectedSwarmRow(); ok {
		return swarm.Name
	}
	return ""
}

func (m *model) clampSelectedSwarm() {
	if m.selectedSwarm >= len(m.swarms) {
		m.selectedSwarm = max(0, len(m.swarms)-1)
	}
	if m.selectedSwarm < 0 {
		m.selectedSwarm = 0
	}
}

func (m *model) selectSwarm(delta int) {
	if len(m.swarms) == 0 {
		m.selectedSwarm = 0
		return
	}
	m.selectedSwarm = (m.selectedSwarm + delta + len(m.swarms)) % len(m.swarms)
	m.swarmMessages = nil
	m.selectLatestMessage()
}

func (m model) swarmLines(width int) []string {
	width = max(1, width)
	if len(m.swarms) == 0 {
		return m.swarmEmptyLines(width)
	}
	swarm, _ := m.selectedSwarmRow()
	lines := []string{fgOnBg(colors.Accent, colors.BaseBg).Bold(true).Render("Swarm " + swarm.Name)}
	if swarm.Warning != "" {
		lines = append(lines, wrapBackgroundStyledText("warning · "+swarm.Warning, width, colors.Warning, colors.BaseBg)...)
	}
	if swarm.MainMissing {
		lines = append(lines, wrapBackgroundStyledText("No main agent configured/running. Swarm messaging will be enabled after a main agent is available.", width, colors.Warning, colors.BaseBg)...)
	} else {
		lines = append(lines, wrapBackgroundStyledText("main · "+swarm.Main.Name, width, colors.TextSubtle, colors.BaseBg)...)
	}
	messages := m.swarmDisplayMessages()
	if len(messages) == 0 {
		lines = append(lines, "", mutedStyle.Render("No swarm timeline messages yet."))
		return lines
	}
	lines = append(lines, "")
	for i, msg := range messages {
		if i > 0 {
			lines = append(lines, bgSpaces(width, colors.BaseBg))
		}
		lines = append(lines, m.messageBubbleLines(msg.Message, i, width)...)
	}
	return lines
}

func (m model) swarmDisplayMessages() []swarmDisplayMessage {
	messages := make([]swarmDisplayMessage, 0, len(m.swarmMessages))
	seen := map[string]bool{}
	for _, msg := range m.swarmMessages {
		body := msg.Body
		if body == "" {
			body = msg.Message
		}
		label := strings.TrimSpace(msg.Sender)
		if msg.Recipient != "" {
			label = strings.TrimSpace(label + " → " + msg.Recipient)
		}
		if msg.MessageID != "" {
			seen[msg.MessageID] = true
		}
		messages = append(messages, swarmDisplayMessage{ID: msg.MessageID, Message: tracker.Message{Sender: label, Body: body, Timestamp: msg.Timestamp, ContentType: msg.ContentType, MessageID: msg.MessageID}})
	}
	swarm, ok := m.selectedSwarmRow()
	if !ok || swarm.MainMissing || rowTarget(swarm.Main) == "" {
		return messages
	}
	appendSent := func(msg tracker.Message) {
		if msg.MessageID != "" && seen[msg.MessageID] {
			return
		}
		if msg.MessageID != "" {
			seen[msg.MessageID] = true
		}
		messages = append(messages, swarmDisplayMessage{ID: msg.MessageID, Message: tracker.Message{Sender: "You → " + swarm.Main.Name, Body: msg.Body, Timestamp: msg.Timestamp, ContentType: msg.ContentType, MessageID: msg.MessageID, Delivered: msg.Delivered, Notified: msg.Notified, Read: msg.Read}})
	}
	for _, msg := range m.sentMessages[conversationKey(swarm.Main)] {
		appendSent(msg)
	}
	for _, rec := range m.outbox {
		if outboxRecordMatchesRow(rec, swarm.Main) {
			appendSent(outboxMessage(rec, false))
		}
	}
	sort.SliceStable(messages, func(i, j int) bool {
		ti, okI := parseMessageTime(messages[i].Message.Timestamp)
		tj, okJ := parseMessageTime(messages[j].Message.Timestamp)
		if !okI || !okJ || ti.Equal(tj) {
			return false
		}
		return ti.After(tj)
	})
	return messages
}

type swarmDisplayMessage struct {
	ID      string
	Message tracker.Message
}

func (m model) swarmEmptyLines(width int) []string {
	lines := []string{}
	if m.swarmErr != nil {
		lines = append(lines, wrapBackgroundStyledText("Swarm API unavailable: "+m.swarmErr.Error(), width, colors.Warning, colors.BaseBg)...)
	}
	text := []string{
		"No swarms found.",
		"Start agents with swarm metadata, for example:",
		"broccoli-comms track --name planner --swarm backend-fix --role main -- pi",
		"broccoli-comms track --name coder-a --swarm backend-fix --role subagent -- pi",
		"or persist them with broccoli-comms agent add ... --swarm backend-fix --role main",
	}
	for _, line := range text {
		lines = append(lines, wrapBackgroundStyledText(line, width, colors.Muted, colors.BaseBg)...)
	}
	return lines
}

func (m model) swarmSidebarView(width, height int) string {
	currentH := min(8, max(5, height/3))
	current := m.swarmCurrentPanel(width, currentH)
	list := m.swarmListPanel(width, max(1, height-currentH))
	return lipgloss.JoinVertical(lipgloss.Left, current, list)
}

func (m model) swarmCurrentPanel(width, height int) string {
	title := shellTitleStyle.Render("Swarm Mode")
	body := title
	if swarm, ok := m.selectedSwarmRow(); ok {
		main := "missing main"
		if !swarm.MainMissing {
			main = swarm.Main.Name
		}
		body += "\n" + fgOnBg(colors.SelectedFg, colors.SelectedBg).Bold(true).Render(truncateCells(swarm.Name, max(1, width-4)))
		body += "\n" + mutedStyle.Render(truncateCells("main · "+main, max(1, width-4)))
		body += "\n" + mutedStyle.Render(fmt.Sprintf("members · %d", len(swarm.Members)))
		if swarm.Warning != "" {
			body += "\n" + fgOnBg(colors.Warning, colors.RightColumnBg).Render(truncateCells(swarm.Warning, max(1, width-4)))
		}
	} else {
		body += "\n" + mutedStyle.Render("no swarms")
	}
	return lipgloss.NewStyle().Width(width).Height(height).Padding(1, 1).Background(colors.RightColumnBg).Render(truncateLines(body, max(1, height-1)))
}

func (m model) swarmListPanel(width, height int) string {
	header := fgOnBg(colors.Accent, colors.RightColumnBg).Bold(true).Render("Swarms")
	var lines []string
	if len(m.swarms) == 0 {
		lines = append(lines, mutedStyle.Render("no swarms"), mutedStyle.Render("use --swarm and --role"))
	} else {
		for i, swarm := range m.swarms {
			bg := colors.RightColumnBg
			fg := colors.Text
			prefix := "  "
			if i == m.selectedSwarm {
				bg = colors.SelectedBg
				fg = colors.SelectedFg
				prefix = "> "
			}
			lines = append(lines, fgOnBg(fg, bg).Bold(i == m.selectedSwarm).Render(truncateCells(prefix+swarm.Name, max(1, width-4))))
			main := "main missing"
			if !swarm.MainMissing {
				main = "main " + swarm.Main.Name
			}
			lines = append(lines, fgOnBg(colors.Muted, bg).Render(truncateCells("  "+main, max(1, width-4))))
		}
	}
	if swarm, ok := m.selectedSwarmRow(); ok && len(swarm.Members) > 0 {
		lines = append(lines, "", sectionHeaderStyle.Render("Members"))
		for _, member := range swarm.Members {
			role := "subagent"
			if member.Name == swarm.Main.Name && !swarm.MainMissing {
				role = "main"
			}
			lines = append(lines, mutedStyle.Render(truncateCells("• "+member.Name+" · "+role, max(1, width-4))))
		}
	}
	body := header + "\n" + strings.Join(lines, "\n")
	return lipgloss.NewStyle().Width(width).Height(height).Padding(1, 1).Background(colors.RightColumnBg).Render(truncateLines(body, max(1, height-1)))
}
