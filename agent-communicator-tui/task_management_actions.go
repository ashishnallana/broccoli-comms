package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
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
		return "press d again to archive " + task.TaskID
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

func (m model) confirmOrRunChainArchive() (model, tea.Cmd) {
	data := m.taskData()
	if len(data.Tasks) == 0 {
		m.tasksErr = fmt.Errorf("no active chain to archive")
		return m, nil
	}
	chainID := firstNonEmpty(data.ActiveChainID, data.RootTaskID, "active-chain")
	if m.tasksConfirm.Action != "archive_chain" || m.tasksConfirm.TaskID != chainID {
		m.tasksConfirm = taskActionConfirmation{Action: "archive_chain", TaskID: chainID}
		m.directInputStatus = taskActionConfirmText(taskRecord{TaskID: chainID}, "archive_chain")
		m.directInputStatusErr = false
		return m, nil
	}
	m.tasksConfirm = taskActionConfirmation{}
	m.tasksLoading = true
	return m, archiveTaskChainCmd(data.Tasks)
}

func (m model) confirmOrRunChainAssign() (model, tea.Cmd) {
	data := m.taskData()
	if len(data.Tasks) == 0 {
		m.tasksErr = fmt.Errorf("no active chain to reassign")
		return m, nil
	}
	chainID := firstNonEmpty(data.ActiveChainID, data.RootTaskID, "active-chain")
	if m.tasksConfirm.Action != "assign_chain" || m.tasksConfirm.TaskID != chainID {
		m.tasksConfirm = taskActionConfirmation{Action: "assign_chain", TaskID: chainID}
		m.directInputStatus = taskActionConfirmText(taskRecord{TaskID: chainID}, "assign_chain")
		m.directInputStatusErr = false
		return m, nil
	}
	m.tasksConfirm = taskActionConfirmation{}
	m.tasksLoading = true
	return m, assignTaskChainCmd(data.Tasks, m.currentRow().Name)
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
		case "ready":
			args = append(args, "--status", "ready")
		default:
			return taskActionResult{TaskID: task.TaskID, Action: action, Err: fmt.Errorf("unsupported task action %q", action)}
		}
		out, err := runApprovalCLI(ctx, args...)
		if err != nil {
			return taskActionResult{TaskID: task.TaskID, Action: action, Err: fmt.Errorf("task %s failed: %w: %s", action, err, string(out))}
		}
		return taskActionResult{TaskID: task.TaskID, Action: action, Status: "Task " + action + " saved"}
	}
}

func createTaskInChainCmd(title, agent, priority string, dependsOn []string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		args := []string{"task", "create", "--title", title, "--priority", firstNonEmpty(priority, "P1"), "--json"}
		if agent != "" {
			args = append(args, "--agent", agent)
		}
		if len(dependsOn) > 0 {
			args = append(args, "--depends-on", strings.Join(dependsOn, ","))
		}
		out, err := runApprovalCLI(ctx, args...)
		if err != nil {
			return taskActionResult{Action: "create", Err: fmt.Errorf("task create failed: %w: %s", err, string(out))}
		}
		return taskActionResult{Action: "create", Status: "Task created"}
	}
}

func summarizeTaskChainCmd(chainID string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if chainID == "" {
			return taskActionResult{Action: "summary", Err: fmt.Errorf("no active chain to summarize")}
		}
		out, err := runApprovalCLI(ctx, "task", "summarize-chain", chainID, "--json")
		if err != nil {
			return taskActionResult{Action: "summary", Err: fmt.Errorf("chain summary failed: %w: %s", err, string(out))}
		}
		return taskActionResult{Action: "summary", Status: "Chain summary refreshed"}
	}
}

