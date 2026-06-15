package main

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func TestMemoryRowLinesShowCoreFieldsAndPreview(t *testing.T) {
	mem := memoryRecord{MemoryID: "mem-1", Status: "active", Version: 3, Type: "fact", SubjectAgent: "broccoli-agent", SourceTaskID: "task-1", Scope: "global", Title: "Endpoint", Body: "Body preview for selected memory"}
	row := strings.Join(memoryRowLines(mem, false, 80), "\n")
	for _, want := range []string{"Endpoint", "active", "fact", "broccoli-agent", "src task-1", "scope global", "v3", "Body preview"} {
		if !strings.Contains(row, want) {
			t.Fatalf("memory row missing %q:\n%s", want, row)
		}
	}
}

func TestMemoryRowSelectedUsesSelectedBackgroundAndFillsWidth(t *testing.T) {
	lines := memoryRowLines(memoryRecord{MemoryID: "mem-1", Status: "pending", Version: 1, Type: "habit", Title: "Run tests"}, true, 50)
	if len(lines) != 3 {
		t.Fatalf("row lines = %d want 3", len(lines))
	}
	for _, line := range lines {
		if got := lipgloss.Width(line); got != 50 {
			t.Fatalf("selected row should fill width 50, got %d: %q", got, line)
		}
	}
}

func TestMemoryMetadataUsesDistinctStatusTypeColorsAndBoldAgent(t *testing.T) {
	previousProfile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(previousProfile)

	line := memoryMetadataLine(memoryRecord{MemoryID: "mem-1", Status: "pending", Type: "habit", SubjectAgent: "broccoli-agent"}, 100, colors.BaseBg, true)
	for label, want := range map[string]string{
		"pending status": fgOnBg(memoryStatusColor("pending"), colors.BaseBg).Bold(true).Render("◔ pending"),
		"habit type":     fgOnBg(memoryTypeColor("habit"), colors.BaseBg).Bold(true).Render("habit"),
		"agent name":     fgOnBg(colors.AccentStrong, colors.BaseBg).Bold(true).Render("broccoli-agent"),
	} {
		if !strings.Contains(line, want) {
			t.Fatalf("metadata line missing styled %s %q in %q", label, want, line)
		}
	}
}

func TestSelectedMemoryPreviewUsesTextStrong(t *testing.T) {
	previousProfile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(previousProfile)

	mem := memoryRecord{MemoryID: "mem-1", Status: "active", Type: "fact", Title: "Endpoint", Body: "Readable selected preview"}
	lines := memoryRowLines(mem, true, 80)
	want := fgOnBg(colors.TextStrong, colors.SelectedBg).Render("  Readable selected preview")
	if !strings.Contains(lines[2], want) {
		t.Fatalf("selected preview should use TextStrong on selected background; want styled preview %q in %q", want, lines[2])
	}
}

func TestMemoryPendingAndActiveRowsAreVisuallyDistinct(t *testing.T) {
	pending := strings.Join(memoryRowLines(memoryRecord{MemoryID: "mem-p", Status: "pending", Type: "habit", Title: "Pending"}, false, 80), "\n")
	active := strings.Join(memoryRowLines(memoryRecord{MemoryID: "mem-a", Status: "active", Type: "habit", Title: "Active"}, false, 80), "\n")
	if !strings.Contains(pending, "◔ pending") {
		t.Fatalf("pending row missing pending marker:\n%s", pending)
	}
	if !strings.Contains(active, "● active") {
		t.Fatalf("active row missing active marker:\n%s", active)
	}
	if pending == active {
		t.Fatalf("pending and active rows should differ")
	}
}

func TestMemoryActionHelpShowsRollbackOnlyWhenPreviousVersionExists(t *testing.T) {
	v1 := memoryActionHelp(memoryRecord{MemoryID: "mem-1", Status: "active", Version: 1})
	if strings.Contains(v1, "R rollback") || !strings.Contains(v1, "rollback unavailable") {
		t.Fatalf("version-1 active memory should not advertise executable rollback: %q", v1)
	}
	v2 := memoryActionHelp(memoryRecord{MemoryID: "mem-2", Status: "active", Version: 2})
	if !strings.Contains(v2, "R rollback") {
		t.Fatalf("version>1 active memory should advertise rollback: %q", v2)
	}
}

func TestMemoryInlineDetailShowsActionsAndStaysWithinWidth(t *testing.T) {
	lines := memoryInlineDetailLines(memoryRecord{MemoryID: "mem-1", Status: "pending", Version: 1, Title: "Pending proposal", Body: "Long preview body"}, 42)
	joined := strings.Join(lines, "\n")
	if !strings.Contains(joined, "a approve") || !strings.Contains(joined, "Pending proposal") {
		t.Fatalf("inline detail missing action/title:\n%s", joined)
	}
	for _, line := range lines {
		if got := lipgloss.Width(line); got != 42 {
			t.Fatalf("inline detail line width=%d want 42: %q", got, line)
		}
	}
}
