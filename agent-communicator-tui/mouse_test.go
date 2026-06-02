package main

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func TestMouseSelectAgentAtListLine(t *testing.T) {
	m := model{width: 100, height: 30, rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}}}
	if !m.selectAgentAtListLine(3, 30) {
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

func TestMouseClickInputModeButtons(t *testing.T) {
	m := model{width: 120, height: 30, rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	y := mouseModeButtonTopForTest(m)
	updated, _ := m.handleMouse(tea.MouseMsg{X: 3 + modeButtonXForTest(1), Y: y, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
	if updated.(model).inputMode != inputModeText {
		t.Fatalf("inputMode=%v want text", updated.(model).inputMode)
	}
	updated, _ = updated.(model).handleMouse(tea.MouseMsg{X: 3 + modeButtonXForTest(2), Y: y, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
	if updated.(model).inputMode != inputModeKeys {
		t.Fatalf("inputMode=%v want keys", updated.(model).inputMode)
	}
}

func TestMouseClickComposerInputDoesNotSwitchModes(t *testing.T) {
	m := model{width: 120, height: 30, inputMode: inputModeMessage, rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	y := mouseComposerTopForTest(m)
	updated, _ := m.handleMouse(tea.MouseMsg{X: 3 + modeButtonXForTest(1), Y: y, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
	if updated.(model).inputMode != inputModeMessage {
		t.Fatalf("composer input click switched inputMode=%v", updated.(model).inputMode)
	}
}

func TestNarrowMouseClickInputModeButtonsUsesFullWidthComposer(t *testing.T) {
	m := model{width: 60, height: 24, rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	y := mouseModeButtonTopForTest(m)
	updated, _ := m.handleMouse(tea.MouseMsg{X: 1 + modeButtonXForTest(1), Y: y, Action: tea.MouseActionPress, Button: tea.MouseButtonLeft})
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

func mouseModeButtonTopForTest(m model) int {
	_, midW, _ := m.layoutWidths()
	panelW := midW
	if m.width < 70 {
		panelW = m.width
	}
	innerW := panelInnerWidth(panelW)
	if m.width < 70 {
		innerW = max(1, panelW-2)
	}
	return mouseComposerTopForTest(m) + lineCount(m.composerInputBox(innerW))
}

func modeButtonXForTest(index int) int {
	x := 0
	buttons := inputModeButtons()
	for i := 0; i < index && i < len(buttons); i++ {
		x += lipgloss.Width(modeTabStyle.Render(buttons[i].Label)) + 1
	}
	return x + 1
}
