package main

import "fmt"

func taskSelectedAgentLines(data taskManagementData, width int) []string {
	bg := colors.RightColumnBg
	lines := []string{padStyledLine(sectionHeaderStyle.Render("Selected agent"), width, bg)}
	if data.SelectedAgent.Name == "" {
		return append(lines, padStyledLine(mutedStyle.Render("No agent selected."), width, bg))
	}
	chain := firstNonEmpty(data.ActiveChainID, data.RootTaskID, "no chain")
	task := firstNonEmpty(data.SelectedAgent.CurrentTask, "No active task")
	return append(lines,
		padStyledLine(fgOnBg(colors.SelectedFg, colors.SelectedBg).Bold(true).Render(truncateCells(data.SelectedAgent.Name+" · "+chain, width)), width, colors.SelectedBg),
		padStyledLine(fgOnBg(colors.SelectedFg, colors.SelectedBg).Render(truncateCells(task, width)), width, colors.SelectedBg),
	)
}

func (m model) taskAgentSidebarLines(data taskManagementData, width, height int) []string {
	bg := colors.RightColumnBg
	if len(m.rows) == 0 {
		return []string{padStyledLine(mutedStyle.Render("No agents found."), width, bg)}
	}
	counts := taskCountsByAgent(m.tasksItems)
	lines := make([]string, 0, len(m.rows)*2)
	for i, row := range m.rows {
		selected := i == m.selected
		rowBg := bg
		fg := colors.Text
		prefix := "  "
		if selected {
			rowBg = colors.SelectedBg
			fg = colors.SelectedFg
			prefix = "▸ "
		}
		status := firstNonEmpty(row.Status, "unknown")
		chain := "no chain"
		if row.CurrentTaskID != "" {
			chain = "chain"
		}
		line1 := fmt.Sprintf("%s%s · %s · %s", prefix, firstNonEmpty(row.Name, "agent"), status, chain)
		line2 := fmt.Sprintf("  %d tasks · %s", counts[row.Name], firstNonEmpty(row.CurrentTask, "No active task"))
		lines = append(lines,
			padStyledLine(fgOnBg(fg, rowBg).Bold(selected).Render(truncateCells(line1, width)), width, rowBg),
			padStyledLine(fgOnBg(colors.Muted, rowBg).Render(truncateCells(line2, width)), width, rowBg),
		)
		if len(lines) >= height {
			return lines[:height]
		}
	}
	return lines
}

func taskCountsByAgent(tasks []taskRecord) map[string]int {
	counts := map[string]int{}
	for _, task := range tasks {
		if task.AssignedAgent != "" {
			counts[task.AssignedAgent]++
		}
	}
	return counts
}
