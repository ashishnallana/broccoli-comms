package main

import "github.com/charmbracelet/lipgloss"

func tokyoNightTerminalTheme() TerminalTheme {
	c := func(hex string) lipgloss.Color { return lipgloss.Color(hex) }
	return TerminalTheme{
		BaseBg:        c("#1a1b26"),
		PanelBg:       c("#1f2335"),
		PanelBgAlt:    c("#24283b"),
		RightColumnBg: c("#24283b"),
		Text:          c("#a9b1d6"),
		TextStrong:    c("#c0caf5"),
		TextSubtle:    c("#9aa5ce"),
		Muted:         c("#737aa2"),
		Accent:        c("#7aa2f7"),
		AccentStrong:  c("#7dcfff"),
		AccentAlt:     c("#bb9af7"),
		Success:       c("#9ece6a"),
		Warning:       c("#e0af68"),
		Error:         c("#f7768e"),
		Info:          c("#7aa2f7"),
		Border:        c("#3b4261"),
		SelectedBg:    c("#7aa2f7"),
		SelectedFg:    c("#16161e"),
		InputBg:       c("#16161e"),
		PopupBg:       c("#16161e"),
		PopupBorder:   c("#3b4261"),
		BadgeBg:       c("#7aa2f7"),
		BadgeFg:       c("#16161e"),
		RemoteBadgeBg: c("#bb9af7"),
		RemoteBadgeFg: c("#16161e"),
		ReadTick:      c("#9ece6a"),
		DeliveredTick: c("#7dcfff"),
		SentTick:      c("#737aa2"),
		Saved:         c("#e0af68"),
		AgentColors: []lipgloss.Color{
			c("#9ece6a"), // Green
			c("#7dcfff"), // Cyan
			c("#bb9af7"), // Purple/Magenta
			c("#e0af68"), // Yellow
			c("#7aa2f7"), // Blue
			c("#f7768e"), // Red
			c("#ff9e64"), // Orange
			c("#73daca"), // Teal
			c("#9d7cd8"), // Dark Purple
			c("#2ac3de"), // Cyan Alt
		},
	}
}
