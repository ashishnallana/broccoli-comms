package main

func (m *model) scrollSelectedMessageIntoView() {
	visible := m.messageVisibleLines()
	if visible <= 0 {
		return
	}
	start, end := m.selectedMessageLineRange()
	if start < 0 {
		return
	}
	if start < m.messageOffset {
		m.messageOffset = start
		return
	}
	if end >= m.messageOffset+visible {
		m.messageOffset = max(0, end-visible+1)
	}
}

func (m model) selectedMessageLineRange() (int, int) {
	messages := m.displayOrderedMessages()
	if m.messageSelected < 0 || m.messageSelected >= len(messages) {
		return -1, -1
	}
	line := 0
	for i, msg := range messages {
		count := len(m.messageBubbleLines(msg, i, m.messageContentWidth()))
		if i > 0 {
			line++
		}
		if i == m.messageSelected {
			return line, line + max(1, count) - 1
		}
		line += count
	}
	return -1, -1
}
