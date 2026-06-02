package main

import (
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var bubbleBorder = lipgloss.RoundedBorder()

func (m model) messageBubbleLines(msg tracker.Message, index, width int) []string {
	start := time.Now()
	defer func() {
		debugLogf("message_bubble duration=%s index=%d body_bytes=%d markdown=%t", time.Since(start), index, len(msg.Body), msg.ContentType == "" || msg.ContentType == "text/markdown")
	}()
	colorKey := m.messageColorKey(msg)
	body := msg.Body
	innerWidth := max(8, width-8)
	if msg.ContentType == "" || msg.ContentType == "text/markdown" {
		body = renderMarkdown(body, innerWidth)
	}
	rail := mutedStyle.Render("┃")
	if index == m.messageSelected {
		rail = lipgloss.NewStyle().Foreground(colors.Accent).Bold(true).Render("┃")
	}
	header := agentStyle(colorKey, true).Render(m.messageHeader(msg, index, colorKey, innerWidth))
	out := []string{rail + "  " + header}
	for _, line := range m.visibleBodyLines(bubbleBodyLines(body, innerWidth), index) {
		line = truncateCells(line, innerWidth)
		if !isSentMessage(msg) && width >= 70 {
			line = lipgloss.NewStyle().Background(colors.PanelBgAlt).Padding(0, 1).Render(line)
		}
		out = append(out, rail+"  "+line)
	}
	if receipt := sentReceiptLine(msg); receipt != "" {
		out = append(out, rail+"  "+receipt)
	}
	return out
}

func (m model) messageHeader(msg tracker.Message, index int, colorKey string, width int) string {
	sender := fallback(msg.Sender, "unknown")
	if m.mode == advancedView && !strings.Contains(sender, "→") && !strings.HasPrefix(sender, "to ") {
		sender += " → " + fallback(m.ownName, "agent-communicator")
	}
	saved := ""
	if m.isSavedMessage(msg) {
		saved = lipgloss.NewStyle().Foreground(colors.Saved).Render("★ ")
	}
	label := messageSenderLabel(msg, sender)
	header := saved + truncateCells(label, max(1, width-25))
	if ts := formatDisplayTime(msg.Timestamp); ts != "" && lipgloss.Width(header)+1 < width {
		if m.isSavedMessage(msg) {
			ts += " ★"
		}
		header += " " + mutedStyle.Render(truncateCells(ts, width-lipgloss.Width(header)-1))
	}
	return header
}

func messageSenderLabel(msg tracker.Message, fallbackSender string) string {
	if isSentMessage(msg) {
		return fallbackSender
	}
	parts := []string{}
	if badge := messageSenderBadge(msg); badge != "??" {
		parts = append(parts, badge)
	}
	parts = append(parts, fallback(fallbackSender, "unknown"))
	if host := strings.TrimSpace(msg.SenderHostname); host != "" {
		parts = append(parts, "@ "+shortHost(host))
	}
	return strings.Join(parts, " ")
}

func messageSenderBadge(msg tracker.Message) string {
	return modelBadge(agentRow{ModelType: msg.SenderModelType, AgentCmd: fallback(msg.SenderAgentCmd, msg.SenderAgentType)})
}

func renderBubble(lines []string, innerWidth int, color lipgloss.Color, outgoing, selected bool) []string {
	border := lipgloss.NewStyle().Foreground(color)
	left, right := "│", "│"
	topLeft, topRight, bottomLeft, bottomRight, horizontal := "╭", "╮", "╰", "╯", "─"
	if outgoing {
		left = "║"
	} else {
		right = "║"
	}
	if selected {
		left, right = "║", "║"
		topLeft, topRight, bottomLeft, bottomRight, horizontal = "╔", "╗", "╚", "╝", "═"
	}
	out := []string{border.Render(topLeft + strings.Repeat(horizontal, innerWidth+2) + topRight)}
	for _, line := range lines {
		cell := lipgloss.PlaceHorizontal(innerWidth, lipgloss.Left, truncateCells(line, innerWidth))
		out = append(out, border.Render(left)+" "+cell+" "+border.Render(right))
	}
	out = append(out, border.Render(bottomLeft+strings.Repeat(horizontal, innerWidth+2)+bottomRight))
	return out
}

func indentLines(lines []string, spaces int) []string {
	if spaces <= 0 {
		return lines
	}
	prefix := strings.Repeat(" ", spaces)
	out := make([]string, len(lines))
	for i, line := range lines {
		out[i] = prefix + line
	}
	return out
}

func bubbleBodyLines(body string, wrapWidth int) []string {
	var out []string
	for _, line := range strings.Split(body, "\n") {
		out = append(out, wrapLine(line, wrapWidth)...)
	}
	return out
}

func isSentMessage(msg tracker.Message) bool {
	return msg.Sender == "You" || strings.Contains(msg.Sender, "→") || strings.HasPrefix(msg.Sender, "to ")
}

func (m model) messageColorKey(msg tracker.Message) string {
	sender := strings.TrimSpace(msg.Sender)
	if strings.HasPrefix(sender, "to ") {
		return strings.TrimSpace(strings.TrimPrefix(sender, "to "))
	}
	if strings.Contains(sender, "→") {
		parts := strings.Split(sender, "→")
		if strings.TrimSpace(parts[0]) == m.ownName || strings.TrimSpace(parts[0]) == "agent-communicator" {
			return strings.TrimSpace(parts[len(parts)-1])
		}
	}
	return senderColorKey(sender)
}

func (m model) messageBorderColor(msg tracker.Message, colorKey string) lipgloss.Color {
	if m.isSavedMessage(msg) {
		return colors.Saved
	}
	if isSentMessage(msg) {
		return colors.Info
	}
	return colors.AgentColors[agentColorIndex(colorKey)]
}
