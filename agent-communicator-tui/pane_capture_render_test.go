package main

import (
	"fmt"
	"os"
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func testPaneCaptureBody(lineCount int) string {
	lines := make([]string, 0, lineCount)
	for i := 1; i <= lineCount; i++ {
		lines = append(lines, fmt.Sprintf("capture-line-%02d", i))
	}
	return "### Pane Capture Snapshot from alpha\n" +
		"- **Pane:** %1\n" +
		"- **Session:** broccoli\n" +
		"- **Copy Mode:** Inactive\n" +
		"- **Captured At:** 2026-06-03T04:00:00Z\n" +
		"- **User Note:** Requested from agent-communicator\n" +
		"\n```\n" + strings.Join(lines, "\n") + "\n```\n"
}

func TestPaneCaptureDisplayUsesLastTenLinesOnly(t *testing.T) {
	display, ok := paneCaptureDisplayBody(testPaneCaptureBody(12))
	if !ok {
		t.Fatal("pane capture heuristic did not detect markdown capture")
	}
	for _, unwanted := range []string{"capture-line-01", "capture-line-02"} {
		if strings.Contains(display, unwanted) {
			t.Fatalf("display should hide earlier capture line %q:\n%s", unwanted, display)
		}
	}
	for _, want := range []string{"▣ pane capture", "… 2 earlier lines hidden", "capture-line-03", "capture-line-12"} {
		if !strings.Contains(display, want) {
			t.Fatalf("display missing %q:\n%s", want, display)
		}
	}
}

func TestPaneCaptureRenderingIsBackgroundSafeAndDoesNotMutateStoredBody(t *testing.T) {
	forceTrueColor(t)
	body := testPaneCaptureBody(12)
	m := model{messages: []tracker.Message{{Sender: "alpha", Body: body}}}
	rendered := strings.Join(m.messageLinesForWidth(100), "\n")
	assertNoResetToRawSpace(t, "pane capture message", rendered)
	assertVisibleCellsHaveBackground(t, "pane capture message", rendered)
	for _, want := range []string{"▣ pane capture", "… 2 earlier lines hidden", "capture-line-03", "capture-line-12", "48;2;52;72;63"} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("rendered pane capture missing %q:\n%s", want, rendered)
		}
	}
	for _, unwanted := range []string{"capture-line-01", "capture-line-02"} {
		if strings.Contains(rendered, unwanted) {
			t.Fatalf("rendered pane capture should hide %q:\n%s", unwanted, rendered)
		}
	}
	if m.messages[0].Body != body {
		t.Fatal("pane capture rendering mutated stored message body")
	}
}

func TestPaneCaptureHeuristicCarriesFutureMetadataTODO(t *testing.T) {
	source, err := os.ReadFile("pane_capture_render.go")
	if err != nil {
		t.Fatalf("read pane_capture_render.go: %v", err)
	}
	text := string(source)
	for _, want := range []string{"TODO", "text/x-pane-capture", "kind: pane_capture"} {
		if !strings.Contains(text, want) {
			t.Fatalf("pane capture heuristic TODO missing %q", want)
		}
	}
}
