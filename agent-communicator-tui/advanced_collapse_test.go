package main

import (
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestAdvancedViewCollapsesUnselectedNonLastMessages(t *testing.T) {
	m := model{mode: advancedView, width: 100, height: 34, messageSelected: 1, allMessages: []tracker.Message{
		{Sender: "a", Body: "a1\na2\na3\na4\na5", Timestamp: "2026-01-01T00:00:00Z"},
		{Sender: "b", Body: "b1\nb2\nb3\nb4", Timestamp: "2026-01-01T00:01:00Z"},
		{Sender: "c", Body: "c1\nc2\nc3\nc4", Timestamp: "2026-01-01T00:02:00Z"},
	}}
	view := m.messageView(100)
	if strings.Contains(view, "a4") || strings.Contains(view, "a5") {
		t.Fatalf("first unselected message should be collapsed:\n%s", view)
	}
	for _, want := range []string{"b4", "c4", "…"} {
		if !strings.Contains(view, want) {
			t.Fatalf("view missing %q:\n%s", want, view)
		}
	}
}

func TestSimpleViewDoesNotCollapseMessages(t *testing.T) {
	m := model{width: 100, height: 20, messages: []tracker.Message{{Sender: "a", Body: "a1\na2\na3\na4"}}}
	view := m.messageView(100)
	if !strings.Contains(view, "a4") {
		t.Fatalf("simple view should show full message:\n%s", view)
	}
}
