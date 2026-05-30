package main

const agentCardHeight = 5

func (m model) visibleAgentCards() int {
	return max(1, m.agentListVisibleLines()/agentCardHeight)
}

func (m model) agentListVisibleLines() int {
	footerH := lineCount(m.footer(max(1, m.width)))
	bodyH := max(3, m.height-footerH)
	return max(1, panelInnerHeight(bodyH)-3)
}

func (m model) selectedAgentLineRangeFromOffset(offset int) (int, int) {
	line := 0
	lastGroup := ""
	hiddenStart := m.hiddenStartIndex()
	for i := offset; i < len(m.rows); i++ {
		if i == hiddenStart && hiddenStart > 0 {
			if line > 0 {
				line++
			}
			lastGroup = ""
		}
		group := m.agentView(m.rows[i]).GroupHeader
		if group != "" && group != lastGroup {
			line++
			lastGroup = group
		}
		if i == m.selected {
			return line, line + agentCardHeight
		}
		line += agentCardHeight
		if i < len(m.rows)-1 {
			line++
		}
	}
	return 0, 0
}

func (m *model) scrollSelectedAgentIntoView() {
	if len(m.rows) == 0 {
		m.agentOffset = 0
		return
	}
	m.selected = min(max(0, m.selected), len(m.rows)-1)
	m.agentOffset = min(max(0, m.agentOffset), len(m.rows)-1)
	if m.selected < m.agentOffset {
		m.agentOffset = m.selected
	}
	visibleLines := m.agentListVisibleLines()
	for m.agentOffset < m.selected {
		_, end := m.selectedAgentLineRangeFromOffset(m.agentOffset)
		if end <= visibleLines {
			break
		}
		m.agentOffset++
	}
	m.agentOffset = min(max(0, m.agentOffset), len(m.rows)-1)
}
