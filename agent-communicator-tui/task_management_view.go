package main

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

func (m model) taskManagementView(width, height int) string {
	if m.tasksPalette.Open {
		return m.taskCommandPaletteView(width, height)
	}
	if width < 70 {
		return m.taskPrimaryPanel(width, height, false)
	}
	contentW, rightW := taskLayoutWidths(width)
	primary := m.taskPrimaryPanel(contentW, height, true)
	right := m.taskDetailsPanel(rightW, height)
	return lipgloss.JoinHorizontal(lipgloss.Top, primary, right)
}

func taskLayoutWidths(width int) (int, int) {
	right := min(42, max(28, (width*32)/100))
	if width < 100 {
		right = min(34, max(24, width/3))
	}
	return max(10, width-right), right
}

func (m model) taskPrimaryPanel(width, height int, wide bool) string {
	bg := colors.BaseBg
	padX := 3
	if !wide {
		padX = 1
	}
	innerW := max(1, width-(padX*2))
	data := m.taskData()
	title := "Chain Investigation"
	if data.ChainFocused {
		title = "Chain Timeline"
	}
	lines := []string{
		padStyledLine(titleStyle.Render(title), innerW, bg),
		m.taskAgentFilterInputBox(innerW),
		padStyledLine(mutedStyle.Render(truncateCells(taskSummaryLine(data), innerW)), innerW, bg),
		padStyledLine(mutedStyle.Render(truncateCells(taskHelpLine(data), innerW)), innerW, bg),
		padStyledLine(mutedStyle.Render(truncateCells("forms use field-aware autocomplete", innerW)), innerW, bg),
		bgSpaces(innerW, bg),
	}
	if m.tasksForm.Active {
		lines = append(lines, taskChainFormLines(m, innerW)...)
	}
	if m.tasksConfirm.Active() {
		lines = append(lines, padStyledLine(fgOnBg(colors.Warning, bg).Render(truncateCells("Confirm: "+taskActionConfirmText(taskRecord{TaskID: m.tasksConfirm.TaskID}, m.tasksConfirm.Action)+" · esc cancel", innerW)), innerW, bg))
	}
	if m.tasksLoading {
		lines = append(lines, padStyledLine(fgOnBg(colors.Muted, bg).Render("Loading tasks…"), innerW, bg))
	} else if m.tasksErr != nil {
		lines = append(lines, padStyledLine(fgOnBg(colors.Error, bg).Render(truncateCells("Tasks load failed · Task load failure · r retry · "+m.tasksErr.Error(), innerW)), innerW, bg))
	} else if len(data.Chains) == 0 {
		msg := "No chains found."
		if data.AgentFilter != "" {
			msg = "No chains matching agent filter."
		}
		lines = append(lines, padStyledLine(fgOnBg(colors.Muted, bg).Render(msg), innerW, bg))
	} else if data.ChainFocused {
		lines = append(lines, taskBucketLines(data, innerW, max(1, height-len(lines)))...)
	} else {
		lines = append(lines, taskChainLines(data, innerW, max(1, height-len(lines)))...)
	}
	return padBlock(strings.Join(lines, "\n"), width, height, padX, bg)
}

func (m model) taskAgentFilterInputBox(width int) string {
	padX := 2
	if m.width < 70 {
		padX = 1
	}
	inner := max(1, width-(padX*2))
	blank := bgSpaces(width, colors.InputBg)
	style := fgOnBg(colors.Muted, colors.InputBg)
	if m.tasksAgentFilterFocused {
		style = fgOnBg(colors.Text, colors.InputBg)
	}
	text := "agent filter: all"
	if strings.TrimSpace(string(m.tasksAgentFilter)) != "" {
		text = "agent filter: " + strings.TrimSpace(string(m.tasksAgentFilter))
	}
	line := bgSpaces(padX, colors.InputBg) + padStyledLine(style.Render(truncateCells(text, inner)), inner, colors.InputBg) + bgSpaces(padX, colors.InputBg)
	return strings.Join([]string{blank, line, blank}, "\n")
}

func taskHelpLine(data taskManagementData) string {
	if data.ChainFocused {
		return "↑/↓ task · enter commands · esc chains · / or f filter agent · tab chips · ctrl-k commands · r refresh"
	}
	return "↑/↓ task/chain · r refresh · ctrl-k commands · ctrl-n/ctrl-p agent · enter focus · / or f filter · tab chips"
}

