package main

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

type CommandPaletteItem struct {
	Title    string
	Subtitle string
	Category string
	Shortcut string
	Enabled  bool
}

type CommandPaletteComponent struct {
	Title       string
	Help        string
	Query       string
	Placeholder string
	Items       []CommandPaletteItem
	Selected    int
	Offset      int
	Width       int
	Height      int
	Popup       bool
}

func (p CommandPaletteComponent) contentWidth() int {
	if p.Popup {
		return max(8, commandPaletteWidth(p.Width)-4)
	}
	return max(1, p.Width-4)
}

func (p CommandPaletteComponent) contentHeight() int {
	if p.Popup {
		return commandPaletteContentHeight(p.Height)
	}
	return max(1, p.Height)
}

func (p CommandPaletteComponent) Lines() []string {
	contentW := p.contentWidth()
	panelBG := colors.PopupBg
	if !p.Popup {
		panelBG = colors.BaseBg
	}
	muted := fgOnBg(colors.Muted, panelBG)
	title := firstNonEmpty(p.Title, "Command palette")
	help := firstNonEmpty(p.Help, "esc close")
	titleGap := max(1, contentW-lipgloss.Width(title)-lipgloss.Width(help))
	titleStyleForPalette := muted
	if !p.Popup {
		titleStyleForPalette = titleStyle.Background(panelBG)
	}
	lines := []string{padStyledLine(titleStyleForPalette.Render(title)+bgSpaces(titleGap, panelBG)+muted.Render(help), contentW, panelBG)}
	if p.Popup {
		query := strings.TrimSpace(p.Query)
		if query == "" {
			query = firstNonEmpty(p.Placeholder, "type to filter commands…")
		}
		lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(colors.InputBg).Foreground(colors.Text).Padding(0, 1).Render(truncateCells(query, max(1, contentW-2))))
	} else {
		lines = append(lines, bgSpaces(contentW, panelBG))
	}
	visibleStart := min(max(0, p.Offset), len(p.Items))
	lastCategory := ""
	if visibleStart > 0 {
		lastCategory = p.Items[visibleStart-1].Category
		lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Muted).Render(truncateCells("↑ more commands", contentW)))
	}
	visibleEnd := visibleStart
	paletteH := p.contentHeight()
	for i, item := range p.Items[visibleStart:] {
		itemIndex := visibleStart + i
		if len(lines) >= paletteH-1 {
			break
		}
		visibleEnd = itemIndex + 1
		if p.Popup && item.Category != lastCategory {
			lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.TextSubtle).Bold(true).Render(truncateCells(strings.ToUpper(item.Category), contentW)))
			lastCategory = item.Category
		}
		lines = append(lines, p.rowLine(item, itemIndex == p.Selected, contentW, panelBG))
		if p.Popup && item.Subtitle != "" && len(lines) < paletteH-1 {
			lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Muted).Render(truncateCells("  "+item.Subtitle, contentW)))
		}
	}
	if len(p.Items) == 0 {
		lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Muted).Render("No backed commands match."))
	} else if visibleEnd < len(p.Items) && len(lines) < paletteH {
		lines = append(lines, lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Muted).Render(truncateCells("↓ more commands", contentW)))
	}
	return lines
}

func (p CommandPaletteComponent) rowLine(item CommandPaletteItem, selected bool, width int, bg lipgloss.Color) string {
	rowBg := bg
	fg := colors.Text
	prefix := ""
	if !p.Popup {
		prefix = "  "
	}
	if !item.Enabled {
		fg = colors.Muted
	}
	if selected {
		rowBg = colors.SelectedBg
		fg = colors.SelectedFg
		if !p.Popup {
			prefix = "▸ "
		}
	}
	if p.Popup {
		title := truncateCells(item.Title, max(1, width-lipgloss.Width(item.Shortcut)-3))
		gap := max(1, width-lipgloss.Width(title)-lipgloss.Width(item.Shortcut))
		rowText := title + strings.Repeat(" ", gap) + item.Shortcut
		style := lipgloss.NewStyle().Width(width).MaxWidth(width).Background(rowBg).Foreground(fg)
		if selected {
			style = style.Bold(true)
		}
		return style.Render(truncateCells(rowText, width))
	}
	status := ""
	if !item.Enabled {
		status = " (disabled)"
	}
	line := prefix + item.Title + status + " · " + item.Subtitle
	return padStyledLine(fgOnBg(fg, rowBg).Render(truncateCells(line, width)), width, rowBg)
}

func (p CommandPaletteComponent) View() string {
	content := strings.Join(p.Lines(), "\n")
	if p.Popup {
		paletteW := commandPaletteWidth(p.Width)
		return lipgloss.NewStyle().Width(paletteW-2).MaxWidth(paletteW).Border(lipgloss.NormalBorder()).BorderForeground(colors.PopupBorder).Padding(1, 1).Background(colors.PopupBg).Render(content)
	}
	return padBlock(content, p.Width, p.Height, 2, colors.BaseBg)
}
