package main

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

var titleStyle = lipgloss.NewStyle().Bold(true).Foreground(colors.Accent)
var selectedStyle = lipgloss.NewStyle().Foreground(colors.Success).Bold(true)
var mutedStyle = lipgloss.NewStyle().Foreground(colors.Muted)
var readStatusStyle = lipgloss.NewStyle().Foreground(colors.ReadTick)
var shellTitleStyle = lipgloss.NewStyle().Bold(true).Foreground(colors.AccentAlt)
var sectionHeaderStyle = lipgloss.NewStyle().Foreground(colors.TextSubtle).Bold(true)
var badgeStyle = lipgloss.NewStyle().Foreground(colors.BadgeFg).Background(colors.BadgeBg).Bold(true).Padding(0, 1)
var modeTabStyle = lipgloss.NewStyle().Foreground(colors.TextSubtle).Border(lipgloss.RoundedBorder()).BorderForeground(colors.Border).Padding(0, 1)
var activeModeTabStyle = lipgloss.NewStyle().Foreground(colors.SelectedFg).Background(colors.Success).Border(lipgloss.RoundedBorder()).BorderForeground(colors.Success).Bold(true).Padding(0, 1)
var statusBarStyle = lipgloss.NewStyle().Foreground(colors.Accent)
var errorBarStyle = lipgloss.NewStyle().Foreground(colors.Error).Bold(true)
var unreadCountStyle = lipgloss.NewStyle().Foreground(colors.SelectedFg).Background(colors.Warning).Bold(true).Padding(0, 1)

func statusDot(status string) string {
	return statusDotStyle(status).Render("●")
}

func agentStatusDot(row agentRow) string {
	return agentStatusDotStyle(row).Render("●")
}

func agentStatusDotStyle(row agentRow) lipgloss.Style {
	if detectionBlocked(row.Detection) {
		return lipgloss.NewStyle().Foreground(colors.Error)
	}
	return statusDotStyle(row.Status)
}

func statusDotStyle(status string) lipgloss.Style {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "running", "active", "online", "idle", "ready":
		return lipgloss.NewStyle().Foreground(colors.Success)
	case "waiting", "pending", "paused":
		return lipgloss.NewStyle().Foreground(colors.Warning)
	case "error", "failed", "stopped", "offline", "dead":
		return lipgloss.NewStyle().Foreground(colors.Error)
	default:
		return lipgloss.NewStyle().Foreground(colors.Muted)
	}
}

func senderColorKey(sender string) string {
	if strings.Contains(sender, "→") {
		return strings.TrimSpace(strings.SplitN(sender, "→", 2)[0])
	}
	return strings.TrimSpace(sender)
}

func unreadCountBadge(count int) string {
	if count > 99 {
		return unreadCountStyle.Render("99+")
	}
	return unreadCountStyle.Render(fmt.Sprintf("%d", count))
}

func agentStyle(name string, bold bool) lipgloss.Style {
	style := lipgloss.NewStyle().Foreground(colors.AgentColors[agentColorIndex(name)])
	if bold {
		style = style.Bold(true)
	}
	return style
}

func (m model) agentRowStyle(row agentRow, selected bool) lipgloss.Style {
	style := agentStyle(row.Name, selected || m.hasUnread(row))
	if m.hasUnread(row) && !selected {
		style = style.Background(colors.PanelBgAlt).Foreground(colors.Text)
	}
	return style
}

func agentColorIndex(name string) int {
	if name == "" {
		return 0
	}
	h := 0
	for _, r := range name {
		h = (h*31 + int(r)) % len(colors.AgentColors)
	}
	return h
}

func lineCount(s string) int {
	if s == "" {
		return 0
	}
	return strings.Count(s, "\n") + 1
}