func taskSummaryLine(data taskManagementData) string {
	return fmt.Sprintf("chains %d · total %d · working %d · ready %d · queued %d · blocked %d · review %d", len(data.Chains), data.Counts.Total, data.Counts.Working, data.Counts.Ready, data.Counts.Queued, data.Counts.Blocked, data.Counts.Review)
}

func taskChainLines(data taskManagementData, width, height int) []string {
	var lines []string
	for i, chain := range data.Chains {
		if i < data.Offset {
			continue
		}
		selected := i == data.SelectedIndex
		lines = append(lines, taskChainRowLines(chain, selected, width)...)
		if len(lines) >= height {
			return lines[:height]
		}
		lines = append(lines, bgSpaces(width, colors.BaseBg))
		if len(lines) >= height {
			return lines[:height]
		}
	}
	return lines
}

func taskChainRowLines(chain taskChainSummary, selected bool, width int) []string {
	bg := colors.TaskUpdateBg
	fg := colors.Text
	marker := "┃"
	if selected {
		bg = colors.SelectedBg
		fg = colors.SelectedFg
		marker = "▸"
	}
	style := fgOnBg(fg, bg).Bold(selected)
	meta := fgOnBg(colors.Muted, bg)
	if selected {
		meta = fgOnBg(colors.SelectedFg, bg)
	}
	line1 := fmt.Sprintf("%s %s · root %s · %s", marker, firstNonEmpty(chain.ChainID, "chain"), firstNonEmpty(chain.RootTaskID, "—"), firstNonEmpty(chain.RootTitle, "Untitled chain"))
	line2 := fmt.Sprintf("  W%d R%d Q%d B%d Rev%d · agents %s", chain.Counts.Working, chain.Counts.Ready, chain.Counts.Queued, chain.Counts.Blocked, chain.Counts.Review, firstNonEmpty(strings.Join(chain.Agents, ", "), "—"))
	current := firstNonEmpty(chain.CurrentTask.Title, chain.CurrentTask.TaskID, "no current")
	next := firstNonEmpty(chain.NextTask.Title, chain.NextTask.TaskID, "no next")
	line3 := fmt.Sprintf("  current %s · next %s · updated %s", current, next, firstNonEmpty(chain.LatestUpdate, "—"))
	return []string{
		padStyledLine(style.Render(truncateCells(line1, width)), width, bg),
		padStyledLine(meta.Render(truncateCells(line2, width)), width, bg),
		padStyledLine(meta.Render(truncateCells(line3, width)), width, bg),
	}
}

func taskBucketLines(data taskManagementData, width, height int) []string {
	var lines []string
	selectedTaskID := ""
	rows := orderedTaskRows(data.Buckets)
	if len(rows) > 0 {
		selectedTaskID = rows[min(max(0, dataSelectedIndex(data, len(rows))), len(rows)-1)].TaskID
	}
	rowIndex := 0
	for _, bucket := range data.Buckets {
		if len(bucket.Tasks) == 0 {
			continue
		}
		var bucketLines []string
		for _, task := range bucket.Tasks {
			visible := rowIndex >= data.Offset
			rowIndex++
			if !visible {
				continue
			}
			current := task.TaskID == data.CurrentTaskID && bucket.Name == "Current"
			selected := task.TaskID != "" && task.TaskID == selectedTaskID
			bucketLines = append(bucketLines, taskRowLines(task, current, selected, width)...)
			if len(lines)+len(bucketLines)+1 >= height {
				break
			}
		}
		if len(bucketLines) == 0 {
			continue
		}
		lines = append(lines, padStyledLine(sectionHeaderStyle.Render(fmt.Sprintf("%s (%d)", bucket.Name, len(bucket.Tasks))), width, colors.BaseBg))
		lines = append(lines, bucketLines...)
		if len(lines) >= height {
			return lines[:height]
		}
		lines = append(lines, bgSpaces(width, colors.BaseBg))
		if len(lines) >= height {
			return lines[:height]
		}
	}
	return lines
}

func dataSelectedIndex(data taskManagementData, count int) int {
	return min(max(0, data.SelectedIndex), max(0, count-1))
}

