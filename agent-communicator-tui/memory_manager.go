package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

type memoryApprovalsLoaded struct {
	Items []memoryRecord
	Err   error
}

type memoryEditClosed struct {
	MemoryID string
	Err      error
}

func loadMemoryApprovalsCmd() tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		out, err := runApprovalCLI(ctx, "memory", "approvals", "--json")
		if err != nil {
			return memoryApprovalsLoaded{Err: fmt.Errorf("memory approvals failed: %w: %s", err, string(out))}
		}
		var payload struct {
			Pending  []memoryRecord `json:"pending"`
			Approved []memoryRecord `json:"approved"`
		}
		if err := json.Unmarshal(out, &payload); err != nil {
			return memoryApprovalsLoaded{Err: fmt.Errorf("memory approvals returned invalid JSON: %w", err)}
		}
		items := append([]memoryRecord{}, payload.Pending...)
		items = append(items, payload.Approved...)
		return memoryApprovalsLoaded{Items: items}
	}
}

func memoryManagerActionCmd(mem memoryRecord, action string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if mem.MemoryID == "" {
			return memoryActionResult{Action: action, Err: fmt.Errorf("memory id is required")}
		}
		args := []string{"memory", action, mem.MemoryID, "--expected-version", strconv.Itoa(mem.Version), "--json"}
		if action == "reject" || action == "revoke" {
			args = append(args, "--reason", "removed from Memory Management tab")
		}
		if action == "rollback" {
			if mem.Version <= 1 {
				return memoryActionResult{MemoryID: mem.MemoryID, Action: action, Err: fmt.Errorf("memory has no previous version")}
			}
			args = []string{"memory", "rollback", mem.MemoryID, "--to-version", strconv.Itoa(mem.Version - 1), "--expected-version", strconv.Itoa(mem.Version), "--json"}
		}
		out, err := runApprovalCLI(ctx, args...)
		if err != nil {
			return memoryActionResult{MemoryID: mem.MemoryID, Action: action, Err: fmt.Errorf("memory %s failed: %w: %s", action, err, string(out))}
		}
		return memoryActionResult{MemoryID: mem.MemoryID, Action: action}
	}
}

func memoryEditorCommandName() string {
	if editor := os.Getenv("EDITOR"); editor != "" {
		return editor
	}
	return "nvim"
}

func editMemoryInEditor(mem memoryRecord) tea.Cmd {
	return func() tea.Msg {
		file, err := os.CreateTemp("", "broccoli-memory-*.md")
		if err != nil {
			return memoryEditClosed{MemoryID: mem.MemoryID, Err: err}
		}
		path := file.Name()
		initial := fmt.Sprintf("%s\n--- body ---\n%s\n", mem.Title, mem.Body)
		if _, err := file.WriteString(initial); err != nil {
			file.Close()
			os.Remove(path)
			return memoryEditClosed{MemoryID: mem.MemoryID, Err: err}
		}
		file.Close()
		editor := memoryEditorCommandName()
		return tea.ExecProcess(exec.Command(editor, path), func(err error) tea.Msg {
			defer os.Remove(path)
			if err != nil {
				return memoryEditClosed{MemoryID: mem.MemoryID, Err: err}
			}
			content, err := os.ReadFile(path)
			if err != nil {
				return memoryEditClosed{MemoryID: mem.MemoryID, Err: err}
			}
			parts := strings.SplitN(string(content), "\n--- body ---\n", 2)
			if len(parts) != 2 {
				return memoryEditClosed{MemoryID: mem.MemoryID, Err: fmt.Errorf("memory edit must keep the --- body --- separator")}
			}
			title := strings.TrimSpace(parts[0])
			body := strings.TrimSpace(parts[1])
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			out, err := runApprovalCLI(ctx, "memory", "edit", mem.MemoryID, "--title", title, "--body", body, "--expected-version", strconv.Itoa(mem.Version), "--json")
			if err != nil {
				return memoryEditClosed{MemoryID: mem.MemoryID, Err: fmt.Errorf("memory edit failed: %w: %s", err, string(out))}
			}
			return memoryEditClosed{MemoryID: mem.MemoryID}
		})()
	}
}

func (m model) selectedMemoryRecord() (memoryRecord, bool) {
	return m.selectedFilteredMemoryRecord()
}

func memoryRecordAgentName(mem memoryRecord) string {
	return firstNonEmpty(mem.SubjectAgent, mem.ProposedBy, "unknown")
}
