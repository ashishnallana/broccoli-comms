package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestSwarmModeCtrlNCtrlPSwitchesSwarms(t *testing.T) {
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix"}, {Name: "frontend-fix"}}, local: &fakeLocal{}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	m = updated.(model)
	if m.selectedSwarm != 1 || m.selectedSwarmName() != "frontend-fix" || cmd == nil {
		t.Fatalf("ctrl-n selected=%d name=%q cmd=%v", m.selectedSwarm, m.selectedSwarmName(), cmd)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyCtrlP})
	m = updated.(model)
	if m.selectedSwarm != 0 || m.selectedSwarmName() != "backend-fix" || cmd == nil {
		t.Fatalf("ctrl-p selected=%d name=%q cmd=%v", m.selectedSwarm, m.selectedSwarmName(), cmd)
	}
}

func TestSwarmMissingMainWarningRenders(t *testing.T) {
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", MainMissing: true, Warning: "No main agent configured/running", Members: []agentRow{{Name: "coder-a"}}}}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")
	for _, want := range []string{"backend-fix", "warning", "No main agent configured/running"} {
		if !strings.Contains(view, want) {
			t.Fatalf("swarm warning view missing %q:\n%s", want, view)
		}
	}
	sidebar := m.swarmSidebarView(40, 16)
	if !strings.Contains(sidebar, "coder-a") || !strings.Contains(sidebar, "main missing") {
		t.Fatalf("swarm sidebar missing member/main warning:\n%s", sidebar)
	}
}

func TestSwarmEmptyStateRendersSetupGuidance(t *testing.T) {
	m := model{mode: swarmView}
	view := strings.Join(m.messageLinesForWidth(100), "\n")
	for _, want := range []string{"No swarms found", "--swarm", "--role", "broccoli-comms track"} {
		if !strings.Contains(view, want) {
			t.Fatalf("swarm empty state missing %q:\n%s", want, view)
		}
	}
}

func TestSwarmComposerSendsToMainAgentOnly(t *testing.T) {
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	local := &fakeLocal{}
	m := model{
		mode:     swarmView,
		ownName:  "agent-communicator",
		local:    local,
		composer: []rune("hello main"),
		swarms: []swarmRow{{
			Name:    "backend-fix",
			Main:    agentRow{Name: "planner", TargetAddress: "planner", Scope: "local"},
			Members: []agentRow{{Name: "planner", TargetAddress: "planner"}, {Name: "coder-a", TargetAddress: "coder-a"}},
		}},
		sentMessages: map[string][]tracker.Message{},
	}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd == nil || string(m.composer) != "" {
		t.Fatalf("swarm submit cmd=%v composer=%q", cmd, string(m.composer))
	}
	_ = cmd()
	if local.sentTo != "planner" || !strings.Contains(local.sentBody, "hello main") {
		t.Fatalf("swarm submit target/body = %q/%q", local.sentTo, local.sentBody)
	}
}

func TestSwarmMissingMainDoesNotSubmitAndPreservesDraft(t *testing.T) {
	local := &fakeLocal{}
	m := model{mode: swarmView, local: local, composer: []rune("keep draft"), swarms: []swarmRow{{Name: "backend-fix", MainMissing: true, Warning: "No main agent configured/running"}}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || string(m.composer) != "keep draft" || local.sentTo != "" {
		t.Fatalf("missing-main submit cmd=%v composer=%q sentTo=%q", cmd, string(m.composer), local.sentTo)
	}
	panel := m.conversationPanel(80, 20)
	if !strings.Contains(panel, "no main agent") || strings.Contains(panel, "/msg") {
		t.Fatalf("missing-main composer should be disabled with warning:\n%s", panel)
	}
}

func TestSwarmComposerPlaceholderMentionsSelectedSwarm(t *testing.T) {
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}}
	view := m.composerView(80)
	if !strings.Contains(view, "message main agent in backend-fix") {
		t.Fatalf("swarm composer placeholder missing selected swarm: %q", view)
	}
}

