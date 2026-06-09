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
	"github.com/charmbracelet/lipgloss"
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
			args = append(args, "--reason", "removed from Memory Approvals TUI")
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
		editor := os.Getenv("EDITOR")
		if editor == "" {
			editor = "vi"
		}
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
	if len(m.memoryItems) == 0 || m.memorySelected < 0 || m.memorySelected >= len(m.memoryItems) {
		return memoryRecord{}, false
	}
	return m.memoryItems[m.memorySelected], true
}

func (m model) updateMemoryApprovals(msg tea.KeyMsg) (model, tea.Cmd) {
	switch msg.Type {
	case tea.KeyCtrlC, tea.KeyCtrlQ:
		return m, tea.Quit
	case tea.KeyEsc:
		m.showingMemoryApprovals = false
		return m, nil
	case tea.KeyUp, tea.KeyCtrlP:
		if len(m.memoryItems) > 0 {
			m.memorySelected = (m.memorySelected - 1 + len(m.memoryItems)) % len(m.memoryItems)
		}
	case tea.KeyDown, tea.KeyCtrlN:
		if len(m.memoryItems) > 0 {
			m.memorySelected = (m.memorySelected + 1) % len(m.memoryItems)
		}
	case tea.KeyRunes:
		mem, ok := m.selectedMemoryRecord()
		if !ok {
			return m, nil
		}
		switch string(msg.Runes) {
		case "a":
			if mem.Status == "pending" {
				return m, memoryManagerActionCmd(mem, "approve")
			}
		case "d":
			if mem.Status == "pending" {
				return m, memoryManagerActionCmd(mem, "reject")
			}
			if mem.Status == "active" {
				return m, memoryManagerActionCmd(mem, "revoke")
			}
		case "e":
			return m, editMemoryInEditor(mem)
		case "r":
			return m, memoryManagerActionCmd(mem, "rollback")
		}
	}
	return m, nil
}

func (m model) memoryApprovalsView(width, height int) string {
	contentW := max(20, width-4)
	panelBG := colors.PopupBg
	style := lipgloss.NewStyle().Width(contentW).MaxWidth(contentW).Background(panelBG).Foreground(colors.Text)
	muted := fgOnBg(colors.Muted, panelBG)
	lines := []string{
		padStyledLine(muted.Render("Memory Approvals")+bgSpaces(max(1, contentW-lipgloss.Width("Memory Approvals")-lipgloss.Width("esc close")), panelBG)+muted.Render("esc close"), contentW, panelBG),
		padStyledLine(muted.Render("↑/↓ select  a approve  e edit  d delete/reject  r rollback previous version"), contentW, panelBG),
	}
	if m.memoryErr != nil {
		lines = append(lines, padStyledLine(fgOnBg(colors.Error, panelBG).Render(m.memoryErr.Error()), contentW, panelBG))
	}
	if len(m.memoryItems) == 0 {
		lines = append(lines, padStyledLine(muted.Render("No pending or approved memory."), contentW, panelBG))
	}
	for i, mem := range m.memoryItems {
		if len(lines) >= max(4, height-2) {
			break
		}
		marker := "  "
		if i == m.memorySelected {
			marker = "▸ "
		}
		title := firstNonEmpty(mem.Title, mem.MemoryID)
		row := fmt.Sprintf("%s[%s] %s v%d %s", marker, mem.Status, mem.MemoryID, mem.Version, title)
		lines = append(lines, padStyledLine(style.Render(row), contentW, panelBG))
		if mem.Body != "" && i == m.memorySelected && len(lines) < max(4, height-2) {
			preview := strings.ReplaceAll(mem.Body, "\n", " ")
			if len(preview) > contentW-4 {
				preview = preview[:contentW-7] + "..."
			}
			lines = append(lines, padStyledLine(muted.Render("   "+preview), contentW, panelBG))
		}
	}
	box := lipgloss.NewStyle().Width(contentW).MaxWidth(width).Border(lipgloss.NormalBorder()).BorderForeground(colors.PopupBorder).Padding(1, 1).Background(panelBG).Render(strings.Join(lines, "\n"))
	return lipgloss.Place(width, height, lipgloss.Center, lipgloss.Center, box, lipgloss.WithWhitespaceBackground(colors.BaseBg))
}
