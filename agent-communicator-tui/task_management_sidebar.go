package main

import "fmt"

func selectedTaskRecord(data taskManagementData) (taskRecord, bool) {
	rows := orderedTaskRows(data.Buckets)
	if len(rows) == 0 {
		return taskRecord{}, false
	}
	if !data.ChainFocused {
		if data.SelectedChain.CurrentTask.TaskID != "" {
			return data.SelectedChain.CurrentTask, true
		}
		if data.SelectedChain.NextTask.TaskID != "" {
			return data.SelectedChain.NextTask, true
		}
		return rows[0], true
	}
	return rows[dataSelectedIndex(data, len(rows))], true
}

func taskSelectedChainLines(data taskManagementData, width int) []string {
	bg := colors.RightColumnBg
	lines := []string{padStyledLine(sectionHeaderStyle.Render("Selected chain"), width, bg)}
	chain := data.SelectedChain
	if chain.ChainID == "" {
		return append(lines, padStyledLine(mutedStyle.Render("No chain selected."), width, bg))
	}
	lines = append(lines,
		padStyledLine(fgOnBg(colors.SelectedFg, colors.SelectedBg).Bold(true).Render(truncateCells(chain.ChainID+" · root "+firstNonEmpty(chain.RootTaskID, "—"), width)), width, colors.SelectedBg),
		padStyledLine(fgOnBg(colors.SelectedFg, colors.SelectedBg).Render(truncateCells(firstNonEmpty(chain.RootTitle, "Untitled chain"), width)), width, colors.SelectedBg),
		padStyledLine(mutedStyle.Render(truncateCells(fmt.Sprintf("working %d · ready %d · blocked %d · review %d · done %d", chain.Counts.Working, chain.Counts.Ready, chain.Counts.Blocked, chain.Counts.Review, chain.Counts.Completed), width)), width, bg),
	)
	if chain.LatestActivity != "" {
		lines = append(lines, padStyledLine(mutedStyle.Render(truncateCells("latest "+chain.LatestActivity, width)), width, bg))
	}
	return lines
}

func taskSelectedTaskLines(data taskManagementData, width int) []string {
	bg := colors.RightColumnBg
	task, ok := selectedTaskRecord(data)
	if !ok {
		return []string{padStyledLine(mutedStyle.Render("No task selected."), width, bg)}
	}
	status := firstNonEmpty(task.Status, task.ResultStatus, "unknown")
	lines := []string{
		padStyledLine(fgOnBg(colors.SelectedFg, colors.SelectedBg).Bold(true).Render(truncateCells(task.TaskID+" · "+firstNonEmpty(task.Title, "Untitled task"), width)), width, colors.SelectedBg),
		padStyledLine(fgOnBg(colors.SelectedFg, colors.SelectedBg).Render(truncateCells(status+" · "+firstNonEmpty(task.Priority, "priority —"), width)), width, colors.SelectedBg),
	}
	if task.NextStep != "" {
		lines = append(lines, padStyledLine(mutedStyle.Render(truncateCells("next "+task.NextStep, width)), width, bg))
	}
	if task.Description != "" {
		lines = append(lines, padStyledLine(mutedStyle.Render(truncateCells(task.Description, width)), width, bg))
	}
	return lines
}

func taskParticipantLines(data taskManagementData, width, height int) []string {
	bg := colors.RightColumnBg
	participants := data.SelectedChain.Participants
	if len(participants) == 0 {
		task, ok := selectedTaskRecord(data)
		if ok && task.AssignedAgent != "" {
			participants = []taskParticipant{{Agent: task.AssignedAgent, Role: "assignee", Status: "active", Compatibility: true}}
		}
	}
	if len(participants) == 0 {
		return []string{padStyledLine(mutedStyle.Render("No participants."), width, bg)}
	}
	lines := make([]string, 0, len(participants)*2)
	for _, p := range participants {
		line := fmt.Sprintf("%s · %s · %s", firstNonEmpty(p.Agent, "agent"), firstNonEmpty(p.Role, "role"), firstNonEmpty(p.Status, "active"))
		if p.Compatibility {
			line += " · legacy"
		}
		lines = append(lines, padStyledLine(fgOnBg(colors.Accent, bg).Render(truncateCells(line, width)), width, bg))
		if len(lines) >= height {
			return lines[:height]
		}
	}
	return lines
}

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
	counts := taskCountsByAgent(m.tasksItems, m.rows)
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
		line2 := fmt.Sprintf("  %d tasks · %s", countTasksForAgent(counts, row), firstNonEmpty(row.CurrentTask, "No active task"))
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

func taskCountsByAgent(tasks []taskRecord, rows []agentRow) map[string]int {
	counts := map[string]int{}
	for _, task := range tasks {
		if taskArchived(task) {
			continue
		}
		if task.AssignedAgent != "" {
			counts[task.AssignedAgent]++
		}
	}
	for _, row := range rows {
		for _, name := range []string{row.Name, row.AgentName, row.TargetAddress} {
			if name != "" && counts[name] == 0 {
				counts[name] = countTasksForAgent(counts, row)
			}
		}
	}
	return counts
}

func countTasksForAgent(counts map[string]int, row agentRow) int {
	for _, name := range []string{row.Name, row.AgentName, row.TargetAddress} {
		if name != "" && counts[name] > 0 {
			return counts[name]
		}
	}
	return 0
}
