package main

import (
	"strings"
	"testing"
)

func TestCommandPaletteComponentRendersGlobalAndTaskPalettes(t *testing.T) {
	items := []CommandPaletteItem{
		{Title: "Switch agent", Subtitle: "Select next", Category: "Agents", Shortcut: "run", Enabled: true},
		{Title: "Delete task", Subtitle: "not supported", Category: "Tasks", Shortcut: "disabled", Enabled: false},
	}
	global := CommandPaletteComponent{Title: "Command palette", Help: "esc close", Placeholder: "type to filter commands…", Items: items, Selected: 0, Width: 100, Height: 20, Popup: true}.View()
	for _, want := range []string{"Command palette", "type to filter commands", "AGENTS", "Switch agent", "run"} {
		if !strings.Contains(global, want) {
			t.Fatalf("global palette missing %q:\n%s", want, global)
		}
	}

	task := CommandPaletteComponent{Title: "Task commands", Help: "↑/↓ select · enter run · esc close", Items: items, Selected: 1, Width: 80, Height: 8}.View()
	for _, want := range []string{"Task commands", "enter run", "Switch agent", "Delete task (disabled)", "not supported"} {
		if !strings.Contains(task, want) {
			t.Fatalf("task palette missing %q:\n%s", want, task)
		}
	}
}
