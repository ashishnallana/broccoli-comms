package main

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

var titleStyle = lipgloss.NewStyle().Bold(true).Foreground(palette.Sky)
var selectedStyle = lipgloss.NewStyle().Foreground(palette.Green).Bold(true)
var mutedStyle = lipgloss.NewStyle().Foreground(palette.Overlay0)
var readStatusStyle = lipgloss.NewStyle().Foreground(palette.Blue)
var shellTitleStyle = lipgloss.NewStyle().Bold(true).Foreground(palette.Mauve)
var sectionHeaderStyle = lipgloss.NewStyle().Foreground(palette.Subtext0).Bold(true)
var badgeStyle = lipgloss.NewStyle().Foreground(palette.Base).Background(palette.Blue).Bold(true).Padding(0, 1)
var modeTabStyle = lipgloss.NewStyle().Foreground(palette.Subtext0).Border(lipgloss.RoundedBorder()).BorderForeground(palette.Surface0).Padding(0, 1)
var activeModeTabStyle = lipgloss.NewStyle().Foreground(palette.Base).Background(palette.Green).Border(lipgloss.RoundedBorder()).BorderForeground(palette.Green).Bold(true).Padding(0, 1)
var statusBarStyle = lipgloss.NewStyle().Foreground(palette.Teal)
var errorBarStyle = lipgloss.NewStyle().Foreground(palette.Red).Bold(true)
var unreadCountStyle = lipgloss.NewStyle().Foreground(palette.Base).Background(palette.Yellow).Bold(true).Padding(0, 1)

func statusDot(status string) string {
	return statusDotStyle(status).Render("●")
}

func statusDotStyle(status string) lipgloss.Style {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "running", "active", "online", "idle", "ready":
		return lipgloss.NewStyle().Foreground(palette.Green)
	case "waiting", "pending", "paused":
		return lipgloss.NewStyle().Foreground(palette.Yellow)
	case "error", "failed", "stopped", "offline", "dead":
		return lipgloss.NewStyle().Foreground(palette.Red)
	default:
		return lipgloss.NewStyle().Foreground(palette.Overlay0)
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
	style := lipgloss.NewStyle().Foreground(palette.AgentColors[agentColorIndex(name)])
	if bold {
		style = style.Bold(true)
	}
	return style
}

func (m model) agentRowStyle(row agentRow, selected bool) lipgloss.Style {
	style := agentStyle(row.Name, selected || m.hasUnread(row))
	if m.hasUnread(row) && !selected {
		style = style.Background(palette.Surface0).Foreground(palette.Text)
	}
	return style
}

func agentColorIndex(name string) int {
	if name == "" {
		return 0
	}
	h := 0
	for _, r := range name {
		h = (h*31 + int(r)) % len(palette.AgentColors)
	}
	return h
}

func lineCount(s string) int {
	if s == "" {
		return 0
	}
	return strings.Count(s, "\n") + 1
}
