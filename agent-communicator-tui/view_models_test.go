package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
)

func TestModelBadgeMapping(t *testing.T) {
	cases := []struct {
		modelType string
		cmd       string
		want      string
	}{
		{"claude", "", "Cl"},
		{"codex", "pi", "Cx"},
		{"pi", "codex", "Pi"},
		{"unknown", "claude-code", "Cl"},
		{"", "/nix/store/bin/codex", "Cx"},
		{"", "pi-coding-agent", "Pi"},
		{"", "unknown-agent", "??"},
		{"", "", "??"},
	}
	for _, tc := range cases {
		if got := modelBadge(agentRow{ModelType: tc.modelType, AgentCmd: tc.cmd}); got != tc.want {
			t.Fatalf("modelBadge(model=%q cmd=%q) = %q, want %q", tc.modelType, tc.cmd, got, tc.want)
		}
	}
}

func TestGroupAgentViewsByMachine(t *testing.T) {
	rows := []agentRow{
		{Name: "local-a", Scope: "local", Hostname: "alpha-host", AgentCmd: "pi"},
		{Name: "local-b", Scope: "local", Hostname: "alpha-host", AgentCmd: "codex"},
		{Name: "remote-a", Scope: "remote", Hostname: "beta-host", AgentCmd: "claude"},
	}
	views := deriveAgentViews(rows, nil, nil)
	groups := groupAgentViews(views)
	if len(groups) != 2 {
		t.Fatalf("groups = %+v, want 2", groups)
	}
	if groups[0].Header != "Local · alpha-host" || len(groups[0].Agents) != 2 {
		t.Fatalf("first group = %+v", groups[0])
	}
	if groups[1].Header != "Remote · beta-host" || len(groups[1].Agents) != 1 {
		t.Fatalf("second group = %+v", groups[1])
	}
}

func TestHiddenCountDerivation(t *testing.T) {
	rows := []agentRow{{Name: "alpha"}, {Name: "beta"}, {Name: "gamma"}}
	hidden := map[string]bool{"beta": true, "gamma": true}
	got := hiddenAgentCount(rows, func(row agentRow) bool { return hidden[row.Name] })
	if got != 2 {
		t.Fatalf("hidden count = %d, want 2", got)
	}
	m := model{rows: rows, hiddenAgents: hidden}
	if got := m.hiddenCount(); got != 2 {
		t.Fatalf("model hidden count = %d, want 2", got)
	}
}

func TestStatusDotMapping(t *testing.T) {
	cases := []struct {
		status string
		color  string
	}{
		{"idle", string(palette.Green)},
		{"waiting", string(palette.Yellow)},
		{"failed", string(palette.Red)},
		{"mystery", string(palette.Overlay0)},
	}
	for _, tc := range cases {
		got := statusDotStyle(tc.status).GetForeground()
		if got == nil || string(got.(lipgloss.Color)) != tc.color {
			t.Fatalf("statusDotStyle(%q) foreground = %v, want %s", tc.status, got, tc.color)
		}
		if dot := statusDot(tc.status); !strings.Contains(dot, "●") {
			t.Fatalf("statusDot(%q) = %q, want dot", tc.status, dot)
		}
	}
}
