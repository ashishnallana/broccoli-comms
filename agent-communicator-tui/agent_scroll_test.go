package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestAgentListScrollsSelectedAgentIntoView(t *testing.T) {
	m := model{width: 100, height: 20}
	for i := 0; i < 12; i++ {
		m.rows = append(m.rows, agentRow{Name: fmt.Sprintf("agent-%02d", i), Scope: "local"})
	}
	m.selected = 11
	m.scrollSelectedAgentIntoView()
	if m.agentOffset == 0 {
		t.Fatalf("agentOffset did not move")
	}
	view := m.agentList(40, 12)
	if !strings.Contains(view, "agent-11") {
		t.Fatalf("selected agent not visible:\n%s", view)
	}
}

func TestAgentListScrollAccountsForGroupHeaders(t *testing.T) {
	m := model{width: 120, height: 24}
	for i := 0; i < 8; i++ {
		m.rows = append(m.rows, agentRow{Name: fmt.Sprintf("agent-%02d", i), Scope: "local", Hostname: fmt.Sprintf("host-%02d", i)})
	}
	m.selected = 3
	m.scrollSelectedAgentIntoView()
	view := m.agentList(32, m.agentListVisibleLines())
	if !strings.Contains(view, "╚") || !strings.Contains(view, "agent-03") {
		t.Fatalf("selected grouped agent should be fully visible, offset=%d:\n%s", m.agentOffset, view)
	}
}

func TestAgentListIsClippedToWindowHeight(t *testing.T) {
	m := model{}
	for i := 0; i < 8; i++ {
		m.rows = append(m.rows, agentRow{Name: fmt.Sprintf("agent-%02d", i), Scope: "local"})
	}
	view := m.agentList(40, 8)
	if got := lineCount(view); got > 8 {
		t.Fatalf("agent list lines=%d > 8:\n%s", got, view)
	}
}
