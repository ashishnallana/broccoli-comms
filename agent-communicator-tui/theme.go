package main

import "github.com/charmbracelet/lipgloss"

func everforestTerminalTheme() TerminalTheme {
	c := func(hex string) lipgloss.Color { return lipgloss.Color(hex) }
	return TerminalTheme{
		BaseBg:           c("#2d353b"),
		PanelBg:          c("#343f44"),
		PanelBgAlt:       c("#3d484d"),
		IncomingBubbleBg: c("#34483f"),
		CapturePaneBg:    c("#3d484d"),
		TaskUpdateBg:     c("#3a435f"),
		RightColumnBg:    c("#343f44"),
		Text:             c("#d3c6aa"),
		TextStrong:       c("#fdf6e3"),
		TextSubtle:       c("#a7c080"),
		Muted:            c("#859289"),
		Accent:           c("#7fbbb3"),
		AccentStrong:     c("#83c092"),
		AccentAlt:        c("#d699b6"),
		Success:          c("#a7c080"),
		Warning:          c("#dbbc7f"),
		Error:            c("#e67e80"),
		Info:             c("#7fbbb3"),
		Border:           c("#4f5b58"),
		SelectedBg:       c("#a7c080"),
		SelectedFg:       c("#2d353b"),
		InputBg:          c("#232a2e"),
		PopupBg:          c("#2d353b"),
		PopupBorder:      c("#4f5b58"),
		BadgeBg:          c("#a7c080"),
		BadgeFg:          c("#2d353b"),
		RemoteBadgeBg:    c("#d699b6"),
		RemoteBadgeFg:    c("#2d353b"),
		ReadTick:         c("#a7c080"),
		DeliveredTick:    c("#83c092"),
		SentTick:         c("#859289"),
		Saved:            c("#dbbc7f"),
		AgentColors: []lipgloss.Color{
			c("#a7c080"), // Green
			c("#83c092"), // Aqua
			c("#d699b6"), // Purple
			c("#dbbc7f"), // Yellow
			c("#7fbbb3"), // Teal
			c("#e67e80"), // Red
			c("#e69875"), // Orange
			c("#a7c080"), // Green Alt
			c("#d699b6"), // Purple Alt
			c("#83c092"), // Aqua Alt
		},
	}
}
