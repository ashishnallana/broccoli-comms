package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
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

func TestAgentCardShowsStatusRegistryThenHostOnTwoContentLines(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "alpha", Scope: "remote", Status: "idle", Hostname: "tanmayvijay-mac-ywd", RegistryName: "mundus", ModelType: "pi"}, false, 70)
	for _, want := range []string{"alpha", "Pi · mundus · tanmayvijay-mac-ywd"} {
		if !strings.Contains(card, want) {
			t.Fatalf("agent card missing %q:\n%s", want, card)
		}
	}
	if got := lineCount(card); got != agentCardHeight {
		t.Fatalf("agent card height = %d, want %d:\n%s", got, agentCardHeight, card)
	}
}

func TestAgentCardTruncatesLongNameAndHostWithoutWrapping(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "agent-with-a-very-very-long-name-that-should-not-wrap", Scope: "remote", Status: "running", Hostname: "host-with-a-very-long-name-that-should-truncate.example.com", RegistryName: "registry-with-long-name", ModelType: "pi"}, false, 34)
	if strings.Contains(card, "running") || strings.Contains(card, "idle") || strings.Contains(card, "host ") {
		t.Fatalf("agent card should not show status words or host keyword:\n%s", card)
	}
	if got := lineCount(card); got != agentCardHeight {
		t.Fatalf("agent card wrapped, height=%d want %d:\n%s", got, agentCardHeight, card)
	}
	for _, line := range strings.Split(card, "\n") {
		if got := lipgloss.Width(line); got != 34 {
			t.Fatalf("line width=%d want 34 line=%q card=\n%s", got, line, card)
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

func TestAgentCardShowsDetectionCountdownAndResult(t *testing.T) {
	m := model{}
	row := agentRow{
		Name:      "claude-agent",
		Scope:     "local",
		ModelType: "claude",
		Detection: tracker.DetectionStatus{Configured: true, Enabled: true, SecondsUntilNextScan: 3, LastResult: "no_match"},
	}
	card := m.agentCard(row, false, 80)
	for _, want := range []string{"⟳3s", "detect clear"} {
		if !strings.Contains(card, want) {
			t.Fatalf("agent card missing %q:\n%s", want, card)
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
