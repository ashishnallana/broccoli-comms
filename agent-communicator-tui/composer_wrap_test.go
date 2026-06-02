package main

import (
	"strings"
	"testing"
)

func TestComposerWrapsLongInputWithCap(t *testing.T) {
	m := model{composer: []rune(strings.Repeat("word ", 30))}
	lines := m.composerLines(24)
	if len(lines) <= 1 || len(lines) > composerMaxLines {
		t.Fatalf("composer lines = %d, lines=%q", len(lines), lines)
	}
}

func TestComposerHeightShrinksMessageViewport(t *testing.T) {
	short := model{height: 20, width: 80, composer: []rune("short")}
	long := model{height: 20, width: 80, composer: []rune(strings.Repeat("long ", 80))}
	if long.messageVisibleLines() >= short.messageVisibleLines() {
		t.Fatalf("long visible=%d short visible=%d", long.messageVisibleLines(), short.messageVisibleLines())
	}
}

func TestAdvancedComposerPrefixWrapsWithInlineMode(t *testing.T) {
	m := model{mode: advancedView, rows: []agentRow{{Name: "review-agent"}}, composer: []rune(strings.Repeat("hello ", 12))}
	view := m.composerView(28)
	if !strings.Contains(view, "/msg") || strings.Contains(view, "@review-agent") || lineCount(view) <= 1 {
		t.Fatalf("advanced composer view = %q", view)
	}
}
