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
		editorInitial := taskEditorInitialContent(field, initial)
		if _, err := file.WriteString(editorInitial); err != nil {
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

func taskEditorInitialContent(field, initial string) string {
	if strings.TrimSpace(initial) != "" {
		return initial
	}
	return "# Edit task " + strings.ReplaceAll(field, "_", " ") + " below. Lines starting with # are ignored.\n# Leave this scaffold unchanged to cancel.\n"
}

func stripTaskEditorScaffold(content string) string {
	var kept []string
	for _, line := range strings.Split(content, "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "#") {
			continue
		}
		kept = append(kept, line)
	}
	return strings.TrimRight(strings.Join(kept, "\n"), "\n")
}

func finishTaskEditorContent(taskID, field, initial, content string, editorErr error) taskEditClosed {
	if editorErr != nil {
		return taskEditClosed{TaskID: taskID, Field: field, Err: fmt.Errorf("editor failed: %w", editorErr)}
	}
	updated := strings.TrimRight(content, "\n")
	if strings.TrimSpace(initial) == "" {
		updated = stripTaskEditorScaffold(content)
	}
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
