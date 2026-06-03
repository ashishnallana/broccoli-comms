package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestHiddenAgentsPersist(t *testing.T) {
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	hidden := map[string]bool{"alpha": true, "remote/beta": true}
	if err := saveHiddenAgents(hidden); err != nil {
		t.Fatal(err)
	}
	loaded, err := loadHiddenAgents()
	if err != nil {
		t.Fatal(err)
	}
	if !loaded["alpha"] || !loaded["remote/beta"] {
		t.Fatalf("loaded = %+v", loaded)
	}
	if _, err := os.Stat(filepath.Dir(hiddenAgentsPath())); err != nil {
		t.Fatal(err)
	}
}

func TestHiddenAgentsSortAfterActiveWithoutVisibleExplanation(t *testing.T) {
	m := model{hiddenAgents: map[string]bool{"beta": true}, rows: []agentRow{{Name: "beta", Scope: "local"}, {Name: "alpha", Scope: "local"}}}
	m.sortRowsByHidden("")
	if m.rows[0].Name != "alpha" || m.rows[1].Name != "beta" {
		t.Fatalf("rows = %+v", m.rows)
	}
	view := m.agentList(40, 20)
	if strings.Contains(strings.ToLower(view), "system agents hidden") || strings.Contains(view, "hidden / Filtered") {
		t.Fatalf("agent list should not show hidden explanatory text =\n%s", view)
	}
}

func TestAgentListShowsHiddenAgentsSeparator(t *testing.T) {
	m := model{
		rows: []agentRow{
			{Name: "alpha", Scope: "local"},
			{Name: "remote-a", Scope: "remote"},
			{Name: "beta", Scope: "local"},
		},
		hiddenAgents: map[string]bool{"beta": true},
	}
	view := m.agentList(60, 20)
	if !strings.Contains(view, "Hidden Agents") {
		t.Fatalf("agent list missing hidden separator:\n%s", view)
	}
	if !strings.Contains(view, "beta") || !strings.Contains(view, "◌") {
		t.Fatalf("hidden row should remain visible with marker:\n%s", view)
	}
}

func TestCtrlHTogglesHiddenAndMovesSelection(t *testing.T) {
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}, {Name: "gamma", Scope: "local"}}, selected: 1, hiddenAgents: map[string]bool{}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlH})
	m = updated.(model)
	if cmd == nil || !m.hiddenAgents["beta"] {
		t.Fatalf("hidden=%+v cmd=%v", m.hiddenAgents, cmd)
	}
	if m.currentRow().Name != "gamma" {
		t.Fatalf("selected row = %+v", m.currentRow())
	}
}

func TestCtrlHToggleHiddenFallsBackWhenSectionBecomesEmpty(t *testing.T) {
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}, selected: 0, hiddenAgents: map[string]bool{}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyCtrlH})
	m = updated.(model)
	if m.agentSection != hiddenAgents || m.currentRow().Name != "alpha" {
		t.Fatalf("section=%v selected=%+v", m.agentSection, m.currentRow())
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlH})
	m = updated.(model)
	if m.agentSection != activeAgents || m.currentRow().Name != "alpha" {
		t.Fatalf("section=%v selected=%+v", m.agentSection, m.currentRow())
	}
}

func TestTabTogglesAgentSection(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}}, hiddenAgents: map[string]bool{"beta": true}}
	m.sortRowsByHidden("")
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyTab})
	m = updated.(model)
	if m.agentSection != hiddenAgents || m.currentRow().Name != "beta" {
		t.Fatalf("section=%v selected=%+v", m.agentSection, m.currentRow())
	}
}

func TestInitialHideMarksAgentsWithoutHistoryHidden(t *testing.T) {
	state := t.TempDir()
	cache := t.TempDir()
	t.Setenv("XDG_STATE_HOME", state)
	t.Setenv("XDG_CACHE_HOME", cache)
	inbox := communicatorInboxPath()
	if err := os.MkdirAll(filepath.Dir(inbox), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(inbox, []byte(`{"sender":"alpha","message":"hi"}`+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}}, hiddenAgents: map[string]bool{}}
	m.applyInitialHiddenForNoHistory()
	if m.hiddenAgents["alpha"] || !m.hiddenAgents["beta"] {
		t.Fatalf("hidden=%+v", m.hiddenAgents)
	}
}

