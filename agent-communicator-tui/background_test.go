package main

import (
	"strconv"
	"strings"
	"testing"
	"unicode/utf8"

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

func assertVisibleCellsHaveBackground(t *testing.T, name, rendered string) {
	t.Helper()
	bgActive := false
	for i := 0; i < len(rendered); {
		if rendered[i] == '\x1b' && i+1 < len(rendered) && rendered[i+1] == '[' {
			end := i + 2
			for end < len(rendered) && rendered[end] != 'm' {
				end++
			}
			if end < len(rendered) {
				bgActive = applySGRBackgroundState(bgActive, rendered[i+2:end])
				i = end + 1
				continue
			}
		}
		r, size := utf8.DecodeRuneInString(rendered[i:])
		if r == '\n' {
			bgActive = false
			i += size
			continue
		}
		if r != '\r' && r != '\t' && !bgActive {
			t.Fatalf("%s has visible cell %q without active background near %q in %q", name, r, rendered[max(0, i-20):min(len(rendered), i+20)], rendered)
		}
		i += size
	}
}

func applySGRBackgroundState(bgActive bool, params string) bool {
	if params == "" {
		return false
	}
	parts := strings.Split(params, ";")
	for i := 0; i < len(parts); i++ {
		code, err := strconv.Atoi(parts[i])
		if err != nil {
			continue
		}
		switch {
		case code == 0:
			bgActive = false
		case code == 49:
			bgActive = false
		case code >= 40 && code <= 47:
			bgActive = true
		case code >= 100 && code <= 107:
			bgActive = true
		case code == 48:
			bgActive = true
			if i+1 < len(parts) {
				mode, _ := strconv.Atoi(parts[i+1])
				if mode == 2 && i+4 < len(parts) {
					i += 4
				} else if mode == 5 && i+2 < len(parts) {
					i += 2
				}
			}
		}
	}
	return bgActive
}

func assertContains(t *testing.T, name, rendered string, wants ...string) {
	t.Helper()
	for _, want := range wants {
		if !strings.Contains(rendered, want) {
			t.Fatalf("%s missing %q: %q", name, want, rendered)
		}
	}
}

func assertNotContains(t *testing.T, name, rendered string, unwanted ...string) {
	t.Helper()
	for _, value := range unwanted {
		if strings.Contains(rendered, value) {
			t.Fatalf("%s unexpectedly contains %q: %q", name, value, rendered)
		}
	}
}

func renderedLineContaining(t *testing.T, rendered, needle string) string {
	t.Helper()
	for _, line := range strings.Split(rendered, "\n") {
		if strings.Contains(line, needle) {
			return line
		}
	}
	t.Fatalf("rendered output missing line containing %q: %q", needle, rendered)
	return ""
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
	selected := m.agentCard(row, true, 40)
	assertNoResetToRawSpace(t, "selected agent card", selected)
	assertContains(t, "selected agent card", selected, "48;2;167;192;128malpha")

	m.rows = []agentRow{row}
	hero := renderedLineContaining(t, m.currentAgentPanel(50, 7), "alpha")
	assertNoResetToRawSpace(t, "current agent hero", hero)
	assertContains(t, "current agent hero", hero, "48;2;167;192;128malpha")

	m = model{unreadCounts: map[string]int{conversationKey(row): 2}}
	assertNoResetToRawSpace(t, "unread agent card", m.agentCard(row, false, 40))
}

func TestRemainingForegroundOnlySegmentsKeepPanelBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{width: 100, height: 20}
	emptyMessage := strings.Join(m.messageLinesForWidth(80), "\n")
	assertNoResetToRawSpace(t, "empty message state", emptyMessage)
	assertVisibleCellsHaveBackground(t, "empty message state", emptyMessage)
	assertContains(t, "empty message state", emptyMessage, "38;2;133;146;137;48;2;44;52;59mNo messages")

	controls := m.composerModeControls(80)
	assertNoResetToRawSpace(t, "composer controls", controls)
	assertContains(t, "composer controls", controls, "38;2;133;146;137;48;2;44;52;59m/msg sends")

	m.commandPalette.Open = true
	palette := m.commandPaletteView(100, 30)
	paletteHeader := renderedLineContaining(t, palette, "Command palette")
	assertNoResetToRawSpace(t, "command palette header", paletteHeader)
	assertContains(t, "command palette header", paletteHeader, "38;2;133;146;137;48;2;44;52;59mCommand palette")

	m = model{rows: []agentRow{{Name: "alpha", Scope: "local"}}}
	switcherHeader := renderedLineContaining(t, m.switcherPanel(60, 8), "Switch agent")
	assertNoResetToRawSpace(t, "switcher header", switcherHeader)
	assertVisibleCellsHaveBackground(t, "switcher header", switcherHeader)
	assertContains(t, "switcher header", switcherHeader, "38;2;127;187;179;48;2;52;63;68mSwitch agent", "38;2;133;146;137;48;2;52;63;68m1 shown")
}

func TestMessageTimelineCriticalSegmentsKeepBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{messages: []tracker.Message{{Sender: "alice", Timestamp: "t1", Body: "hello world"}}}
	incomingLines := m.messageLinesForWidth(80)
	incoming := strings.Join(incomingLines, "\n")
	assertNoResetToRawSpace(t, "incoming message", incoming)
	assertVisibleCellsHaveBackground(t, "incoming message", incoming)
	assertContains(t, "incoming message", incoming, "48;2;52;72;63", "48;2;52;72;63malice", "48;2;52;72;63mt1", "hello world")
	for _, line := range incomingLines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		assertNotContains(t, "incoming full-width row", line, "48;2;44;52;59")
	}

	m = model{messages: []tracker.Message{{Sender: "You", Body: "hello world", Read: true}}}
	outgoing := strings.Join(m.messageLinesForWidth(80), "\n")
	assertNoResetToRawSpace(t, "outgoing message", outgoing)
	assertVisibleCellsHaveBackground(t, "outgoing message", outgoing)

	m = model{messages: []tracker.Message{{Sender: "alice", Body: "See [docs](https://example.com/docs) and `code`\n```go\nfunc main() { return \"hello\" 42 // comment }\n```"}}}
	markdown := strings.Join(m.messageLinesForWidth(90), "\n")
	assertNoResetToRawSpace(t, "markdown message", markdown)
	assertVisibleCellsHaveBackground(t, "markdown message", markdown)
	assertContains(t, "markdown message", markdown, "func", "return", "\"hello\"", "42", "comment", "48;2;52;72;63")
}

func TestMarkdownCodeHighlightingKeepsTokenColorsWithBackground(t *testing.T) {
	forceTrueColor(t)
	rendered := highlightCodeLine(`func main() { return "hello" 42 // comment }`, "go", colors.IncomingBubbleBg)
	assertNoResetToRawSpace(t, "highlighted code", rendered)
	assertContains(t, "highlighted code", rendered,
		"1;38;2;214;153;182;48;2;52;72;63mfunc",
		"1;38;2;214;153;182;48;2;52;72;63mreturn",
		"38;2;167;192;128;48;2;52;72;63m\"hello\"",
		"38;2;127;187;179;48;2;52;72;63m42",
		"3;38;2;133;146;137;48;2;52;72;63m// comment",
	)
}
