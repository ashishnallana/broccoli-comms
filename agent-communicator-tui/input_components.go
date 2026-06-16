package main

import (
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/lipgloss"
)

type InputSurface struct {
	Width         int
	TerminalWidth int
	Bg            lipgloss.Color
	Lines         []string
}

func (s InputSurface) View() string {
	return renderInputSurface(s.Width, s.TerminalWidth, s.Lines, s.Bg)
}

type TextInputSurface struct {
	Input         textinput.Model
	Width         int
	TerminalWidth int
	Bg            lipgloss.Color
	Focused       bool
	TextStyle     lipgloss.Style
	MutedStyle    lipgloss.Style
}

func NewTextInputSurface(width, terminalWidth int, bg lipgloss.Color, value, placeholder string, focused bool) TextInputSurface {
	input := textinput.New()
	input.SetValue(value)
	input.Placeholder = placeholder
	if focused {
		input.Focus()
	} else {
		input.Blur()
	}
	return TextInputSurface{
		Input:         input,
		Width:         width,
		TerminalWidth: terminalWidth,
		Bg:            bg,
		Focused:       focused,
		TextStyle:     fgOnBg(colors.Text, bg),
		MutedStyle:    fgOnBg(colors.Muted, bg),
	}
}

func (s TextInputSurface) ViewText() string {
	padX := responsiveInputPadding(s.TerminalWidth)
	inner := max(1, s.Width-(padX*2))
	text := s.Input.Value()
	style := s.MutedStyle
	if s.Focused {
		style = s.TextStyle
	}
	if text == "" {
		text = s.Input.Placeholder
		style = s.MutedStyle
	}
	return style.Render(truncateCells(text, inner))
}

func (s TextInputSurface) View() string {
	return InputSurface{Width: s.Width, TerminalWidth: s.TerminalWidth, Bg: s.Bg, Lines: []string{s.ViewText()}}.View()
}

type ComposerInputSurface struct {
	Width         int
	TerminalWidth int
	Lines         []string
}

func (s ComposerInputSurface) View() string {
	return InputSurface{Width: s.Width, TerminalWidth: s.TerminalWidth, Bg: colors.InputBg, Lines: s.Lines}.View()
}