func archiveTaskChainCmd(tasks []taskRecord) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		for _, task := range tasks {
			if task.TaskID == "" || taskCompleted(task) {
				continue
			}
			out, err := runApprovalCLI(ctx, "task", "update", task.TaskID, "--status", "archived", "--json")
			if err != nil {
				return taskActionResult{TaskID: task.TaskID, Action: "archive_chain", Err: fmt.Errorf("archive chain failed at %s: %w: %s", task.TaskID, err, string(out))}
			}
		}
		return taskActionResult{Action: "archive_chain", Status: "Chain archived"}
	}
}

func assignTaskChainCmd(tasks []taskRecord, agent string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if agent == "" {
			return taskActionResult{Action: "assign_chain", Err: fmt.Errorf("no selected agent to assign chain")}
		}
		for _, task := range tasks {
			if task.TaskID == "" || taskCompleted(task) {
				continue
			}
			out, err := runApprovalCLI(ctx, "task", "update", task.TaskID, "--assign-agent", agent, "--json")
			if err != nil {
				return taskActionResult{TaskID: task.TaskID, Action: "assign_chain", Err: fmt.Errorf("assign chain failed at %s: %w: %s", task.TaskID, err, string(out))}
			}
		}
		return taskActionResult{Action: "assign_chain", Status: "Chain reassigned"}
	}
}

func editTaskFieldInEditor(task taskRecord, field string) tea.Cmd {
	return func() tea.Msg {
		initial, ok := editableTaskFieldValue(task, field)
		if !ok {
			return taskEditClosed{TaskID: task.TaskID, Field: field, Err: fmt.Errorf("unsupported editable task field %q", field)}
		}
		file, err := os.CreateTemp("", "broccoli-task-*.md")
		if err != nil {
			return taskEditClosed{TaskID: task.TaskID, Field: field, Err: err}
		}
		path := file.Name()
		if _, err := file.WriteString(initial); err != nil {
			file.Close()
			os.Remove(path)
			return taskEditClosed{TaskID: task.TaskID, Field: field, Err: err}
		}
		file.Close()
		return tea.ExecProcess(exec.Command(memoryEditorCommandName(), path), func(err error) tea.Msg {
			defer os.Remove(path)
			if err != nil {
				return finishTaskEditorContent(task.TaskID, field, initial, "", err)
			}
			content, err := os.ReadFile(path)
			if err != nil {
				return taskEditClosed{TaskID: task.TaskID, Field: field, Err: err}
			}
			return finishTaskEditorContent(task.TaskID, field, initial, string(content), nil)
		})()
	}
}

func finishTaskEditorContent(taskID, field, initial, content string, editorErr error) taskEditClosed {
	if editorErr != nil {
		return taskEditClosed{TaskID: taskID, Field: field, Err: fmt.Errorf("editor failed: %w", editorErr)}
	}
	updated := strings.TrimRight(content, "\n")
	if updated == strings.TrimRight(initial, "\n") {
		return taskEditClosed{TaskID: taskID, Field: field, Status: "Task edit unchanged"}
	}
	return updateTaskField(taskID, field, updated)
}

func editableTaskFieldValue(task taskRecord, field string) (string, bool) {
	switch field {
	case "next_step":
		return task.NextStep, true
	case "result_summary":
		return task.ResultSummary, true
	default:
		return "", false
	}
}

func updateTaskField(taskID, field, value string) taskEditClosed {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	args := []string{"task", "update", taskID, "--json"}
	switch field {
	case "next_step":
		args = append(args, "--next-step", value)
	case "result_summary":
		args = append(args, "--result-summary", value)
	default:
		return taskEditClosed{TaskID: taskID, Field: field, Err: fmt.Errorf("unsupported editable task field %q", field)}
	}
	out, err := runApprovalCLI(ctx, args...)
	if err != nil {
		return taskEditClosed{TaskID: taskID, Field: field, Err: fmt.Errorf("task edit failed: %w: %s", err, string(out))}
	}
	return taskEditClosed{TaskID: taskID, Field: field, Status: "Task " + strings.ReplaceAll(field, "_", " ") + " saved"}
}