func TestSwarmTimelineRendersSenderRecipientLabels(t *testing.T) {
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}, swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "please fix"}}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")
	if !strings.Contains(view, "planner → coder-a") || !strings.Contains(view, "please fix") {
		t.Fatalf("swarm timeline missing sender/recipient label:\n%s", view)
	}
	if !strings.Contains(view, "┃") {
		t.Fatalf("swarm timeline should reuse message bubble rail styling:\n%s", view)
	}
}

func TestSwarmViewIncludesLocalSentToMainMessages(t *testing.T) {
	main := agentRow{Name: "planner", TargetAddress: "planner", Scope: "local"}
	m := model{
		mode:   swarmView,
		swarms: []swarmRow{{Name: "backend-fix", Main: main, Members: []agentRow{main}}},
		sentMessages: map[string][]tracker.Message{
			conversationKey(main): {{Sender: "You", Body: "local sent body", Timestamp: "2026-06-06T09:20:00Z", MessageID: "sent-1"}},
		},
	}
	view := strings.Join(m.messageLinesForWidth(100), "\n")
	if !strings.Contains(view, "You → planner") || !strings.Contains(view, "local sent body") {
		t.Fatalf("swarm view missing local sent-to-main message:\n%s", view)
	}
	if !strings.Contains(view, "┃") {
		t.Fatalf("swarm sent message should reuse message bubble rail styling:\n%s", view)
	}
}

func TestSwarmTimelineShowsNewestMessageFirst(t *testing.T) {
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}, swarmMessages: []tracker.SwarmTimelineMessage{
		{Sender: "planner", Recipient: "coder-a", Body: "old message", Timestamp: "2026-06-06T09:00:00Z", MessageID: "old"},
		{Sender: "coder-a", Recipient: "planner", Body: "new message", Timestamp: "2026-06-06T09:05:00Z", MessageID: "new"},
	}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")
	oldIndex := strings.Index(view, "old message")
	newIndex := strings.Index(view, "new message")
	if oldIndex < 0 || newIndex < 0 || newIndex > oldIndex {
		t.Fatalf("swarm timeline should render newest before oldest (new=%d old=%d):\n%s", newIndex, oldIndex, view)
	}
}

func TestSwarmSwitchReloadsAndChangesTimeline(t *testing.T) {
	local := &fakeLocal{swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "new timeline"}}}
	m := model{mode: swarmView, local: local, swarms: []swarmRow{{Name: "backend-fix"}, {Name: "frontend-fix"}}, swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "old", Body: "stale"}}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	m = updated.(model)
	if len(m.swarmMessages) != 0 || cmd == nil {
		t.Fatalf("switch should clear current timeline and reload, messages=%+v cmd=%v", m.swarmMessages, cmd)
	}
	updated, _ = m.Update(cmd())
	m = updated.(model)
	if local.lastSwarmName != "frontend-fix" || len(m.swarmMessages) != 1 || m.swarmMessages[0].Body != "new timeline" {
		t.Fatalf("reload swarm=%q messages=%+v", local.lastSwarmName, m.swarmMessages)
	}
}

func TestSwarmRowsFromTrackerMapsMainMembersAndWarnings(t *testing.T) {
	rows := swarmRowsFromTracker([]tracker.Swarm{{
		Name: "backend-fix",
		Main: tracker.SwarmMember{Name: "planner", Role: "main", TargetAddress: "planner"},
		Members: []tracker.SwarmMember{
			{Name: "planner", Role: "main", TargetAddress: "planner"},
			{Name: "coder-a", Role: "subagent", TargetAddress: "coder-a"},
		},
		Warnings: []string{"duplicate main"},
	}})
	if len(rows) != 1 || rows[0].Main.Name != "planner" || len(rows[0].Members) != 2 || !strings.Contains(rows[0].Warning, "duplicate main") {
		t.Fatalf("rows=%+v", rows)
	}
}
