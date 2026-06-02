package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestMessageLinesHighlightSenderAndSeparateMessages(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "alice", Timestamp: "t1", Body: "**hello**"}, {Sender: "bob", Body: "second"}}}
	lines := strings.Join(m.messageLinesForWidth(80), "\n")
	for _, want := range []string{"alice", "t1", "hello", "┃", "bob", "second"} {
		if !strings.Contains(lines, want) {
			t.Fatalf("message lines missing %q:\n%s", want, lines)
		}
	}
}

func TestMarkdownTablesRenderAsAlignedRows(t *testing.T) {
	body := "# Test Markdown Report\n\n| ID | Name | Status |\n|---:|---|---|\n| 1 | Alpha | Complete |"
	view := model{height: 24, messages: []tracker.Message{{Sender: "agent", Body: body}}}.messageView(100)
	for _, want := range []string{"Test Markdown Report", "│ ID", "Alpha", "Complete", "├"} {
		if !strings.Contains(view, want) {
			t.Fatalf("rendered markdown missing %q:\n%s", want, view)
		}
	}
}

func TestMessageLinesWrapLongMessageBody(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "alice", Body: "one two three four five six seven"}}}
	lines := m.messageLinesForWidth(16)
	joined := strings.Join(lines, "\n")
	if !strings.Contains(joined, "one") || !strings.Contains(joined, "four") {
		t.Fatalf("expected wrapped lines, got:\n%s", joined)
	}
	for _, line := range lines {
		if lipgloss.Width(line) > 15 {
			t.Fatalf("line width %d > 15: %q", lipgloss.Width(line), line)
		}
	}
}

func TestMessageViewportScrollsIndependently(t *testing.T) {
	m := model{height: 8, messageOffset: 3, messages: []tracker.Message{{Sender: "a", Body: "one\ntwo\nthree\nfour\nfive"}}}
	view := m.messageView(80)
	if strings.Contains(view, "one") || !strings.Contains(view, "three") {
		t.Fatalf("unexpected scrolled message view:\n%s", view)
	}
}

func TestTypingKeepsMessagesPinnedToTopAndAppendsComposer(t *testing.T) {
	m := model{height: 8, messageOffset: 2, messages: []tracker.Message{{Sender: "a", Body: "one\ntwo\nthree\nfour\nfive"}}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("x")})
	m = updated.(model)
	if string(m.composer) != "x" {
		t.Fatalf("composer = %q, want x", string(m.composer))
	}
	if m.messageOffset != 0 {
		t.Fatalf("messageOffset = %d, want top 0", m.messageOffset)
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeySpace})
	m = updated.(model)
	if string(m.composer) != "x " {
		t.Fatalf("composer after space = %q, want x-space", string(m.composer))
	}
}

func TestCtrlUCtrlDClampMessageScroll(t *testing.T) {
	m := model{height: 8, messages: []tracker.Message{{Sender: "a", Body: "one\ntwo\nthree\nfour\nfive"}}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyCtrlD})
	m = updated.(model)
	wantOlder := clampMessageOffset(messagePageSize(m.height), len(m.messageLinesForWidth(m.messageContentWidth())), m.messageVisibleLines())
	if m.messageOffset != wantOlder {
		t.Fatalf("ctrl+d offset = %d, want clamped %d", m.messageOffset, wantOlder)
	}
	for i := 0; i < 10; i++ {
		updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlD})
		m = updated.(model)
	}
	wantMax := messageBottomOffset(len(m.messageLinesForWidth(m.messageContentWidth())), m.messageVisibleLines())
	if m.messageOffset != wantMax {
		t.Fatalf("repeated ctrl+d offset = %d, want %d", m.messageOffset, wantMax)
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlU})
	m = updated.(model)
	if m.messageOffset != max(0, wantMax-messagePageSize(m.height)) {
		t.Fatalf("ctrl+u offset = %d", m.messageOffset)
	}
}

func TestViewWideAndNarrowIncludeCoreRegions(t *testing.T) {
	m := model{width: 120, height: 30, rows: []agentRow{{Name: "alpha", Scope: "local", Status: "idle", CWD: "/repo"}}, messages: []tracker.Message{{Sender: "agent", Body: "**hello**"}}}
	wide := m.View()
	for _, want := range []string{"Switch agent", "Conversation", "alpha", "hello"} {
		if !strings.Contains(wide, want) {
			t.Fatalf("wide view missing %q:\n%s", want, wide)
		}
	}
	if strings.Contains(wide, "Selected") {
		t.Fatalf("wide view should be two-panel only:\n%s", wide)
	}
	if got := maxRenderedLineWidth(wide); got > m.width {
		t.Fatalf("wide view width = %d, want <= %d", got, m.width)
	}
	m.width = 48
	narrow := m.View()
	if !strings.Contains(narrow, "Conversation") || strings.Contains(narrow, "Selected") {
		t.Fatalf("unexpected narrow view:\n%s", narrow)
	}
	if got := maxRenderedLineWidth(narrow); got > m.width {
		t.Fatalf("narrow view width = %d, want <= %d", got, m.width)
	}
}

func TestWideComposerSitsNearBottom(t *testing.T) {
	m := model{width: 120, height: 30, rows: []agentRow{{Name: "alpha", Scope: "local"}}, messages: []tracker.Message{{Sender: "agent", Body: "hello"}}}
	view := m.View()
	composerIndex := strings.LastIndex(view, "/msg")
	messageIndex := strings.Index(view, "hello")
	if composerIndex < 0 || messageIndex < 0 || composerIndex < messageIndex {
		t.Fatalf("composer should render below timeline near bottom:\n%s", view)
	}
}

func TestLayoutWidthsConsumeAvailableWidth(t *testing.T) {
	m := model{width: 160}
	chat, right, extra := m.layoutWidths()
	if extra != 0 {
		t.Fatalf("extra panel = %d, want 0 for two-column layout", extra)
	}
	if got := chat + right; got != m.width {
		t.Fatalf("two-column width = %d, want %d", got, m.width)
	}
	if right != 42 || chat != 118 {
		t.Fatalf("chat/right = %d/%d, want 118/42", chat, right)
	}
}

func mustUpdate(m model, msg tea.Msg) (model, tea.Cmd) {
	updated, cmd := m.Update(msg)
	return updated.(model), cmd
}

func maxRenderedLineWidth(s string) int {
	maxWidth := 0
	for _, line := range strings.Split(s, "\n") {
		if width := lipgloss.Width(line); width > maxWidth {
			maxWidth = width
		}
	}
	return maxWidth
}
