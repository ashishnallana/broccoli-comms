package main

import (
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type TerminalTheme struct {
	BaseBg        lipgloss.Color
	PanelBg       lipgloss.Color
	PanelBgAlt    lipgloss.Color
	RightColumnBg lipgloss.Color
	Text          lipgloss.Color
	TextStrong    lipgloss.Color
	TextSubtle    lipgloss.Color
	Muted         lipgloss.Color
	Accent        lipgloss.Color
	AccentStrong  lipgloss.Color
	AccentAlt     lipgloss.Color
	Success       lipgloss.Color
	Warning       lipgloss.Color
	Error         lipgloss.Color
	Info          lipgloss.Color
	Border        lipgloss.Color
	SelectedBg    lipgloss.Color
	SelectedFg    lipgloss.Color
	InputBg       lipgloss.Color
	PopupBg       lipgloss.Color
	PopupBorder   lipgloss.Color
	BadgeBg       lipgloss.Color
	BadgeFg       lipgloss.Color
	RemoteBadgeBg lipgloss.Color
	RemoteBadgeFg lipgloss.Color
	ReadTick      lipgloss.Color
	DeliveredTick lipgloss.Color
	SentTick      lipgloss.Color
	Saved         lipgloss.Color
	AgentColors   []lipgloss.Color
}

var colors = defaultTerminalTheme()

func defaultTerminalTheme() TerminalTheme {
	c := func(index string) lipgloss.Color { return lipgloss.Color(index) }
	return TerminalTheme{
		BaseBg:        c("0"),
		PanelBg:       c("0"),
		PanelBgAlt:    c("8"),
		RightColumnBg: c("8"),
		Text:          c("7"),
		TextStrong:    c("15"),
		TextSubtle:    c("8"),
		Muted:         c("8"),
		Accent:        c("6"),
		AccentStrong:  c("14"),
		AccentAlt:     c("5"),
		Success:       c("2"),
		Warning:       c("3"),
		Error:         c("1"),
		Info:          c("4"),
		Border:        c("8"),
		SelectedBg:    c("14"),
		SelectedFg:    c("0"),
		InputBg:       c("8"),
		PopupBg:       c("0"),
		PopupBorder:   c("8"),
		BadgeBg:       c("4"),
		BadgeFg:       c("0"),
		RemoteBadgeBg: c("5"),
		RemoteBadgeFg: c("0"),
		ReadTick:      c("10"),
		DeliveredTick: c("14"),
		SentTick:      c("8"),
		Saved:         c("3"),
		AgentColors:   []lipgloss.Color{c("2"), c("6"), c("5"), c("3"), c("4"), c("1"), c("10"), c("13"), c("11"), c("14")},
	}
}

type commandPaletteState struct {
	Open     bool
	Query    []rune
	Selected int
}

type commandAction struct {
	ID       string
	Title    string
	Subtitle string
	Category string
	Shortcut string
	Keywords []string
	Enabled  func(model) bool
	Run      func(*model) tea.Cmd
}

func isCommandPaletteOpenKey(msg tea.KeyMsg) bool {
	return msg.Type == tea.KeyCtrlO
}

func commandPaletteActions() []commandAction {
	return []commandAction{
		{
			ID:       "switch-agent-next",
			Title:    "Switch agent",
			Subtitle: "Select the next normal local or remote agent.",
			Category: "Agents",
			Shortcut: "run",
			Keywords: []string{"agent", "next", "select"},
			Enabled:  func(m model) bool { return m.mode != savedView && len(m.rows) > 1 },
			Run: func(m *model) tea.Cmd {
				m.selectNextInSection(1)
				m.scrollSelectedAgentIntoView()
				m.selectLatestMessage()
				return m.reloadMessages()
			},
		},
		{
			ID:       "refresh-agents",
			Title:    "Refresh agents",
			Subtitle: "Reload tracker health, agents, outbox, and unread counts.",
			Category: "Agents",
			Shortcut: "run",
			Keywords: []string{"reload", "list", "tracker"},
			Enabled:  func(model) bool { return true },
			Run: func(m *model) tea.Cmd {
				m.agentListLoading = true
				return tea.Batch(loadHealth(m.local), loadAgents(m.local), loadOutboxCmd(), loadUnreadCounts(m.local, m.ownName), tickAgentListSpinner())
			},
		},
		{
			ID:       "toggle-system-agents",
			Title:    "Show system agents",
			Subtitle: "Toggle agent-communicator mailboxes in the switcher list.",
			Category: "Agents",
			Shortcut: "toggle",
			Keywords: []string{"hidden", "system", "agent-communicator"},
			Enabled:  func(model) bool { return true },
			Run: func(m *model) tea.Cmd {
				m.showSystemAgents = !m.showSystemAgents
				m.applyAgentVisibility(conversationKey(m.currentRow()))
				m.scrollSelectedAgentIntoView()
				return m.reloadMessages()
			},
		},
		{
			ID:       "focus-selected-pane",
			Title:    "Focus selected pane",
			Subtitle: "Switch tmux focus to the current agent pane.",
			Category: "Agents",
			Shortcut: "run",
			Keywords: []string{"tmux", "pane", "focus"},
			Enabled:  func(m model) bool { return m.currentRow().Name != "" },
			Run:      func(m *model) tea.Cmd { return switchToAgentPane(m.currentRow()) },
		},
		{
			ID:       "registry-status",
			Title:    "Registry status",
			Subtitle: "Refresh and show registry connectivity in the right status line.",
			Category: "Runtime",
			Shortcut: "open",
			Keywords: []string{"runtime", "health", "registry"},
			Enabled:  func(model) bool { return true },
			Run: func(m *model) tea.Cmd {
				m.directInputStatus = m.registryStatusLine()
				m.directInputStatusErr = false
				return tea.Batch(loadHealth(m.local), tea.Tick(4*time.Second, func(time.Time) tea.Msg { return clearDirectInputStatusTick{} }))
			},
		},
		{
			ID:       "clear-composer",
			Title:    "Clear composer",
			Subtitle: "Remove draft text from the input.",
			Category: "Messaging",
			Shortcut: "run",
			Keywords: []string{"message", "draft", "input"},
			Enabled:  func(m model) bool { return len(m.composer) > 0 },
			Run: func(m *model) tea.Cmd {
				m.composer = nil
				return nil
			},
		},
		{
			ID:       "quit",
			Title:    "Quit",
			Subtitle: "Exit Agent Communicator.",
			Category: "UI",
			Shortcut: "run",
			Keywords: []string{"exit", "close"},
			Enabled:  func(model) bool { return true },
			Run:      func(*model) tea.Cmd { return tea.Quit },
		},
	}
}

func (m model) filteredCommandActions() []commandAction {
	query := strings.ToLower(strings.TrimSpace(string(m.commandPalette.Query)))
	actions := commandPaletteActions()
	out := make([]commandAction, 0, len(actions))
	for _, action := range actions {
		if action.Enabled != nil && !action.Enabled(m) {
			continue
		}
		if query == "" || commandMatches(action, query) {
			out = append(out, action)
		}
	}
	return out
}

func commandMatches(action commandAction, query string) bool {
	haystack := strings.ToLower(strings.Join(append([]string{action.Title, action.Subtitle, action.Category, action.Shortcut}, action.Keywords...), " "))
	for _, part := range strings.Fields(query) {
		if !strings.Contains(haystack, part) {
			return false
		}
	}
	return true
}

func (m *model) clampCommandPaletteSelection() {
	actions := m.filteredCommandActions()
	if len(actions) == 0 {
		m.commandPalette.Selected = 0
		return
	}
	if m.commandPalette.Selected >= len(actions) {
		m.commandPalette.Selected = len(actions) - 1
	}
	if m.commandPalette.Selected < 0 {
		m.commandPalette.Selected = 0
	}
}

func (m model) updateCommandPalette(msg tea.KeyMsg) (model, tea.Cmd) {
	switch msg.Type {
	case tea.KeyCtrlC, tea.KeyCtrlQ:
		return m, tea.Quit
	case tea.KeyEsc:
		m.commandPalette.Open = false
		m.commandPalette.Query = nil
		m.commandPalette.Selected = 0
		return m, nil
	case tea.KeyUp, tea.KeyCtrlP:
		actions := m.filteredCommandActions()
		if len(actions) > 0 {
			m.commandPalette.Selected = (m.commandPalette.Selected - 1 + len(actions)) % len(actions)
		}
		return m, nil
	case tea.KeyDown, tea.KeyCtrlN:
		actions := m.filteredCommandActions()
		if len(actions) > 0 {
			m.commandPalette.Selected = (m.commandPalette.Selected + 1) % len(actions)
		}
		return m, nil
	case tea.KeyEnter:
		actions := m.filteredCommandActions()
		if len(actions) == 0 {
			return m, nil
		}
		idx := min(max(0, m.commandPalette.Selected), len(actions)-1)
		action := actions[idx]
		m.commandPalette.Open = false
		m.commandPalette.Query = nil
		m.commandPalette.Selected = 0
		if action.Run == nil {
			return m, nil
		}
		cmd := action.Run(&m)
		return m, cmd
	case tea.KeyBackspace:
		if len(m.commandPalette.Query) > 0 {
			m.commandPalette.Query = m.commandPalette.Query[:len(m.commandPalette.Query)-1]
			m.commandPalette.Selected = 0
		}
		return m, nil
	case tea.KeySpace:
		m.commandPalette.Query = append(m.commandPalette.Query, ' ')
		m.commandPalette.Selected = 0
		return m, nil
	case tea.KeyRunes:
		m.commandPalette.Query = append(m.commandPalette.Query, msg.Runes...)
		m.commandPalette.Selected = 0
		return m, nil
	}
	m.clampCommandPaletteSelection()
	return m, nil
}

func (m model) commandPaletteView(width, height int) string {
	actions := m.filteredCommandActions()
	paletteW := min(max(42, width/2), max(42, width-8))
	paletteH := min(max(10, len(actions)+5), max(10, height-4))
	contentW := max(8, paletteW-4)
	panelBG := colors.PopupBg
	panelLine := lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Text).Render
	query := strings.TrimSpace(string(m.commandPalette.Query))
	if query == "" {
		query = "type to filter commands…"
	}
	titleGap := max(1, contentW-lipgloss.Width("Command palette")-lipgloss.Width("esc close"))
	lines := []string{
		panelLine(lipgloss.NewStyle().Foreground(colors.Muted).Render("Command palette") + strings.Repeat(" ", titleGap) + lipgloss.NewStyle().Foreground(colors.Muted).Render("esc close")),
		lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(colors.InputBg).Foreground(colors.Text).Padding(0, 1).Render(truncateCells(query, max(1, contentW-2))),
	}
	lastCategory := ""
	for i, action := range actions {
		if len(lines) >= paletteH-1 {
			break
		}
		if action.Category != lastCategory {
			lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.TextSubtle).Bold(true).Render(truncateCells(strings.ToUpper(action.Category), contentW)))
			lastCategory = action.Category
		}
		title := truncateCells(action.Title, max(1, contentW-lipgloss.Width(action.Shortcut)-3))
		gap := max(1, contentW-lipgloss.Width(title)-lipgloss.Width(action.Shortcut))
		rowText := title + strings.Repeat(" ", gap) + action.Shortcut
		if i == m.commandPalette.Selected {
			lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(colors.SelectedBg).Foreground(colors.SelectedFg).Bold(true).Render(truncateCells(rowText, contentW)))
		} else {
			lines = append(lines, panelLine(rowText))
		}
		if action.Subtitle != "" && len(lines) < paletteH-1 {
			lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Muted).Render(truncateCells("  "+action.Subtitle, contentW)))
		}
	}
	if len(actions) == 0 {
		lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Muted).Render("No backed commands match."))
	}
	content := strings.Join(lines, "\n")
	box := lipgloss.NewStyle().Width(paletteW-2).MaxWidth(paletteW).Border(lipgloss.NormalBorder()).BorderForeground(colors.PopupBorder).Padding(1, 1).Background(panelBG).Render(content)
	return overlayString(m.baseView(), box, width, height)
}

