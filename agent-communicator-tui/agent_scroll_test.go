package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestAgentListIncludesCurrentAgentAndShowsCounts(t *testing.T) {
	m := model{width: 100, height: 20}
	for i := 0; i < 4; i++ {
		m.rows = append(m.rows, agentRow{Name: fmt.Sprintf("agent-%02d", i), Scope: "local"})
	}
	m.selected = 3
	view := m.agentList(40, 12)
	if !strings.Contains(view, "agent-03") {
		t.Fatalf("current agent should be listed in switcher list:\n%s", view)
	}
	if !strings.Contains(view, "LOCAL (4)") || !strings.Contains(view, "agent-00") {
		t.Fatalf("list missing local count/rows:\n%s", view)
	}
}

func TestAgentListUsesLocalAndRemoteSectionHeadings(t *testing.T) {
	m := model{width: 120, height: 24, rows: []agentRow{
		{Name: "local-a", Scope: "local", Hostname: "host-a"},
		{Name: "remote-a", Scope: "remote", Hostname: "host-r"},
		{Name: "remote-b", Scope: "remote", Hostname: "host-r"},
	}}
	m.selected = 0
	view := m.agentList(40, 12)
	if !strings.Contains(view, "LOCAL (1)") || !strings.Contains(view, "REMOTE (2)") || !strings.Contains(view, "local-a") {
		t.Fatalf("switcher list should show all agents with counts:\n%s", view)
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
