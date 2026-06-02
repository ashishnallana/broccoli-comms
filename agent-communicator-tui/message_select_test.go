package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestUpDownSelectsMessageAndTypingFocusesComposer(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "a", Body: "one"}, {Sender: "b", Body: "two"}}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = updated.(model)
	if m.messageSelected != 1 || !m.messageFocused {
		t.Fatalf("selected=%d focused=%v", m.messageSelected, m.messageFocused)
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("x")})
	m = updated.(model)
	if string(m.composer) != "x" || m.messageFocused {
		t.Fatalf("composer=%q focused=%v", string(m.composer), m.messageFocused)
	}
}

func TestComposerShowsCursorOnlyWhenInputFocused(t *testing.T) {
	m := model{}
	view := m.composerView(30)
	if !strings.Contains(view, "█") {
		t.Fatal("focused composer should show cursor")
	}
	if strings.Index(view, "█") > strings.Index(view, "type message") {
		t.Fatalf("cursor should appear before placeholder: %q", view)
	}
	m.cursorHidden = true
	if strings.Contains(m.composerView(30), "█") {
		t.Fatal("blink-hidden composer should hide cursor")
	}
	m.cursorHidden = false
	m.messageFocused = true
	if strings.Contains(m.composerView(30), "█") {
		t.Fatal("message focus should hide composer cursor")
	}
}

func TestMessageViewMarksSelectedMessageWithRail(t *testing.T) {
	m := model{width: 80, height: 20, messageSelected: 0, messages: []tracker.Message{{Sender: "a", Body: "one"}, {Sender: "b", Body: "two"}}}
	view := m.messageView(80)
	if !strings.Contains(view, "┃") || strings.Contains(view, "● b") || strings.Contains(view, "╔") {
		t.Fatalf("view = %q", view)
	}
}

func TestFormatMessageForEditor(t *testing.T) {
	content := formatMessageForEditor(tracker.Message{Sender: "alice", Timestamp: "2026-01-01T00:00:00Z", Body: "hello"})
	if !strings.Contains(content, "# Message from alice") || !strings.Contains(content, "hello") {
		t.Fatalf("content = %q", content)
	}
}
