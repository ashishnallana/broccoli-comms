package main

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

func (m model) memoryFormView(width, height int) string {
	bg := colors.BaseBg
	innerW := max(1, width-4)
	title := "New memory"
	lines := []string{padStyledLine(titleStyle.Render(truncateCells(title, innerW)), innerW, bg)}
	help := "tab/↑↓ fields · enter submit · esc cancel · c-t trusted manual"
	lines = append(lines, padStyledLine(fgOnBg(colors.Muted, bg).Render(truncateCells(help, innerW)), innerW, bg))
	if m.memoryForm.Err != nil {
		lines = append(lines, padStyledLine(fgOnBg(colors.Error, bg).Render(truncateCells(m.memoryForm.Err.Error(), innerW)), innerW, bg))
	}
	for i, input := range m.memoryForm.Inputs {
		label := memoryFormLabels[i]
		if i == m.memoryForm.Index {
			label = "▸ " + label
		} else {
			label = "  " + label
		}
		lines = append(lines, padStyledLine(fgOnBg(colors.Muted, bg).Render(truncateCells(label, innerW)), innerW, bg))
		lines = append(lines, padStyledLine(truncateCells(input.View(), innerW), innerW, colors.InputBg))
	}
	trusted := "false"
	if m.memoryForm.TrustedManual {
		trusted = "true"
	}
	modeLine := "trusted-manual:" + trusted
	lines = append(lines, padStyledLine(fgOnBg(colors.Muted, bg).Render(truncateCells(modeLine, innerW)), innerW, bg))
	return lipgloss.NewStyle().Width(width).Height(height).MaxHeight(height).Padding(1, 2).Background(bg).Render(truncateLines(strings.Join(lines, "\n"), max(1, height-1)))
}
