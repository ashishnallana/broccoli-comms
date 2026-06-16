package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestComponentCharacterizationComposerMessagePaletteAndRows(t *testing.T) {
	t.Run("composer input uses shared input surface and mode prefix", func(t *testing.T) {
		m := model{mode: simpleView, width: 100, composer: []rune("hello reusable components")}
		box := m.composerInputBox(48)
		if lineCount(box) != 3 {
			t.Fatalf("composer input should keep blank/content/blank structure, got %d lines:\n%s", lineCount(box), box)
		}
		if !strings.Contains(box, "/msg") || !strings.Contains(box, "hello reusable components") {
			t.Fatalf("composer input missing mode prefix or draft text:\n%s", box)
		}
		for i, line := range strings.Split(box, "\n") {
			if got := lipgloss.Width(line); got != 48 {
				t.Fatalf("composer input line %d width=%d want 48: %q", i, got, line)
			}
		}
	})

	t.Run("message viewport clips to requested height and preserves scroll window", func(t *testing.T) {
		m := model{width: 100, height: 24, messages: []tracker.Message{
			{Sender: "alpha", Body: "first message body"},
			{Sender: "beta", Body: "second message body"},
			{Sender: "gamma", Body: "third message body"},
		}, messageOffset: 3}
		view := m.messageViewWithHeight(50, 4)
		if got := lineCount(view); got != 4 {
			t.Fatalf("message viewport height=%d want 4:\n%s", got, view)
		}
		if strings.Contains(view, "first message body") || !strings.Contains(view, "second message body") {
			t.Fatalf("message viewport should render scrolled window, got:\n%s", view)
		}
	})

	t.Run("global command palette keeps modal title and selected action bounded", func(t *testing.T) {
		m := model{width: 100, height: 24, rows: []agentRow{{Name: "alpha", Scope: "local"}}, local: &fakeLocal{}}
		m.commandPalette.Open = true
		palette := m.commandPaletteView(80, 16)
		for _, want := range []string{"Command palette", "Refresh agents", "esc close"} {
			if !strings.Contains(palette, want) {
				t.Fatalf("command palette missing %q:\n%s", want, palette)
			}
		}
		if got := maxRenderedLineWidth(palette); got > 80 {
			t.Fatalf("command palette width=%d > 80:\n%s", got, palette)
		}
	})

	t.Run("representative list rows keep two or three line card contracts", func(t *testing.T) {
		agentModel := model{rows: []agentRow{{Name: "alpha", Scope: "local", Status: "online", ModelType: "pi", Hostname: "host"}}, selected: 0}
		agent := agentModel.agentCard(agentModel.rows[0], true, 40)
		if got := lineCount(agent); got != agentCardHeight {
			t.Fatalf("agent row lines=%d want %d:\n%s", got, agentCardHeight, agent)
		}
		assertRenderedContainsAll(t, "agent row", agent, "alpha", "online", "pi")

		taskLines := taskRowLines(taskRecord{TaskID: "task-1", Title: "Implement component shell", Status: "working", Priority: "P1", AssignedAgent: "broccoli-agent", NextStep: "extract helpers"}, true, false, 72)
		if len(taskLines) != 2 {
			t.Fatalf("task row lines=%d want 2: %#v", len(taskLines), taskLines)
		}
		assertRenderedContainsAll(t, "task row", strings.Join(taskLines, "\n"), "task-1", "Implement component shell", "working", "broccoli-agent", "next extract helpers")
		for i, line := range taskLines {
			if got := lipgloss.Width(line); got != 72 {
				t.Fatalf("task row line %d width=%d want 72: %q", i, got, line)
			}
		}

		memoryLines := memoryRowLines(memoryRecord{MemoryID: "mem-1", Status: "pending", Version: 2, Type: "habit", SubjectAgent: "broccoli-agent", Title: "Run tests", Body: "Always run focused tests."}, true, 72)
		if len(memoryLines) != 3 {
			t.Fatalf("memory row lines=%d want 3: %#v", len(memoryLines), memoryLines)
		}
		assertRenderedContainsAll(t, "memory row", strings.Join(memoryLines, "\n"), "Run tests", "pending", "habit", "broccoli-agent", "Always run focused tests.")
		for i, line := range memoryLines {
			if got := lipgloss.Width(line); got != 72 {
				t.Fatalf("memory row line %d width=%d want 72: %q", i, got, line)
			}
		}
	})
}

func assertRenderedContainsAll(t *testing.T, name, rendered string, wants ...string) {
	t.Helper()
	for _, want := range wants {
		if !strings.Contains(rendered, want) {
			t.Fatalf("%s missing %q:\n%s", name, want, rendered)
		}
	}
}