func TestZv2AgentNeverHidden(t *testing.T) {
	state := t.TempDir()
	cache := t.TempDir()
	t.Setenv("XDG_STATE_HOME", state)
	t.Setenv("XDG_CACHE_HOME", cache)

	m := model{
		rows: []agentRow{
			{Name: "zv2-agent", Scope: "local"},
			{Name: "beta", Scope: "local"},
		},
		hiddenAgents: map[string]bool{
			"zv2-agent": true,
			"beta":      true,
		},
	}

	if m.isHiddenAgent(m.rows[0]) {
		t.Fatalf("zv2-agent should not be considered hidden even if in hiddenAgents map")
	}
	if !m.isHiddenAgent(m.rows[1]) {
		t.Fatalf("beta should be considered hidden")
	}

	m2 := model{
		rows: []agentRow{
			{Name: "zv2-agent-new", Scope: "local"},
			{Name: "beta-new", Scope: "local"},
		},
		hiddenAgents: map[string]bool{},
	}
	m2.applyInitialHiddenForNoHistory()
	if m2.hiddenAgents["zv2-agent-new"] {
		t.Fatalf("zv2-agent-new was auto-hidden by applyInitialHiddenForNoHistory")
	}
}

func TestInitialHideKeepsLocalAgentWithIDHistoryAndTrackerID(t *testing.T) {
	state := t.TempDir()
	cache := t.TempDir()
	t.Setenv("XDG_STATE_HOME", state)
	t.Setenv("XDG_CACHE_HOME", cache)
	inbox := communicatorInboxPath()
	if err := os.MkdirAll(filepath.Dir(inbox), 0o700); err != nil {
		t.Fatal(err)
	}
	line := `{"sender":"old-alpha","sender_agent_id":"agent-1","sender_tracker_id":"tracker-local","message":"hi"}` + "\n"
	if err := os.WriteFile(inbox, []byte(line), 0o600); err != nil {
		t.Fatal(err)
	}
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local", AgentID: "agent-1"}, {Name: "beta", Scope: "local", AgentID: "agent-2"}}, hiddenAgents: map[string]bool{}}
	m.applyInitialHiddenForNoHistory()
	if m.hiddenAgents["local:agent-1"] || !m.hiddenAgents["local:agent-2"] {
		t.Fatalf("hidden=%+v", m.hiddenAgents)
	}
}

func TestSendUnhidesHiddenAgent(t *testing.T) {
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	row := agentRow{Name: "alpha", Scope: "local"}
	m := model{rows: []agentRow{row}, hiddenAgents: map[string]bool{"alpha": true}}
	cmd := m.unhideAgent(row)
	if cmd == nil || m.hiddenAgents["alpha"] || m.agentSection != activeAgents {
		t.Fatalf("hidden=%+v section=%v cmd=%v", m.hiddenAgents, m.agentSection, cmd)
	}
}

func TestUnhideImmediatelyRebuildsDisplayGrouping(t *testing.T) {
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	alpha := agentRow{Name: "alpha", Scope: "local"}
	beta := agentRow{Name: "beta", Scope: "local"}
	remote := agentRow{Name: "host/remote", Scope: "remote"}
	m := model{
		allRows:      []agentRow{alpha, beta, remote},
		rows:         []agentRow{alpha, remote, beta},
		selected:     2,
		hiddenAgents: map[string]bool{"beta": true},
		agentSection: hiddenAgents,
	}

	cmd := m.unhideAgent(beta)
	if cmd == nil {
		t.Fatal("expected hidden-agent save command")
	}
	if got := namesOfRows(m.rows); strings.Join(got, ",") != "alpha,beta,host/remote" {
		t.Fatalf("rows were not regrouped immediately: %v", got)
	}
	if m.currentRow().Name != "beta" || m.agentSection != activeAgents {
		t.Fatalf("selected=%+v section=%v", m.currentRow(), m.agentSection)
	}
}

func namesOfRows(rows []agentRow) []string {
	names := make([]string, 0, len(rows))
	for _, row := range rows {
		names = append(names, row.Name)
	}
	return names
}

func TestCtrlNCtrlPSkipHiddenAgents(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}, {Name: "gamma", Scope: "local"}}, hiddenAgents: map[string]bool{"gamma": true}}
	m.sortRowsByHidden("")
	// "gamma" is hidden, so active cycling should stay between alpha and beta.

	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	m = updated.(model)
	if m.currentRow().Name != "beta" {
		t.Fatalf("selected=%+v", m.currentRow())
	}

	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	m = updated.(model)
	if m.currentRow().Name != "alpha" {
		t.Fatalf("ctrl-n should skip hidden agents, selected=%+v", m.currentRow())
	}

	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlP})
	m = updated.(model)
	if m.currentRow().Name != "beta" {
		t.Fatalf("ctrl-p should skip hidden agents, selected=%+v", m.currentRow())
	}
}

func TestCtrlNCtrlPFallbackWhenAllAgentsHidden(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}}, hiddenAgents: map[string]bool{"alpha": true, "beta": true}}
	m.sortRowsByHidden("")

	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	m = updated.(model)
	if m.currentRow().Name != "beta" {
		t.Fatalf("all-hidden fallback should preserve existing cycling, selected=%+v", m.currentRow())
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlP})
	m = updated.(model)
	if m.currentRow().Name != "alpha" {
		t.Fatalf("all-hidden fallback should preserve existing cycling, selected=%+v", m.currentRow())
	}
}
