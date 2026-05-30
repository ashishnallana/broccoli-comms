package main

const agentCardHeight = 5

func (m model) visibleAgentCards() int {
	return max(1, (m.height-lineCount(m.footer(max(1, m.width)))-4)/agentCardHeight)
}

func (m *model) scrollSelectedAgentIntoView() {
	visible := m.visibleAgentCards()
	if m.selected < m.agentOffset {
		m.agentOffset = m.selected
	}
	if m.selected >= m.agentOffset+visible {
		m.agentOffset = m.selected - visible + 1
	}
	maxOffset := max(0, len(m.rows)-visible)
	if m.agentOffset > maxOffset {
		m.agentOffset = maxOffset
	}
	m.agentOffset = max(0, m.agentOffset)
}
