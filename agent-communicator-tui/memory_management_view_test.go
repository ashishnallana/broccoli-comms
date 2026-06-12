package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func TestMemoryManagementTabDisablesComposer(t *testing.T) {
	m := model{mode: memoryView, rows: []agentRow{{Name: "alpha", Scope: "local"}}, inputMode: inputModeMessage}
	if m.activeTabCanCompose() {
		t.Fatal("memory tab should disable composer")
	}
	updated, cmd := m.handleKeyMsg(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("hello")})
	if cmd != nil || string(updated.composer) != "" {
		t.Fatalf("typing in memory tab should not edit composer, composer=%q cmd=%v", string(updated.composer), cmd)
	}
}

func TestMemoryManagementWideLayoutShowsRightColumn(t *testing.T) {
	m := model{mode: memoryView, width: 120, height: 30, memoryItems: []memoryRecord{{MemoryID: "mem-1", Status: "pending", Version: 2, Type: "habit", SubjectAgent: "broccoli-agent", Title: "Run tests", Body: "Always run relevant tests."}}}
	view := m.memoryManagementView(120, 24)
	for _, want := range []string{"Memory Management", "⌕ search memory", "mem-1", "Memory details", "a approve"} {
		if !strings.Contains(view, want) {
			t.Fatalf("wide memory view missing %q:\n%s", want, view)
		}
	}
}

func TestMemoryManagementNarrowLayoutHidesRightColumn(t *testing.T) {
	m := model{mode: memoryView, width: 60, height: 24, memoryItems: []memoryRecord{{MemoryID: "mem-1", Status: "active", Version: 1, Type: "fact", Title: "Endpoint", Body: "Body preview"}}}
	view := m.memoryManagementView(60, 20)
	if !strings.Contains(view, "Memory Management") || !strings.Contains(view, "mem-1") {
		t.Fatalf("narrow memory view missing primary content:\n%s", view)
	}
	if strings.Contains(view, "Memory details") {
		t.Fatalf("narrow memory view should hide right details column:\n%s", view)
	}
}

func TestMemoryManagementRenderedLinesStayWithinWidth(t *testing.T) {
	items := []memoryRecord{{MemoryID: "mem-1", Status: "active", Version: 1, Type: "fact", Title: "A very long title that should not force horizontal scrolling", Body: "Body preview"}}
	for _, width := range []int{60, 70, 72} {
		m := model{mode: memoryView, width: width, height: 24, memoryItems: items}
		view := m.memoryManagementView(width, 20)
		for i, line := range strings.Split(view, "\n") {
			if got := lipgloss.Width(line); got > width {
				t.Fatalf("memory view line width=%d > %d at terminal width %d line %d: %q\n%s", got, width, width, i, line, view)
			}
		}
	}
}

func TestMemoryManagementViewUsesWidthArgumentForWideLayout(t *testing.T) {
	m := model{mode: memoryView, width: 120, height: 24, memoryItems: []memoryRecord{{MemoryID: "mem-1", Status: "pending", Version: 1, Type: "habit", Title: "Plan"}}}
	view := m.memoryManagementView(70, 20)
	for i, line := range strings.Split(view, "\n") {
		if got := lipgloss.Width(line); got > 70 {
			t.Fatalf("memory view should honor width argument; line width=%d > 70 at line %d: %q\n%s", got, i, line, view)
		}
	}
}
