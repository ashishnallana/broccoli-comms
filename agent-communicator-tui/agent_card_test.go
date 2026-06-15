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

func TestSelectedAgentCardUsesSolidFill(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "alpha", Scope: "local"}, true, 40)
	for _, unwanted := range []string{"╔", "╝", "╭", "╰"} {
		if strings.Contains(card, unwanted) {
			t.Fatalf("selected agent card should use solid fill, not border:\n%s", card)
		}
	}
	if !strings.Contains(card, "alpha") {
		t.Fatalf("selected card missing name:\n%s", card)
	}
}

func TestAgentCardShowsNameHostProviderStatusOnly(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "tanmayvijay-mac-ywd/alpha", AgentName: "alpha", Scope: "remote", Status: "idle", Hostname: "tanmayvijay-mac-ywd", RegistryName: "mundus", ModelType: "pi"}, false, 70)
	for _, want := range []string{"alpha", "tanmayvijay-mac-ywd · pi", "idle"} {
		if !strings.Contains(card, want) {
			t.Fatalf("agent card missing %q:\n%s", want, card)
		}
	}
	if strings.Contains(strings.Split(card, "\n")[0], "tanmayvijay-mac-ywd") {
		t.Fatalf("remote hostname should stay off primary name line:\n%s", card)
	}
	if strings.Contains(card, "mundus") || strings.Contains(card, "cwd") {
		t.Fatalf("agent card contains unsupported metadata:\n%s", card)
	}
	if got := lineCount(card); got != agentCardHeight {
		t.Fatalf("agent card height = %d, want %d:\n%s", got, agentCardHeight, card)
	}
}

func TestRemoteAgentViewNameOmitsHostname(t *testing.T) {
	view := newAgentView(agentRow{Name: "tanmayvijay.c.googlers.com/remote-agent", Scope: "remote", AgentName: "remote-agent", Hostname: "tanmayvijay.c.googlers.com"}, false, 0)
	if view.Name != "remote-agent" || view.HostnameLabel != "tanmayvijay.c.googlers.com" {
		t.Fatalf("remote display name/host = %q/%q", view.Name, view.HostnameLabel)
	}
}

func TestAgentCardTruncatesLongNameAndHostWithoutWrapping(t *testing.T) {
	m := model{}
	card := m.agentCard(agentRow{Name: "agent-with-a-very-very-long-name-that-should-not-wrap", Scope: "remote", Status: "running", Hostname: "host-with-a-very-long-name-that-should-truncate.example.com", RegistryName: "registry-with-long-name", ModelType: "pi"}, false, 34)
	if strings.Contains(card, "host ") || strings.Contains(card, "registry-with-long-name") {
		t.Fatalf("agent card should not show host labels or registry:\n%s", card)
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

func TestAgentCardHidesDetectionTextAndUsesRedDotWhenBlocked(t *testing.T) {
	m := model{}
	row := agentRow{Name: "claude-agent", Scope: "local", Status: "idle", ModelType: "claude", Detection: tracker.DetectionStatus{Configured: true, Enabled: true, SecondsUntilNextScan: 3, LastResult: "detected_cooldown"}}
	card := m.agentCard(row, false, 80)
	if strings.Contains(card, "detect") || strings.Contains(card, "⟳") {
		t.Fatalf("agent card should not show detection text:\n%s", card)
	}
	got := agentStatusDotStyle(row).GetForeground()
	if got == nil || string(got.(lipgloss.Color)) != string(colors.Error) {
		t.Fatalf("blocked agent dot foreground = %v, want %s", got, colors.Error)
	}
}

func TestAgentCardUnreadCountStaysOnNameLine(t *testing.T) {
	row := agentRow{Name: "coding-agent", Scope: "local", AgentID: "agent-1"}
	m := model{unreadCounts: map[string]int{conversationKey(row): 12}}
	card := m.agentCard(row, false, 86)
	lines := strings.Split(card, "\n")
	if len(lines) < 1 || !strings.Contains(lines[0], "12") {
		t.Fatalf("unread count not on name line:\n%s", card)
	}
	if len(lines) > 1 && strings.Contains(lines[1], "12") {
		t.Fatalf("unread count wrapped to detail line:\n%s", card)
	}
}
