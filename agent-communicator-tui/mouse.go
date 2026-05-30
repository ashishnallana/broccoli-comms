package main

import tea "github.com/charmbracelet/bubbletea"

func (m model) handleMouse(msg tea.MouseMsg) (tea.Model, tea.Cmd) {
	event := tea.MouseEvent(msg)
	if event.Action != tea.MouseActionPress || event.Button != tea.MouseButtonLeft {
		return m, nil
	}
	if m.mode != savedView && m.mouseSelectAgent(event.X, event.Y) {
		m.scrollSelectedAgentIntoView()
		m.selectLatestMessage()
		return m, m.reloadMessages()
	}
	if mode, ok := m.mouseInputMode(event.X, event.Y); ok {
		m.inputMode = mode
		return m, nil
	}
	return m, nil
}

func (m *model) mouseSelectAgent(x, y int) bool {
	leftW, _, _ := m.layoutWidths()
	bodyH := max(3, m.height-lineCount(m.footer(max(1, m.width))))
	if x < 0 || x >= leftW || y < 1 || y >= bodyH-1 || len(m.rows) == 0 {
		return false
	}
	listY := y - 4 // top border + title + device hostname + section header
	if listY < 0 {
		return false
	}
	return m.selectAgentAtListLine(listY, panelInnerWidth(leftW))
}

func (m *model) selectAgentAtListLine(listY, width int) bool {
	visible := max(1, m.sidebarAgentListHeight()/agentCardHeight)
	offset := min(max(0, m.agentOffset), max(0, len(m.rows)-visible))
	end := min(len(m.rows), offset+visible)
	hiddenStart := m.hiddenStartIndex()
	line := 0
	lastGroup := ""
	for i := offset; i < end; i++ {
		if i == hiddenStart && hiddenStart > 0 {
			line++
			lastGroup = ""
		}
		group := m.agentView(m.rows[i]).GroupHeader
		if group != "" && group != lastGroup {
			line++
			lastGroup = group
		}
		cardLines := lineCount(m.agentCard(m.rows[i], i == m.selected, width-2))
		if listY >= line && listY < line+cardLines {
			m.selected = i
			return true
		}
		line += cardLines
		if i < end-1 {
			line++
		}
	}
	return false
}

func (m model) sidebarAgentListHeight() int {
	bodyH := max(3, m.height-lineCount(m.footer(max(1, m.width))))
	return max(1, panelInnerHeight(bodyH)-3)
}

func (m model) mouseInputMode(x, y int) (inputMode, bool) {
	if m.mode == savedView || m.width == 0 || m.height == 0 {
		return inputModeMessage, false
	}
	leftW, midW, _ := m.layoutWidths()
	panelX := 0
	if m.width >= 70 {
		panelX = leftW
	}
	innerX := x - panelX - 2
	if innerX < 0 || innerX >= panelInnerWidth(midW) {
		return inputModeMessage, false
	}
	footerH := lineCount(m.footer(max(1, m.width)))
	bodyH := max(3, m.height-footerH)
	innerH := panelInnerHeight(bodyH)
	titleH := lineCount(titleStyle.Render(m.conversationTitle()))
	composerH := lineCount(m.composerBox(panelInnerWidth(midW)))
	composerTop := 1 + titleH + max(1, innerH-titleH-composerH-2) + 1
	if m.width < 70 {
		composerTop = titleH + max(1, innerH-titleH-composerH)
	}
	if y != composerTop {
		return inputModeMessage, false
	}
	if innerX < 13 {
		return inputModeMessage, true
	}
	if innerX < 28 {
		return inputModeText, true
	}
	if innerX < 41 {
		return inputModeKeys, true
	}
	return inputModeBroadcast, true
}
