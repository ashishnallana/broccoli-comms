package main

import (
	"fmt"
	"strings"
)

func (m model) taskCommandPaletteView(width, height int) string {
	bg := colors.BaseBg
	innerW := max(1, width-4)
	lines := []string{
		padStyledLine(titleStyle.Render("Task commands"), innerW, bg),
		padStyledLine(mutedStyle.Render("↑/↓ select · enter run · esc close"), innerW, bg),
		bgSpaces(innerW, bg),
	}
	for i, entry := range m.taskCommandEntries() {
		rowBg := bg
		fg := colors.Text
		prefix := "  "
		if !entry.Enabled {
			fg = colors.Muted
		}
		if i == m.tasksPalette.Selected {
			rowBg = colors.SelectedBg
			fg = colors.SelectedFg
			prefix = "▸ "
		}
		status := ""
		if !entry.Enabled {
			status = " (disabled)"
		}
		line := fmt.Sprintf("%s%s%s · %s", prefix, entry.Label, status, entry.Help)
		lines = append(lines, padStyledLine(fgOnBg(fg, rowBg).Render(truncateCells(line, innerW)), innerW, rowBg))
		if len(lines) >= height {
			break
		}
	}
	return padBlock(strings.Join(lines, "\n"), width, height, 2, bg)
}
