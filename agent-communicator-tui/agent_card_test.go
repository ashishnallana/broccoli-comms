package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
)

func TestAgentCardUsesRequestedWidth(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "alpha", Scope: "local"}, false, 40)
	for _, line := range strings.Split(card, "\n") {
		if got := lipgloss.Width(line); got != 40 {
			t.Fatalf("line width=%d want 40 line=%q card=\n%s", got, line, card)
		}
	}
}

func TestSelectedAgentCardUsesDoubleBorder(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "alpha", Scope: "local"}, true, 40)
	if !strings.Contains(card, "╔") || !strings.Contains(card, "╝") {
		t.Fatalf("selected agent card should use double border:\n%s", card)
	}
}

func TestAgentCardShowsStatusRegistryAndFullHost(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "alpha", Scope: "remote", Status: "idle", Hostname: "tanmayvijay-mac-ywd", RegistryName: "mundus", ModelType: "pi"}, false, 70)
	for _, want := range []string{"alpha", "Pi · idle · mundus", "host tanmayvijay-mac-ywd"} {
		if !strings.Contains(card, want) {
			t.Fatalf("agent card missing %q:\n%s", want, card)
		}
	}
}

func TestCompactCWD(t *testing.T) {
	cases := map[string]string{
		"":                               "",
		"unknown":                        "",
		"unavailable":                    "",
		"/":                              "/",
		"/repo":                          "repo",
		"/Users/tanmayvijay/project":     "tanmayvijay/project",
		"/Users/tanmayvijay/project/sub": "project/sub",
		"relative/path/to/project":       "to/project",
	}
	for input, want := range cases {
		if got := compactCWD(input); got != want {
			t.Fatalf("compactCWD(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestAgentCardUnreadCountStaysOnNameLine(t *testing.T) {
	row := agentRow{Name: "coding-agent", Scope: "local", AgentID: "agent-1"}
	m := model{unreadCounts: map[string]int{conversationKey(row): 12}}
	card := m.agentCard(row, false, 86)
	lines := strings.Split(card, "\n")
	if len(lines) < 3 || !strings.Contains(lines[1], "12") {
		t.Fatalf("unread count not on name line:\n%s", card)
	}
	if len(lines) > 2 && strings.Contains(lines[2], "12") {
		t.Fatalf("unread count wrapped to detail line:\n%s", card)
	}
}
