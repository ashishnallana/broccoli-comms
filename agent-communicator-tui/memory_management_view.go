package main

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

func (m model) memoryManagementView(width, height int) string {
	if width < 70 {
		return m.memoryPrimaryPanel(width, height, false)
	}
	contentW, rightW := memoryLayoutWidths(width)
	primary := m.memoryPrimaryPanel(contentW, height, true)
	right := m.memoryDetailsPanel(rightW, height)
	return lipgloss.JoinHorizontal(lipgloss.Top, primary, right)
}

func memoryLayoutWidths(width int) (int, int) {
	return contentDetailLayoutWidths(width)
}

func (m model) memoryPrimaryPanel(width, height int, wide bool) string {
	if m.memoryFormActive() {
		return m.memoryFormView(width, height)
	}
	padX := responsivePanelPaddingForWidth(width, wide)
	innerW := max(1, width-(padX*2))
	bg := colors.BaseBg
	title := titleStyle.Render("Memory Management")
	query := m.memoryFilterInputBox(innerW)
	helpText := "↑/↓ select · / search · s/t/g filters · n new · e edit EDITOR/nvim · a approve · d reject/revoke · R rollback · r refresh"
	help := padStyledLine(mutedStyle.Render(truncateCells(helpText, innerW)), innerW, bg)
	statusLine := m.memoryConfirmationLine(innerW, bg)
	chromeH := lineCount(title) + lineCount(query) + lineCount(help) + lineCount(statusLine) + 3
	listH := max(1, height-chromeH)
	list := m.memoryListView(innerW, listH, !wide)
	body := title + "\n" + query + "\n" + help
	if statusLine != "" {
		body += "\n" + statusLine
	}
	body += "\n" + bgSpaces(innerW, bg) + "\n" + list
	return lipgloss.NewStyle().Width(width).Height(height).MaxWidth(width).MaxHeight(height).Padding(1, padX, 0, padX).Background(bg).Render(truncateLines(body, max(1, height-1)))
}

func (m model) memoryFilterInputBox(width int) string {
	return NewTextInputSurface(width, m.width, colors.InputBg, m.memoryFilterText(), "search memory…", m.memorySearchFocused).View()
}

func (m model) memoryConfirmationLine(width int, bg lipgloss.Color) string {
	if !m.memoryConfirm.Active() {
		return ""
	}
	for _, mem := range m.memoryItems {
		if m.memoryConfirmationMatches(mem, m.memoryConfirm.Action) {
			return padStyledLine(fgOnBg(colors.Warning, bg).Render(truncateCells(memoryActionConfirmText(mem, m.memoryConfirm.Action), width)), width, bg)
		}
	}
	return ""
}

func (m model) memoryListView(width, height int, includePreview bool) string {
	bg := colors.BaseBg
	if m.memoryLoading {
		return padStyledLine(fgOnBg(colors.Muted, bg).Render("Loading memory…"), width, bg)
	}
	if m.memoryErr != nil {
		return padStyledLine(fgOnBg(colors.Error, bg).Render(truncateCells("Memory load failed · r retry · "+m.memoryErr.Error(), width)), width, bg)
	}
	items := m.filteredMemoryItems()
	if len(items) == 0 {
		return padStyledLine(fgOnBg(colors.Muted, bg).Render("No memory records match this filter."), width, bg)
	}
	visibleRows := memoryVisibleRowsForHeight(height)
	start := min(max(0, m.memoryOffset), max(0, len(items)-visibleRows))
	end := min(len(items), start+visibleRows)
	lines := []string{}
	for i := start; i < end && len(lines) < height; i++ {
		mem := items[i]
		selected := i == m.memorySelected
		for _, line := range memoryRowLines(mem, selected, width) {
			if len(lines) >= height {
				break
			}
			lines = append(lines, line)
		}
		if includePreview && selected {
			for _, line := range memoryInlineDetailLines(mem, width) {
				if len(lines) >= height {
					break
				}
				lines = append(lines, line)
			}
		}
		if i < end-1 && len(lines) < height {
			lines = append(lines, bgSpaces(width, bg))
		}
	}
	return lipgloss.NewStyle().Width(width).Height(height).MaxHeight(height).Background(bg).Render(strings.Join(lines, "\n"))
}

func (m model) memoryFilterText() string {
	query := strings.TrimSpace(string(m.memoryQuery))
	if query == "" {
		query = "search memory…"
	}
	prefix := "⌕ "
	if m.memorySearchFocused {
		prefix = "⌕ "
	}
	parts := []string{
		prefix + query,
		"status " + memoryFilterLabel(m.memoryStatusFilter),
		"type " + memoryFilterLabel(m.memoryTypeFilter),
	}
	if strings.TrimSpace(m.memoryAgentFilter) != "" {
		parts = append(parts, "agent "+m.memoryAgentFilter)
	}
	return strings.Join(parts, "  ·  ")
}

func (m model) memoryDetailsPanel(width, height int) string {
	bg := colors.RightColumnBg
	innerW := max(1, width-4)
	muted := fgOnBg(colors.Muted, bg)
	accent := fgOnBg(colors.Accent, bg).Bold(true)
	lines := []string{
		padStyledLine(accent.Render("Memory details"), innerW, bg),
	}
	if mem, ok := m.selectedMemoryRecord(); ok {
		lines = append(lines,
			padStyledLine(fgOnBg(colors.TextStrong, bg).Render(truncateCells(firstNonEmpty(mem.Title, mem.MemoryID), innerW)), innerW, bg),
			memoryMetadataLine(mem, innerW, bg, false),
			padStyledLine(muted.Render(truncateCells("id "+mem.MemoryID, innerW)), innerW, bg),
			padStyledLine(muted.Render(""), innerW, bg),
			padStyledLine(accent.Render("Filters"), innerW, bg),
			padStyledLine(muted.Render(truncateCells(m.memoryFilterText(), innerW)), innerW, bg),
			padStyledLine(accent.Render("Actions"), innerW, bg),
		)
		lines = append(lines, padStyledLine(muted.Render(truncateCells(memoryActionHelp(mem), innerW)), innerW, bg))
		if m.memoryConfirmationMatches(mem, m.memoryConfirm.Action) {
			lines = append(lines, padStyledLine(fgOnBg(colors.Warning, bg).Render(truncateCells(memoryActionConfirmText(mem, m.memoryConfirm.Action), innerW)), innerW, bg))
		}
		if mem.Body != "" {
			previewStyle := fgOnBg(colors.TextStrong, bg)
			lines = append(lines, padStyledLine(muted.Render(""), innerW, bg), padStyledLine(accent.Render("Preview"), innerW, bg))
			for _, line := range wrapLine(strings.ReplaceAll(mem.Body, "\n", " "), innerW) {
				if len(lines) >= max(1, height-2) {
					break
				}
				lines = append(lines, padStyledLine(previewStyle.Render(truncateCells(line, innerW)), innerW, bg))
			}
		}
	} else {
		lines = append(lines, padStyledLine(muted.Render("No memory selected."), innerW, bg), padStyledLine(muted.Render("n new memory"), innerW, bg))
	}
	body := strings.Join(lines, "\n")
	return lipgloss.NewStyle().Width(width).Height(height).MaxHeight(height).Padding(1, 2).Background(bg).Render(truncateLines(body, max(1, height-1)))
}
