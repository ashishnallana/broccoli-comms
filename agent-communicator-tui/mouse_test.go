package main

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestMouseSelectAgentAtListLine(t *testing.T) {
	m := model{width: 100, height: 30, rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}}}
	if !m.selectAgentAtListLine(agentCardHeight+2, 30) {
		t.Fatal("mouse list line did not select agent")
	}
	if m.selected != 1 {
		t.Fatalf("selected=%d want 1", m.selected)
	}
}

func TestMouseClickInputModes(t *testing.T) {
	m := model{width: 120, height: 30, rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	m.View()
	_, midW, _ := m.layoutWidths()
	footerH := lineCount(m.footer(max(1, m.width)))
	bodyH := max(3, m.height-footerH)
	innerH := panelInnerHeight(bodyH)
	titleH := lineCount(titleStyle.Render(m.conversationTitle()))
	composerH := lineCount(m.composerBox(panelInnerWidth(midW)))
	y := 1 + titleH + max(1, innerH-titleH-composerH-2) + 1
	leftW, _, _ := m.layoutWidths()
	updated, _ := m.handleMouse(tea.MouseMsg{X: leftW + 2 + 18, Y: y, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
	if updated.(model).inputMode != inputModeText {
		t.Fatalf("inputMode=%v want text", updated.(model).inputMode)
	}
	updated, _ = updated.(model).handleMouse(tea.MouseMsg{X: leftW + 2 + 45, Y: y, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
	if updated.(model).inputMode != inputModeBroadcast {
		t.Fatalf("inputMode=%v want broadcast", updated.(model).inputMode)
	}
}
