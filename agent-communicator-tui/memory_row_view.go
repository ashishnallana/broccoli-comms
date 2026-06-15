package main

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

type memoryRowTheme struct {
	Bg lipgloss.Color
	Fg lipgloss.Color
}

func memoryRowThemeFor(mem memoryRecord, selected bool) memoryRowTheme {
	if selected {
		return memoryRowTheme{Bg: colors.SelectedBg, Fg: colors.SelectedFg}
	}
	switch strings.ToLower(strings.TrimSpace(mem.Status)) {
	case "pending":
		return memoryRowTheme{Bg: colors.PanelBgAlt, Fg: colors.Warning}
	case "active", "approved":
		return memoryRowTheme{Bg: colors.BaseBg, Fg: colors.Text}
	default:
		return memoryRowTheme{Bg: colors.BaseBg, Fg: colors.Muted}
	}
}

func memoryStatusMarker(mem memoryRecord) string {
	switch strings.ToLower(strings.TrimSpace(mem.Status)) {
	case "pending":
		return "◔"
	case "active", "approved":
		return "●"
	case "revoked", "rejected", "superseded":
		return "×"
	default:
		return "○"
	}
}

func memoryStatusColor(status string) lipgloss.Color {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "pending":
		return colors.Warning
	case "active", "approved":
		return colors.Success
	case "revoked", "rejected", "superseded":
		return colors.Error
	default:
		return colors.Muted
	}
}

func memoryTypeColor(memoryType string) lipgloss.Color {
	switch strings.ToLower(strings.TrimSpace(memoryType)) {
	case "fact":
		return colors.Accent
	case "habit":
		return colors.Success
	case "episode":
		return colors.AccentAlt
	case "expertise":
		return colors.Warning
	case "skill":
		return colors.Info
	default:
		return colors.Muted
	}
}

func memoryActionHelp(mem memoryRecord) string {
	switch strings.ToLower(strings.TrimSpace(mem.Status)) {
	case "pending":
		return "a approve · d reject · e edit in editor · n new"
	case "active", "approved":
		if mem.Version > 1 {
			return "d revoke · R rollback · e edit in editor · n new"
		}
		return "d revoke · rollback unavailable (v1) · e edit in editor · n new"
	default:
		return "e edit in editor · n new"
	}
}

func memorySourceVersionHint(mem memoryRecord) string {
	parts := []string{}
	if mem.SourceTaskID != "" {
		parts = append(parts, "src "+mem.SourceTaskID)
	}
	if mem.Scope != "" {
		parts = append(parts, "scope "+mem.Scope)
	}
	if mem.Version > 0 {
		parts = append(parts, fmt.Sprintf("v%d", mem.Version))
	}
	return strings.Join(parts, " · ")
}

func memoryPreviewText(mem memoryRecord) string {
	preview := strings.Join(strings.Fields(mem.Body), " ")
	if preview == "" && len(mem.Tags) > 0 {
		preview = "tags: " + strings.Join(mem.Tags, ", ")
	}
	if preview == "" {
		preview = "—"
	}
	return preview
}

func memoryRowLines(mem memoryRecord, selected bool, width int) []string {
	theme := memoryRowThemeFor(mem, selected)
	style := fgOnBg(theme.Fg, theme.Bg)
	muted := fgOnBg(colors.Muted, theme.Bg)
	previewStyle := muted
	if selected {
		previewStyle = fgOnBg(colors.TextStrong, theme.Bg)
	}
	prefix := "  "
	if selected {
		prefix = "▸ "
	}
	title := firstNonEmpty(mem.Title, mem.MemoryID)
	line1 := prefix + title
	line3 := "  " + memoryPreviewText(mem)
	return []string{
		padStyledLine(style.Bold(selected).Render(truncateCells(line1, width)), width, theme.Bg),
		memoryMetadataLine(mem, width, theme.Bg, true),
		padStyledLine(previewStyle.Render(truncateCells(line3, width)), width, theme.Bg),
	}
}

func memoryMetadataLine(mem memoryRecord, width int, bg lipgloss.Color, includeID bool) string {
	muted := fgOnBg(colors.Muted, bg)
	separator := muted.Render(" · ")
	parts := []string{
		bgOnly(bg).Render("  ") + fgOnBg(memoryStatusColor(mem.Status), bg).Bold(true).Render(memoryStatusMarker(mem)+" "+firstNonEmpty(mem.Status, "unknown")),
	}
	if includeID && mem.MemoryID != "" {
		parts = append(parts, muted.Render(mem.MemoryID))
	}
	parts = append(parts,
		fgOnBg(memoryTypeColor(mem.Type), bg).Bold(true).Render(firstNonEmpty(mem.Type, "unknown")),
		fgOnBg(colors.AccentStrong, bg).Bold(true).Render(memoryRecordAgentName(mem)),
	)
	if hint := memorySourceVersionHint(mem); hint != "" {
		parts = append(parts, muted.Render(hint))
	}
	return padStyledLine(truncateCells(strings.Join(parts, separator), width), width, bg)
}

func compactNonEmpty(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			out = append(out, value)
		}
	}
	return out
}

func memoryInlineDetailLines(mem memoryRecord, width int) []string {
	bg := colors.BaseBg
	muted := fgOnBg(colors.Muted, bg)
	previewStyle := fgOnBg(colors.TextStrong, bg)
	accent := fgOnBg(colors.Accent, bg).Bold(true)
	lines := []string{
		padStyledLine(accent.Render(truncateCells("Selected · "+firstNonEmpty(mem.Title, mem.MemoryID), width)), width, bg),
		memoryMetadataLine(mem, width, bg, false),
		padStyledLine(muted.Render(truncateCells(memoryActionHelp(mem), width)), width, bg),
	}
	if mem.Body != "" {
		lines = append(lines, padStyledLine(previewStyle.Render(truncateCells(memoryPreviewText(mem), width)), width, bg))
	}
	return lines
}
