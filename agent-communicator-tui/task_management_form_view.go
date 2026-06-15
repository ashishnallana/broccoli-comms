package main

import "strings"

func taskChainFormLines(m model, width int) []string {
	bg := colors.InputBg
	text := m.tasksForm.Text()
	if text == "" {
		text = "title | agent | priority | depends"
	}
	lines := []string{
		padStyledLine(fgOnBg(colors.AccentStrong, bg).Bold(true).Render(truncateCells(taskChainFormHelp(m.tasksForm.Action), width)), width, bg),
		padStyledLine(fgOnBg(colors.Text, bg).Render(truncateCells(text, width)), width, bg),
	}
	if m.tasksForm.Err != nil {
		lines = append(lines, padStyledLine(fgOnBg(colors.Error, bg).Render(truncateCells(m.tasksForm.Err.Error(), width)), width, bg))
	}
	fieldIndex, token := currentTaskFormField(m.tasksForm.Text())
	options := m.taskFormAutocompleteOptions(fieldIndex, token)
	if len(options) > 0 {
		parts := make([]string, 0, min(4, len(options)))
		for i, option := range options {
			if i >= 4 {
				break
			}
			parts = append(parts, option.Kind+":"+option.Value)
		}
		lines = append(lines, padStyledLine(fgOnBg(colors.Muted, bg).Render(truncateCells("autocomplete "+strings.Join(parts, " · "), width)), width, bg))
	}
	return lines
}

func currentTaskFormField(text string) (int, string) {
	parts := strings.Split(text, "|")
	return len(parts) - 1, strings.TrimSpace(parts[len(parts)-1])
}
