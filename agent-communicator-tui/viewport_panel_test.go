package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestViewportPanelClipsAndClampsReusableContent(t *testing.T) {
	panel := NewViewportPanel(12, 3, 2, colors.BaseBg, []string{"one", "two", "three", "four", "five"})
	if got := panel.ClampedOffset(); got != 2 {
		t.Fatalf("clamped offset=%d want 2", got)
	}
	view := panel.View()
	if got := lineCount(view); got != 3 {
		t.Fatalf("viewport line count=%d want 3:\n%s", got, view)
	}
	if strings.Contains(view, "one") || !strings.Contains(view, "three") || !strings.Contains(view, "five") {
		t.Fatalf("viewport did not render expected clipped window:\n%s", view)
	}
	for i, line := range strings.Split(view, "\n") {
		if got := lipgloss.Width(line); got != 12 {
			t.Fatalf("viewport line %d width=%d want 12: %q", i, got, line)
		}
	}

	panel.Offset = 100
	if got := panel.ClampedOffset(); got != 2 {
		t.Fatalf("bottom-clamped offset=%d want 2", got)
	}
	panel.Offset = -100
	if got := panel.ClampedOffset(); got != 0 {
		t.Fatalf("top-clamped offset=%d want 0", got)
	}
}

func TestMessageStreamUsesViewportPanelWithoutChangingBubbleSelectionOrScroll(t *testing.T) {
	m := model{width: 100, height: 20, messageOffset: 2, messageSelected: 1, messages: []tracker.Message{
		{Sender: "alpha", Body: "first message"},
		{Sender: "beta", Body: "second message"},
		{Sender: "gamma", Body: "third message"},
	}}
	panel := m.messageViewportPanel(60, 5)
	if panel.Width != 60 || panel.Height != 5 || panel.Offset != 2 {
		t.Fatalf("message viewport panel dimensions/offset = %d/%d/%d", panel.Width, panel.Height, panel.Offset)
	}
	view := panel.View()
	if strings.Contains(view, "first message") || !strings.Contains(view, "second message") {
		t.Fatalf("message viewport should preserve scrolled bubble content:\n%s", view)
	}
	if !strings.Contains(view, "┃") {
		t.Fatalf("message viewport should preserve custom message bubble rail:\n%s", view)
	}

	totalLines := len(m.messageLinesForWidth(m.messageContentWidth()))
	visibleLines := m.messageVisibleLines()
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyCtrlD})
	m = updated.(model)
	want := clampViewportOffset(2+messagePageSize(20), totalLines, visibleLines)
	if m.messageOffset != want {
		t.Fatalf("ctrl-d message offset=%d want %d", m.messageOffset, want)
	}
}
