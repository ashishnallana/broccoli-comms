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

func TestNarrowMouseClickDoesNotSelectInvisibleSidebarAgent(t *testing.T) {
	m := model{width: 60, height: 24, selected: 0, rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}}}
	updated, cmd := m.handleMouse(tea.MouseMsg{X: 5, Y: 8, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
	if cmd != nil {
		t.Fatalf("narrow sidebar click produced command: %v", cmd)
	}
	if updated.(model).selected != 0 {
		t.Fatalf("narrow click selected invisible sidebar row %d", updated.(model).selected)
	}
}

func TestMouseClickInputModes(t *testing.T) {
	m := model{width: 120, height: 30, rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	y := mouseComposerTopForTest(m)
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

func TestNarrowMouseClickInputModesUsesFullWidthComposer(t *testing.T) {
	m := model{width: 60, height: 24, rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	y := mouseComposerTopForTest(m)
	updated, _ := m.handleMouse(tea.MouseMsg{X: 2 + 18, Y: y, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
	if updated.(model).inputMode != inputModeText {
		t.Fatalf("narrow inputMode=%v want text", updated.(model).inputMode)
	}
}

func mouseComposerTopForTest(m model) int {
	titleH := lineCount(titleStyle.Render(m.conversationTitle()))
	if m.width < 70 {
		return titleH
	}
	return 1 + titleH
}
