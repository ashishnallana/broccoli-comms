package main

import (
	"context"
	"encoding/json"
	"reflect"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestCommandPaletteOpensMemoryApprovals(t *testing.T) {
	m := model{commandPalette: commandPaletteState{Open: true, Query: []rune("memory")}}
	updated, cmd := m.updateCommandPalette(tea.KeyMsg{Type: tea.KeyEnter})
	if !updated.showingMemoryApprovals {
		t.Fatalf("memory approvals should open from command palette")
	}
	if updated.commandPalette.Open {
		t.Fatalf("command palette should close after opening memory approvals")
	}
	if cmd == nil {
		t.Fatalf("opening memory approvals should load memory records")
	}
}

func TestMemoryApprovalsEscapeClosesOverlay(t *testing.T) {
	m := model{showingMemoryApprovals: true}
	updated, cmd := m.handleKeyMsg(tea.KeyMsg{Type: tea.KeyEsc})
	if updated.showingMemoryApprovals {
		t.Fatalf("esc should close memory approvals overlay")
	}
	if cmd != nil {
		t.Fatalf("esc should not return command: %v", cmd)
	}
}

func TestMemoryApprovalsSelectionKeysAreRouted(t *testing.T) {
	m := model{showingMemoryApprovals: true, memoryItems: []memoryRecord{{MemoryID: "mem-1"}, {MemoryID: "mem-2"}}, memorySelected: 0}
	updated, cmd := m.handleKeyMsg(tea.KeyMsg{Type: tea.KeyDown})
	if cmd != nil {
		t.Fatalf("selection should not return command: %v", cmd)
	}
	if updated.memorySelected != 1 {
		t.Fatalf("down should select second memory, got %d", updated.memorySelected)
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

func TestMemoryApprovalsViewShowsTypeAndAgent(t *testing.T) {
	m := model{
		showingMemoryApprovals: true,
		memoryItems:            []memoryRecord{{MemoryID: "mem-1", Status: "pending", Version: 1, Type: "habit", SubjectAgent: "broccoli-agent", Title: "Run tests"}},
		memorySelected:         0,
	}
	view := m.memoryApprovalsView(120, 30)
	for _, want := range []string{"type:habit", "agent:broccoli-agent"} {
		if !strings.Contains(view, want) {
			t.Fatalf("memory approvals view missing %q: %q", want, view)
		}
	}
}

func TestMemoryApprovalsViewFallsBackToProposerAgent(t *testing.T) {
	m := model{
		showingMemoryApprovals: true,
		memoryItems:            []memoryRecord{{MemoryID: "mem-1", Status: "pending", Version: 1, Type: "fact", ProposedBy: "proposer-agent", Title: "Endpoint"}},
		memorySelected:         0,
	}
	view := m.memoryApprovalsView(120, 30)
	if !strings.Contains(view, "agent:proposer-agent") {
		t.Fatalf("memory approvals view should fall back to proposed_by agent: %q", view)
	}
}

func TestMemoryApprovalsApproveActionCommand(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, args)
		return json.Marshal(map[string]any{"ok": true})
	}

	m := model{showingMemoryApprovals: true, memoryItems: []memoryRecord{{MemoryID: "mem-1", Status: "pending", Version: 3}}, memorySelected: 0}
	updated, cmd := m.handleKeyMsg(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("a")})
	if !updated.showingMemoryApprovals {
		t.Fatalf("approve action should keep overlay open")
	}
	if cmd == nil {
		t.Fatalf("approve action should return command")
	}
	res := cmd().(memoryActionResult)
	if res.Err != nil {
		t.Fatalf("approve command returned error: %v", res.Err)
	}
	want := []string{"memory", "approve", "mem-1", "--expected-version", "3", "--json"}
	if len(calls) != 1 || !reflect.DeepEqual(calls[0], want) {
		t.Fatalf("approve args = %#v, want %#v", calls, want)
	}
}
