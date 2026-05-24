package main

import (
	"strings"
	"testing"
)

func TestMarkdownRendersLinksWithURL(t *testing.T) {
	rendered := renderMarkdown("See [docs](https://example.com/docs) and https://example.com/raw", 80)
	for _, want := range []string{"docs", "https://example.com/docs", "https://example.com/raw"} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("rendered link missing %q:\n%s", want, rendered)
		}
	}
}

func TestMarkdownHighlightsFencedCode(t *testing.T) {
	rendered := renderMarkdown("```go\nfunc main() {\n  return\n}\n```", 80)
	for _, want := range []string{"func", "return", "main"} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("rendered code missing %q:\n%s", want, rendered)
		}
	}
}

func TestMarkdownCodeBlockWithoutLanguageAndBlankLinesDoesNotPanic(t *testing.T) {
	rendered := renderMarkdown("```\n\nvalue // comment\n```", 80)
	if !strings.Contains(rendered, "value") || !strings.Contains(rendered, "comment") {
		t.Fatalf("rendered code missing content:\n%s", rendered)
	}
}
