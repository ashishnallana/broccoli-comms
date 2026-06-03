package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func assertNoResetToRawSpace(t *testing.T, name, rendered string) {
	t.Helper()
	if strings.Contains(rendered, "\x1b[0m ") {
		t.Fatalf("%s contains a reset followed by a raw space, which can expose the terminal background: %q", name, rendered)
	}
}

func assertContains(t *testing.T, name, rendered string, wants ...string) {
	t.Helper()
	for _, want := range wants {
		if !strings.Contains(rendered, want) {
			t.Fatalf("%s missing %q: %q", name, want, rendered)
		}
	}
}

func forceTrueColor(t *testing.T) {
	t.Helper()
	previous := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	t.Cleanup(func() { lipgloss.SetColorProfile(previous) })
}

func TestComposerCriticalSegmentsKeepInputBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{composer: []rune("hello world")}
	assertNoResetToRawSpace(t, "composer with text", m.composerInputBox(40))

	m = model{}
	assertNoResetToRawSpace(t, "empty composer", m.composerInputBox(40))
}

func TestAgentCardCriticalSegmentsKeepCardBackground(t *testing.T) {
	forceTrueColor(t)
	row := agentRow{Name: "alpha", Scope: "local", Status: "idle", ModelType: "pi"}
	m := model{}
	assertNoResetToRawSpace(t, "normal agent card", m.agentCard(row, false, 40))
	assertNoResetToRawSpace(t, "selected agent card", m.agentCard(row, true, 40))

	m = model{unreadCounts: map[string]int{conversationKey(row): 2}}
	assertNoResetToRawSpace(t, "unread agent card", m.agentCard(row, false, 40))
}

func TestMessageTimelineCriticalSegmentsKeepBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{messages: []tracker.Message{{Sender: "alice", Body: "hello world"}}}
	incoming := strings.Join(m.messageLinesForWidth(80), "\n")
	assertNoResetToRawSpace(t, "incoming message", incoming)

	m = model{messages: []tracker.Message{{Sender: "You", Body: "hello world", Read: true}}}
	outgoing := strings.Join(m.messageLinesForWidth(80), "\n")
	assertNoResetToRawSpace(t, "outgoing message", outgoing)

	m = model{messages: []tracker.Message{{Sender: "alice", Body: "See [docs](https://example.com/docs) and `code`\n```go\nfunc main() { return \"hello\" 42 // comment }\n```"}}}
	markdown := strings.Join(m.messageLinesForWidth(90), "\n")
	assertNoResetToRawSpace(t, "markdown message", markdown)
	assertContains(t, "markdown message", markdown, "func", "return", "\"hello\"", "42", "comment", "48;2;36;40;59")
}

func TestMarkdownCodeHighlightingKeepsTokenColorsWithBackground(t *testing.T) {
	forceTrueColor(t)
	rendered := highlightCodeLine(`func main() { return "hello" 42 // comment }`, "go", colors.PanelBgAlt)
	assertNoResetToRawSpace(t, "highlighted code", rendered)
	assertContains(t, "highlighted code", rendered,
		"1;38;2;187;154;247;48;2;36;40;59mfunc",
		"1;38;2;187;154;247;48;2;36;40;59mreturn",
		"38;2;158;206;105;48;2;36;40;59m\"hello\"",
		"38;2;121;162;247;48;2;36;40;59m42",
		"3;38;2;115;121;162;48;2;36;40;59m// comment",
	)
}
