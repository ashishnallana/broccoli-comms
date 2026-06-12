package main

import (
	"context"
	"encoding/json"
	"reflect"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestCommandPaletteOpensMemoryManagementTab(t *testing.T) {
	m := model{commandPalette: commandPaletteState{Open: true, Query: []rune("memory")}}
	updated, cmd := m.updateCommandPalette(tea.KeyMsg{Type: tea.KeyEnter})
	if updated.mode != memoryView {
		t.Fatalf("memory action should switch to memory tab, got mode %v", updated.mode)
	}
	if updated.commandPalette.Open {
		t.Fatalf("command palette should close after opening memory management")
	}
	if !updated.memoryLoading || cmd == nil {
		t.Fatalf("opening memory management should load memory records, loading=%v cmd=%v", updated.memoryLoading, cmd)
	}
}

func TestMemoryEditorCommandDefaultsToNvimAndHonorsEditor(t *testing.T) {
	t.Setenv("EDITOR", "")
	if got := memoryEditorCommandName(); got != "nvim" {
		t.Fatalf("default editor=%q want nvim", got)
	}
	t.Setenv("EDITOR", "nano")
	if got := memoryEditorCommandName(); got != "nano" {
		t.Fatalf("EDITOR override=%q want nano", got)
	}
}

func TestLoadMemoryApprovalsUsesApprovalsBackend(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, args)
		return json.Marshal(map[string]any{
			"pending":  []memoryRecord{{MemoryID: "mem-p", Status: "pending", Version: 1}},
			"approved": []memoryRecord{{MemoryID: "mem-a", Status: "active", Version: 2}},
		})
	}
	msg := loadMemoryApprovalsCmd()().(memoryApprovalsLoaded)
	if msg.Err != nil {
		t.Fatalf("loadMemoryApprovalsCmd error: %v", msg.Err)
	}
	if len(msg.Items) != 2 || msg.Items[0].MemoryID != "mem-p" || msg.Items[1].MemoryID != "mem-a" {
		t.Fatalf("loaded items = %#v", msg.Items)
	}
	want := []string{"memory", "approvals", "--json"}
	if len(calls) != 1 || !reflect.DeepEqual(calls[0], want) {
		t.Fatalf("load args = %#v, want %#v", calls, want)
	}
}

func TestMemoryManagementTabEscDoesNotLeaveTab(t *testing.T) {
	m := model{mode: memoryView}
	updated, cmd := m.handleKeyMsg(tea.KeyMsg{Type: tea.KeyEsc})
	if updated.mode != memoryView || cmd != nil {
		t.Fatalf("esc in memory tab should only cancel local state, mode=%v cmd=%v", updated.mode, cmd)
	}
}
