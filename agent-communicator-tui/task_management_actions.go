package main

import (
	"context"
	"fmt"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

type taskActionConfirmation struct {
	Action string
	TaskID string
}

type taskActionResult struct {
	TaskID string
	Action string
	Err    error
	Status string
}

type taskEditClosed struct {
	TaskID string
	Field  string
	Err    error
	Status string
}

func (c taskActionConfirmation) Active() bool { return c.Action != "" && c.TaskID != "" }

func (m model) selectedTaskRecord() (taskRecord, bool) {
	rows := orderedTaskRows(m.taskData().Buckets)
	if len(rows) == 0 {
		return taskRecord{}, false
	}
	idx := min(max(0, m.tasksSelected), len(rows)-1)
	return rows[idx], true
}

func (m model) taskConfirmationMatches(task taskRecord, action string) bool {
	return m.tasksConfirm.Action == action && m.tasksConfirm.TaskID == task.TaskID
}

func (m model) confirmOrRunTaskAction(task taskRecord, action string) (model, tea.Cmd) {
	if task.TaskID == "" {
		m.tasksErr = fmt.Errorf("task id is required")
		return m, nil
	}
	if !m.taskConfirmationMatches(task, action) {
		m.tasksConfirm = taskActionConfirmation{Action: action, TaskID: task.TaskID}
		m.directInputStatus = taskActionConfirmText(task, action)
		m.directInputStatusErr = false
		return m, nil
	}
	m.tasksConfirm = taskActionConfirmation{}
	m.tasksLoading = true
	return m, taskActionCmd(task, action, m.currentRow().Name)
}

func taskActionConfirmText(task taskRecord, action string) string {
	switch action {
	case "archive":
		return "press enter again to remove/archive " + task.TaskID
	case "archive_chain":
		return "press D again to archive active chain"
	case "assign":
		return "press x again to reassign " + task.TaskID
	case "assign_chain":
		return "press X again to reassign active chain"
	default:
		return "press again to confirm " + action + " " + task.TaskID
	}
}

func taskActionCmd(task taskRecord, action, agent string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		args := []string{"task", "update", task.TaskID, "--json"}
		switch action {
		case "archive":
			args = append(args, "--status", "archived")
		case "assign":
			if agent == "" {
				return taskActionResult{TaskID: task.TaskID, Action: action, Err: fmt.Errorf("no selected agent to assign")}
			}
			args = append(args, "--assign-agent", agent)
		case "start":
			args = append(args, "--status", "working")
		case "complete":
			args = append(args, "--status", "done")
		case "ready":
			args = append(args, "--status", "ready")
		default:
			return taskActionResult{TaskID: task.TaskID, Action: action, Err: fmt.Errorf("unsupported task action %q", action)}
		}
		out, err := runApprovalCLI(ctx, args...)
		if err != nil {
			return taskActionResult{TaskID: task.TaskID, Action: action, Err: fmt.Errorf("task %s failed: %w: %s", action, err, string(out))}
		}
		status := "Task " + action + " saved"
		if action == "complete" {
			status = "Task marked complete"
		}
		return taskActionResult{TaskID: task.TaskID, Action: action, Status: status}
	}
}
