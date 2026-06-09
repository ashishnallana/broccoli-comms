package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type memoryActionResult struct {
	MemoryID string
	Action   string
	Err      error
}

type memoryRecord struct {
	MemoryID     string `json:"memory_id"`
	Status       string `json:"status"`
	Version      int    `json:"version"`
	Type         string `json:"type"`
	Scope        string `json:"scope"`
	SubjectAgent string `json:"subject_agent"`
	ProposedBy   string `json:"proposed_by"`
	Title        string `json:"title"`
	Body         string `json:"body"`
}

func selectedMemoryMessage(m model) (tracker.Message, bool) {
	messages := m.displayOrderedMessages()
	if m.messageSelected < 0 || m.messageSelected >= len(messages) {
		return tracker.Message{}, false
	}
	msg := messages[m.messageSelected]
	return msg, isMemoryProposalMessage(msg)
}

func memoryMessageForAction(memoryID string, selected tracker.Message) tracker.Message {
	msg := selected
	msg.MemoryID = memoryID
	return msg
}

func loadMemoryForMessage(ctx context.Context, msg tracker.Message) (memoryRecord, error) {
	out, err := runApprovalCLI(ctx, "memory", "show", msg.MemoryID, "--json")
	if err != nil {
		return memoryRecord{}, fmt.Errorf("memory lookup failed: %w: %s", err, string(out))
	}
	var rec memoryRecord
	if err := json.Unmarshal(out, &rec); err != nil {
		return memoryRecord{}, fmt.Errorf("memory lookup returned invalid JSON: %w", err)
	}
	return rec, nil
}

func memoryActionCmd(msg tracker.Message, action string, title string, body string) tea.Cmd {
	return func() tea.Msg {
		if msg.MemoryID == "" {
			return memoryActionResult{MemoryID: msg.MemoryID, Action: action, Err: errors.New("memory id is required")}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		shown, err := loadMemoryForMessage(ctx, msg)
		if err != nil {
			return memoryActionResult{MemoryID: msg.MemoryID, Action: action, Err: err}
		}
		if shown.MemoryID != msg.MemoryID || shown.Status != "pending" {
			return memoryActionResult{MemoryID: msg.MemoryID, Action: action, Err: errors.New("memory proposal is stale or no longer pending")}
		}
		args := []string{"memory", action, msg.MemoryID, "--expected-version", strconv.Itoa(shown.Version), "--json"}
		if action == "edit" {
			if title == "" && body == "" {
				return memoryActionResult{MemoryID: msg.MemoryID, Action: action, Err: errors.New("/memory edit requires title | body")}
			}
			if title != "" {
				args = append(args, "--title", title)
			}
			if body != "" {
				args = append(args, "--body", body)
			}
		}
		out, err := runApprovalCLI(ctx, args...)
		if err != nil {
			return memoryActionResult{MemoryID: msg.MemoryID, Action: action, Err: fmt.Errorf("memory %s failed: %w: %s", action, err, string(out))}
		}
		return memoryActionResult{MemoryID: msg.MemoryID, Action: action, Err: nil}
	}
}
