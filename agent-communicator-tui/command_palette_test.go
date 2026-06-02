package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestCtrlOOpensPaletteAndCtrlPNavigatesPrevious(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}}, selected: 1, local: &fakeLocal{}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlP})
	m = updated.(model)
	if m.commandPalette.Open || m.selected != 0 || cmd == nil {
		t.Fatalf("ctrl+p should navigate previous, selected=%d open=%v cmd=%v", m.selected, m.commandPalette.Open, cmd)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyCtrlO})
	m = updated.(model)
	if !m.commandPalette.Open || cmd != nil {
		t.Fatalf("ctrl+o should open palette, open=%v cmd=%v", m.commandPalette.Open, cmd)
	}
}

func TestCommandPaletteOverlaysWithoutRelayout(t *testing.T) {
	m := model{
		width:  120,
		height: 30,
		rows: []agentRow{
			{Name: "alpha", Scope: "local", Status: "idle", ModelType: "pi", Hostname: "host"},
			{Name: "beta", Scope: "local", Status: "idle", ModelType: "pi", Hostname: "host"},
		},
	}
	base := m.baseView()
	m.commandPalette.Open = true
	overlaid := m.View()
	if lineCount(overlaid) != lineCount(base) {
		t.Fatalf("palette changed rendered line count: base=%d overlay=%d", lineCount(base), lineCount(overlaid))
	}
	if got := maxRenderedLineWidth(overlaid); got > m.width {
		t.Fatalf("palette overlay width=%d > terminal width=%d\n%s", got, m.width, overlaid)
	}
	if !strings.Contains(overlaid, "Command palette") || !strings.Contains(overlaid, "Switch agent") {
		t.Fatalf("palette should overlay base layout while preserving command content:\n%s", overlaid)
	}
	if !strings.Contains(overlaid, "registry online") {
		t.Fatalf("right status should remain in normal layout below overlay:\n%s", overlaid)
	}
}
