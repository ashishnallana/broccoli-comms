package main

import "github.com/charmbracelet/lipgloss"

type Palette struct {
	Text     lipgloss.Color
	Subtext0 lipgloss.Color
	Overlay0 lipgloss.Color
	Surface0 lipgloss.Color
	Base     lipgloss.Color

	Red      lipgloss.Color
	Peach    lipgloss.Color
	Yellow   lipgloss.Color
	Green    lipgloss.Color
	Teal     lipgloss.Color
	Sky      lipgloss.Color
	Sapphire lipgloss.Color
	Blue     lipgloss.Color
	Lavender lipgloss.Color
	Mauve    lipgloss.Color
	Pink     lipgloss.Color

	AgentColors []lipgloss.Color
}

var palette = everforestDarkMedium()

func everforestDarkMedium() Palette {
	p := Palette{
		Text:     lipgloss.Color("#d3c6aa"),
		Subtext0: lipgloss.Color("#9da9a0"),
		Overlay0: lipgloss.Color("#859289"),
		Surface0: lipgloss.Color("#4f5b58"),
		Base:     lipgloss.Color("#2d353b"),
		Red:      lipgloss.Color("#e67e80"),
		Peach:    lipgloss.Color("#e69875"),
		Yellow:   lipgloss.Color("#dbbc7f"),
		Green:    lipgloss.Color("#a7c080"),
		Teal:     lipgloss.Color("#83c092"),
		Sky:      lipgloss.Color("#7fbbb3"),
		Sapphire: lipgloss.Color("#7fbbb3"),
		Blue:     lipgloss.Color("#7fbbb3"),
		Lavender: lipgloss.Color("#d699b6"),
		Mauve:    lipgloss.Color("#d699b6"),
		Pink:     lipgloss.Color("#d699b6"),
	}
	p.AgentColors = []lipgloss.Color{p.Green, p.Sky, p.Mauve, p.Yellow, p.Blue, p.Red, p.Teal, p.Pink, p.Peach, p.Lavender}
	return p
}
