package main

import (
	"errors"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestAgentsLoadedErrorKeepsLastGoodRowsAndMessages(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}, messages: []tracker.Message{{Sender: "alpha", Body: "old"}}}
	updated, _ := m.Update(agentsLoaded{Err: errors.New("tracker list: signal: killed")})
	m = updated.(model)
	if len(m.rows) != 1 || m.rows[0].Name != "alpha" || len(m.messages) != 1 {
		t.Fatalf("state lost on list error: rows=%+v messages=%+v", m.rows, m.messages)
	}
	if m.err == nil || !m.agentListStale {
		t.Fatalf("err=%v stale=%v", m.err, m.agentListStale)
	}
}

func TestSendDisabledWhileAgentListUnreachable(t *testing.T) {
	m := model{agentListStale: true, rows: []agentRow{{Name: "alpha", Scope: "local"}}, composer: []rune("hello"), local: &fakeLocal{}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || string(m.composer) != "hello" {
		t.Fatalf("cmd=%v composer=%q", cmd, string(m.composer))
	}
	m.composer = nil
	if !strings.Contains(m.composerView(80), "sending disabled") {
		t.Fatalf("composer missing disabled hint: %q", m.composerView(80))
	}
}

func TestAgentsLoadedSuccessReEnablesSending(t *testing.T) {
	m := model{agentListStale: true, rows: []agentRow{{Name: "old", Scope: "local"}}}
	updated, _ := m.Update(agentsLoaded{Rows: []agentRow{{Name: "alpha", Scope: "local"}}})
	m = updated.(model)
	if m.agentListStale || len(m.rows) != 1 || m.rows[0].Name != "alpha" {
		t.Fatalf("stale=%v rows=%+v", m.agentListStale, m.rows)
	}
}
