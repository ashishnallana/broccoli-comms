package main

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

type ViewportPanel struct {
	Width  int
	Height int
	Offset int
	Bg     lipgloss.Color
	Lines  []string
}

func NewViewportPanel(width, height, offset int, bg lipgloss.Color, lines []string) ViewportPanel {
	return ViewportPanel{Width: max(1, width), Height: max(1, height), Offset: offset, Bg: bg, Lines: lines}
}

func (v ViewportPanel) ClampedOffset() int {
	return clampViewportOffset(v.Offset, len(v.Lines), v.Height)
}

func (v ViewportPanel) View() string {
	if len(v.Lines) == 0 {
		return ""
	}
	offset := v.ClampedOffset()
	end := min(len(v.Lines), offset+max(1, v.Height))
	return lipgloss.NewStyle().Width(v.Width).Height(v.Height).MaxHeight(v.Height).Background(v.Bg).Render(strings.Join(v.Lines[offset:end], "\n"))
}

func viewportPageSize(height int) int {
	return max(1, height/2)
}

func viewportBottomOffset(total, visible int) int {
	return max(0, total-max(1, visible))
}

func clampViewportOffset(offset, total, visible int) int {
	maxOffset := viewportBottomOffset(total, visible)
	if offset > maxOffset {
		return maxOffset
	}
	return max(0, offset)
}
