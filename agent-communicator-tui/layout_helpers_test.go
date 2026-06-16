package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
)

func TestSharedLayoutHelpersPreserveExistingSizingContracts(t *testing.T) {
	for _, width := range []int{70, 80, 120} {
		memContent, memRight := memoryLayoutWidths(width)
		taskContent, taskRight := taskLayoutWidths(width)
		if memContent != taskContent || memRight != taskRight {
			t.Fatalf("memory/task layout widths diverged at %d: memory=%d/%d task=%d/%d", width, memContent, memRight, taskContent, taskRight)
		}
		if memContent+memRight != width {
			t.Fatalf("layout widths should consume width %d, got %d + %d", width, memContent, memRight)
		}
	}
	if got := responsivePanelPadding(46, true); got != 3 {
		t.Fatalf("wide-context panel padding=%d want 3", got)
	}
	if got := responsivePanelPadding(60, false); got != 1 {
		t.Fatalf("narrow-context panel padding=%d want 1", got)
	}
	if got := responsivePanelPaddingForWidth(46, true); got != 1 {
		t.Fatalf("width-responsive panel padding=%d want 1", got)
	}
}

func TestSharedInputSurfaceRendersComposerFamilyBox(t *testing.T) {
	box := renderInputSurface(20, 100, []string{"hello"}, colors.InputBg)
	lines := strings.Split(box, "\n")
	if len(lines) != 3 {
		t.Fatalf("input surface lines=%d want 3:\n%s", len(lines), box)
	}
	for i, line := range lines {
		if got := lipgloss.Width(line); got != 20 {
			t.Fatalf("input surface line %d width=%d want 20: %q", i, got, line)
		}
	}
	if !strings.Contains(box, "hello") {
		t.Fatalf("input surface missing content:\n%s", box)
	}
}
