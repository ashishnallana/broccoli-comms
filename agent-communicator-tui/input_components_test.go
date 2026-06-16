package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
)

func TestTextInputSurfaceUsesBubblesModelAndSharedInputSurface(t *testing.T) {
	surface := NewTextInputSurface(36, 100, colors.InputBg, "agent:broccoli", "search memory…", true)
	if surface.Input.Value() != "agent:broccoli" || surface.Input.Placeholder != "search memory…" || !surface.Input.Focused() {
		t.Fatalf("text input model not configured: value=%q placeholder=%q focused=%v", surface.Input.Value(), surface.Input.Placeholder, surface.Input.Focused())
	}
	view := surface.View()
	lines := strings.Split(view, "\n")
	if len(lines) != 3 {
		t.Fatalf("text input surface lines=%d want 3:\n%s", len(lines), view)
	}
	if !strings.Contains(view, "agent:broccoli") {
		t.Fatalf("text input surface missing value:\n%s", view)
	}
	for i, line := range lines {
		if got := lipgloss.Width(line); got != 36 {
			t.Fatalf("text input surface line %d width=%d want 36: %q", i, got, line)
		}
	}
}

func TestComposerInputSurfacePreservesPrefixPlaceholderAndFullWidthFill(t *testing.T) {
	m := model{mode: simpleView, width: 100, inputMode: inputModeKeys}
	box := m.composerInputBox(44)
	if !strings.Contains(box, "/keys") || !strings.Contains(box, "type key tokens") {
		t.Fatalf("composer input surface missing mode prefix or placeholder:\n%s", box)
	}
	for i, line := range strings.Split(box, "\n") {
		if got := lipgloss.Width(line); got != 44 {
			t.Fatalf("composer input surface line %d width=%d want 44: %q", i, got, line)
		}
	}
}