func overlayString(base, overlay string, width, height int) string {
	baseLines := strings.Split(base, "\n")
	for len(baseLines) < height {
		baseLines = append(baseLines, "")
	}
	overlayLines := strings.Split(overlay, "\n")
	overlayW := 0
	for _, line := range overlayLines {
		overlayW = max(overlayW, lipgloss.Width(line))
	}
	top := max(0, (height-len(overlayLines))/2)
	left := max(0, (width-overlayW)/2)
	scrim := lipgloss.NewStyle().Background(colors.PopupBg).Render
	for i, line := range overlayLines {
		idx := top + i
		if idx >= len(baseLines) {
			break
		}
		lineW := lipgloss.Width(line)
		prefixW := min(left, width)
		rightW := max(0, width-prefixW-lineW)
		if lineW > width-prefixW {
			// Do not ANSI-truncate the overlay line; instead keep the styled
			// panel intact and let the terminal clip at the edge. This avoids
			// corrupting escape sequences, which previously let underlying right
			// column text bleed through the palette area.
			rightW = 0
		}
		baseLines[idx] = scrim(strings.Repeat(" ", prefixW)) + line + scrim(strings.Repeat(" ", rightW))
	}
	return strings.Join(baseLines[:min(len(baseLines), height)], "\n")
}
