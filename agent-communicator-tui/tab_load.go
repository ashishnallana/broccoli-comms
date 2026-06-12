package main

import tea "github.com/charmbracelet/bubbletea"

func (m model) loadActiveTabCmd() tea.Cmd {
	if tab, ok := tabForMode(m.mode); ok && tab.Load != nil {
		return tab.Load(m)
	}
	return nil
}
