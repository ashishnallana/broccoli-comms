package main

import (
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"

	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var composerBoxStyle = lipgloss.NewStyle().Background(colors.InputBg).Foreground(colors.Text).Padding(1, 2)
var panelBoxStyle = lipgloss.NewStyle().Background(colors.PanelBg).Padding(0, 1)
var mobileComposerBoxStyle = lipgloss.NewStyle().Background(colors.InputBg).Padding(1, 1)

const composerMaxLines = 5

func (m model) View() string {
	defer debugSince("view", time.Now())
	if m.width == 0 {
		return "loading..."
	}
	if m.commandPalette.Open {
		return m.commandPaletteView(m.width, m.height)
	}
	if m.showingMemoryApprovals {
		return m.memoryApprovalsView(m.width, m.height)
	}
	return m.baseView()
}

func (m model) baseView() string {
	fullH := max(1, m.height)
	if m.showingSaveForm {
		return m.renderSaveForm()
	}
	if m.showingPromptMenu {
		return m.renderPromptMenu(m.width, fullH)
	}
	if m.showingConfigMenu {
		return m.renderConfigMenu(m.width, fullH)
	}
	if m.showingRunAgentForm {
		return m.renderRunAgentForm(m.width, fullH)
	}
	tabs := m.bottomTabBar(m.width)
	status := m.footer(m.width)
	bottomH := lineCount(status) + lineCount(tabs)
	bodyH := max(1, fullH-bottomH)
	parts := []string{m.mainContentView(bodyH)}
	if status != "" {
		parts = append(parts, status)
	}
	if tabs != "" {
		parts = append(parts, tabs)
	}
	return truncateLines(lipgloss.JoinVertical(lipgloss.Left, parts...), fullH)
}

func (m model) mainContentView(bodyH int) string {
	if m.width < 70 {
		return truncateLines(m.conversationPanel(m.width, bodyH), bodyH)
	}
	chatW, rightW, _ := m.layoutWidths()
	chat := m.conversationPanel(chatW, bodyH)
	right := m.rightColumn(rightW, bodyH)
	return truncateLines(lipgloss.JoinHorizontal(lipgloss.Top, chat, right), bodyH)
}

func (m model) layoutWidths() (int, int, int) {
	right := min(42, max(28, (m.width*32)/100))
	if m.width < 100 {
		right = min(34, max(24, m.width/3))
	}
	chat := max(10, m.width-right)
	return chat, right, 0
}

func (m model) footer(width int) string {
	lines := []string{}
	if m.paneCaptureStatus != "" {
		lines = append(lines, m.paneCaptureStatus)
	} else if m.directInputStatus != "" {
		statusLine := m.directInputStatus
		if m.directInputStatusErr {
			statusLine = errorBarStyle.Render(statusLine)
		}
		lines = append(lines, statusLine)
	}
	if m.err != nil {
		lines = append(lines, errorBarStyle.Render(m.errorStatusLine()))
	}
	for i, text := range lines {
		if lipgloss.Width(text) > width {
			lines[i] = truncateCells(text, max(1, width-1)) + "…"
		}
	}
	return mutedStyle.Render(strings.Join(lines, "\n"))
}

func (m model) errorStatusLine() string {
	text := "error · " + m.err.Error()
	if rpcErr, ok := m.err.(*tracker.RPCError); ok && rpcErr.Data != nil {
		parts := []string{"error"}
		if rpcErr.Data.Operation != "" {
			parts = append(parts, rpcErr.Data.Operation)
		}
		if rpcErr.Data.Agent != "" {
			parts = append(parts, rpcErr.Data.Agent)
		}
		parts = append(parts, rpcErr.Message)
		text = strings.Join(parts, " · ")
	}
	if m.retryOperation != "" {
		text += " · r retry"
	}
	return text
}

func (m model) runtimeStatusLine() string {
	state := "rpc ok"
	if m.agentListLoading {
		state = "rpc refreshing"
	}
	if m.healthErr != nil || m.agentListStale || m.err != nil {
		state = "rpc degraded"
	}
	if m.health.Status != "" && m.health.Status != "ok" && state == "rpc ok" {
		state = "rpc " + m.health.Status
	}
	row := m.currentRow()
	active := "no agent"
	if row.Name != "" {
		activeParts := []string{row.Name}
		if badge := modelBadge(row); badge != "??" {
			activeParts = append(activeParts, badge)
		}
		if machine := rowMachineLabel(row); machine != "" {
			activeParts = append(activeParts, "@ "+machine)
		}
		active = strings.Join(activeParts, " ")
	}
	online, total := m.health.OnlineAgentCount, m.health.AgentCount
	if total == 0 && len(m.rows) > 0 {
		total = len(m.rows)
		online = countOnlineRows(m.rows)
	}
	registry := "registry unknown"
	if m.health.RegistryConnected != nil {
		if *m.health.RegistryConnected {
			registry = "registry online"
		} else {
			registry = "registry offline"
		}
	}
	details := []string{state, "active " + active, fmt.Sprintf("online %d/%d", online, total), registry}
	if m.health.RemoteTrackerCount > 0 {
		details = append(details, fmt.Sprintf("trackers %d/%d", m.health.OnlineRemoteTrackerCount, m.health.RemoteTrackerCount))
	}
	details = append(details, time.Now().In(displayLocation).Format("15:04"))
	if m.runtime.AppRuntime {
		details = append([]string{"Broccoli Comms runtime"}, details...)
	}
	if m.runtime.TrackerSocket != "" {
		details = append(details, "socket "+filepath.Base(m.runtime.TrackerSocket))
	}
	return strings.Join(details, " · ")
}

func (m model) sendingContextLine() string {
	row := m.currentRow()
	if row.Name == "" {
		return "no target"
	}
	parts := []string{row.Name}
	if badge := modelBadge(row); badge != "??" {
		parts = append(parts, badge)
	}
	if machine := rowMachineLabel(row); machine != "" {
		parts = append(parts, "@ "+machine)
	}
	return strings.Join(parts, " ")
}

func truncateLines(s string, height int) string {
	lines := strings.Split(s, "\n")
	if len(lines) > height {
		lines = lines[:height]
	}
	return strings.Join(lines, "\n")
}

func wrapLine(s string, width int) []string {
	if lipgloss.Width(s) <= width {
		return []string{s}
	}
	words := strings.Fields(s)
	if len(words) == 0 {
		return []string{""}
	}
	var lines []string
	current := ""
	for _, word := range words {
		candidate := strings.TrimSpace(current + " " + word)
		if lipgloss.Width(candidate) <= width {
			current = candidate
			continue
		}
		if current != "" {
			lines = append(lines, current)
		}
		for lipgloss.Width(word) > width {
			part := truncateCells(word, width)
			lines = append(lines, part)
			word = strings.TrimPrefix(word, part)
		}
		current = word
	}
	if current != "" {
		lines = append(lines, current)
	}
	return lines
}
func truncateCells(s string, width int) string {
	var b strings.Builder
	for _, r := range s {
		if lipgloss.Width(b.String()+string(r)) > width {
			break
		}
		b.WriteRune(r)
	}
	return b.String()
}
func marker(selected bool) string {
	if selected {
		return ">"
	}
	return " "
}
func panelInnerWidth(w int) int  { return max(1, w-4) }
func panelInnerHeight(h int) int { return max(1, h-2) }

func box(s string, w, h int) string {
	innerW := panelInnerWidth(w)
	innerH := panelInnerHeight(h)
	return panelBoxStyle.Width(innerW).Height(innerH).MaxWidth(max(1, w)).Render(s)
}
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func localHostname() string {
	if h := config.GetString("", "tracker", "hostname"); h != "" {
		return h
	} else if h := os.Getenv("AGENT_TRACKER_HOSTNAME"); h != "" {
		return h
	}
	if h, err := os.Hostname(); err == nil {
		return h
	}
	return "local"
}

func (m model) renderPromptMenu(width, height int) string {
	var body string
	if len(m.prompts) == 0 {
		body = lipgloss.NewStyle().
			Foreground(colors.Warning).
			Render("No prompt templates found.\nAdd <prompt-name>.md files in ~/.config/agent-communicator/prompts/")
	} else {
		var listLines []string
		for i, prompt := range m.prompts {
			style := lipgloss.NewStyle().Foreground(colors.Text)
			prefix := "  "
			if i == m.promptSelected {
				style = style.Background(colors.SelectedBg).Foreground(colors.SelectedFg)
				prefix = "> "
			}
			listLines = append(listLines, prefix+style.Render(prompt.Name))
		}
		body = strings.Join(listLines, "\n")
	}

	title := titleStyle.Render("Prompt Templates")
	help := mutedStyle.Render("enter edit/send · esc close · only saved edits are sent")
	boxContent := title + "\n" + help + "\n\n" + body
	return box(boxContent, width, height)
}

func (m model) renderRunAgentForm(width, height int) string {
	name := string(m.runAgentName)
	if name == "" {
		name = "agent-name"
	}
	provider := fallback(m.runAgentProvider, "no configured provider")
	content := titleStyle.Render("Run new agent") + "\n" +
		mutedStyle.Render("Host: "+fallback(m.runAgentHost, localHostname())+" · Provider: "+provider) + "\n\n" +
		"Agent name: " + lipgloss.NewStyle().Foreground(colors.TextStrong).Render(name) + "\n\n" +
		mutedStyle.Render("Type name · Enter run via broccoli-comms run · Esc cancel")
	return box(content, width, height)
}

func (m model) renderConfigMenu(width, height int) string {
	var body string
	items := m.filteredConfigItems()
	query := string(m.configQuery)
	if len(m.configItems) == 0 {
		body = lipgloss.NewStyle().
			Foreground(colors.Error).
			Render("No configured, running, or remote agents found via broccoli-comms agent list.")
	} else if len(items) == 0 {
		body = lipgloss.NewStyle().Foreground(colors.Error).Render("No agents match search: " + query)
	} else {
		var listLines []string
		for i, item := range items {
			style := lipgloss.NewStyle().Foreground(colors.Text)
			prefix := "  "
			if i == m.configSelected {
				style = style.Background(colors.SelectedBg).Foreground(colors.SelectedFg)
				prefix = "> "
			}

			scopePrefix := fmt.Sprintf("[%s] ", shortHost(localHostname()))
			if item.IsNewAgent {
				scopePrefix = fmt.Sprintf("[%s] new ", shortHost(item.Hostname))
			} else if item.IsRemote {
				scopePrefix = fmt.Sprintf("[%s] remote ", shortHost(item.Hostname))
			} else if item.Running {
				scopePrefix = fmt.Sprintf("[%s] running ", shortHost(localHostname()))
			} else if item.Configured {
				scopePrefix = fmt.Sprintf("[%s] configured ", shortHost(localHostname()))
			}

			scopeStyle := lipgloss.NewStyle().Foreground(colors.Muted)
			if !item.IsRemote {
				scopeStyle = lipgloss.NewStyle().Foreground(colors.Success)
			}
			if i == m.configSelected {
				scopeStyle = scopeStyle.Background(colors.SelectedBg).Foreground(colors.SelectedFg)
			}

			action := "Enter: run"
			if item.IsNewAgent {
				action = "Enter: name agent"
			} else if item.IsRemote || !item.Launchable {
				action = "Enter: immutable copy"
			} else if item.Copyable {
				action = "Enter: run · c: copy"
			}
			listLines = append(listLines, prefix+scopeStyle.Render(scopePrefix)+style.Render(item.Name)+" - "+item.Description+mutedStyle.Render(" · "+action))
		}
		body = strings.Join(listLines, "\n")
	}

	title := titleStyle.Render("Agents (search/run/copy/new)")
	boxContent := title + "\n" + mutedStyle.Render("Search: "+query+"  ·  Enter runs existing agents or opens new-agent name form") + "\n\n" + body
	return box(boxContent, width, height)
}