func taskRowLines(task taskRecord, current bool, selected bool, width int) []string {
	bg := colors.BaseBg
	fg := colors.Text
	marker := "┃"
	completed := taskCompleted(task)
	if current {
		bg = colors.SelectedBg
		fg = colors.SelectedFg
		marker = "▸"
	} else if selected {
		bg = colors.PanelBgAlt
		fg = colors.TextStrong
		marker = "›"
	} else if strings.EqualFold(task.Status, "blocked") || task.BlockedReason != "" {
		bg = colors.PanelBgAlt
		fg = colors.Warning
	} else if completed {
		fg = colors.Muted
		marker = "✓"
	}
	style := fgOnBg(fg, bg)
	metaStyle := fgOnBg(colors.Muted, bg)
	if current {
		metaStyle = fgOnBg(colors.SelectedFg, bg)
	}
	status := firstNonEmpty(task.Status, task.ResultStatus, "unknown")
	line1 := fmt.Sprintf("%s %s · %s", marker, firstNonEmpty(task.TaskID, "task"), firstNonEmpty(task.Title, "Untitled task"))
	line2 := fmt.Sprintf("  %s · %s · %s", status, firstNonEmpty(task.Priority, "priority —"), firstNonEmpty(task.AssignedAgent, "unassigned"))
	if task.NextStep != "" {
		line2 += " · next " + task.NextStep
	} else if task.BlockedReason != "" {
		line2 += " · blocked " + task.BlockedReason
	}
	return []string{
		padStyledLine(style.Bold(current || selected).Render(truncateCells(line1, width)), width, bg),
		padStyledLine(metaStyle.Render(truncateCells(line2, width)), width, bg),
	}
}

func (m model) taskDetailsPanel(width, height int) string {
	bg := colors.RightColumnBg
	innerW := max(1, width-2)
	data := m.taskData()
	lines := []string{
		padStyledLine(shellTitleStyle.Render("Task details · Chain details"), innerW, bg),
		padStyledLine(mutedStyle.Render(truncateCells(taskSummaryLine(data), innerW)), innerW, bg),
		bgSpaces(innerW, bg),
	}
	lines = append(lines, taskSelectedChainLines(data, innerW)...)
	lines = append(lines, bgSpaces(innerW, bg), padStyledLine(sectionHeaderStyle.Render("Selected task"), innerW, bg))
	lines = append(lines, taskSelectedTaskLines(data, innerW)...)
	lines = append(lines, bgSpaces(innerW, bg), padStyledLine(sectionHeaderStyle.Render("Agents"), innerW, bg))
	lines = append(lines, m.taskAgentSidebarLines(data, innerW, max(1, height-len(lines)-10))...)
	lines = append(lines, bgSpaces(innerW, bg), padStyledLine(sectionHeaderStyle.Render("Review"), innerW, bg))
	approvals := data.Approvals
	if len(approvals) == 0 {
		lines = append(lines, padStyledLine(mutedStyle.Render("No approval records for this chain."), innerW, bg))
	} else {
		for _, approval := range approvals {
			line := fmt.Sprintf("%s · %s · %s", firstNonEmpty(approval.ApprovalID, "approval"), firstNonEmpty(approval.Status, "unknown"), firstNonEmpty(approval.Result, "pending"))
			lines = append(lines, padStyledLine(fgOnBg(colors.Accent, bg).Render(truncateCells(line, innerW)), innerW, bg))
		}
	}
	lines = append(lines, bgSpaces(innerW, bg), padStyledLine(sectionHeaderStyle.Render("Participants"), innerW, bg))
	lines = append(lines, taskParticipantLines(data, innerW, max(1, height-len(lines)-8))...)
	if len(data.Blockers) > 0 {
		lines = append(lines, bgSpaces(innerW, bg), padStyledLine(sectionHeaderStyle.Render("Blockers"), innerW, bg))
		for _, blocker := range data.Blockers {
			lines = append(lines, padStyledLine(fgOnBg(colors.Warning, bg).Render(truncateCells("• "+blocker, innerW)), innerW, bg))
		}
	}
	return padBlock(strings.Join(lines, "\n"), width, height, 1, bg)
}

func taskCompleted(task taskRecord) bool {
	status := strings.ToLower(strings.TrimSpace(firstNonEmpty(task.Status, task.ResultStatus)))
	return status == "done" || status == "completed" || status == "validated" || task.ResultStatus == "good"
}

func padBlock(content string, width, height, padX int, bg lipgloss.Color) string {
	innerW := max(1, width-(padX*2))
	left := bgSpaces(padX, bg)
	lines := strings.Split(content, "\n")
	for len(lines) < height {
		lines = append(lines, bgSpaces(innerW, bg))
	}
	if len(lines) > height {
		lines = lines[:height]
	}
	for i, line := range lines {
		lines[i] = left + padStyledLine(line, innerW, bg) + left
	}
	return strings.Join(lines, "\n")
}
