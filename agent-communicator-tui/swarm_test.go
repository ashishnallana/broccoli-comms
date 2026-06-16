package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func boolPtr(v bool) *bool { return &v }

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
	for _, want := range []string{"No swarms found", "/swarm create", "agent start-swarm", "config.json"} {
		if !strings.Contains(view, want) {
			t.Fatalf("swarm empty state missing %q:\n%s", want, view)
		}
	}
	for _, obsolete := range []string{"broccoli-comms run", "--swarm", "--role"} {
		if strings.Contains(view, obsolete) {
			t.Fatalf("swarm empty state should not show obsolete hint %q:\n%s", obsolete, view)
		}
	}
}

func TestSwarmCreateCommandAssignsLiveAgentsAndSelectsNewSwarm(t *testing.T) {
	local := &fakeLocal{}
	m := model{
		mode:     swarmView,
		local:    local,
		composer: []rune("/swarm create backend-fix --main planner --subagent coder-a"),
		rows: []agentRow{
			{Name: "planner", TargetAddress: "planner", Scope: "local"},
			{Name: "coder-a", TargetAddress: "coder-a", Scope: "local"},
		},
	}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd == nil || string(m.composer) != "" {
		t.Fatalf("create cmd=%v composer=%q", cmd, string(m.composer))
	}
	updated, timelineCmd := m.Update(cmd().(swarmAssigned))
	m = updated.(model)
	if local.assignedSwarm != "backend-fix" || local.assignedMain != "planner" || len(local.assignedSubagents) != 1 || local.assignedSubagents[0] != "coder-a" {
		t.Fatalf("assigned swarm=%q main=%q subs=%v", local.assignedSwarm, local.assignedMain, local.assignedSubagents)
	}
	if m.selectedSwarmName() != "backend-fix" || timelineCmd == nil {
		t.Fatalf("selected swarm=%q timelineCmd=%v", m.selectedSwarmName(), timelineCmd)
	}
}

func TestSwarmCreateRejectsNonLiveAgent(t *testing.T) {
	m := model{mode: swarmView, local: &fakeLocal{}, composer: []rune("/swarm create backend-fix --main planner --subagent missing"), rows: []agentRow{{Name: "planner", TargetAddress: "planner", Scope: "local"}}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || m.err == nil || !strings.Contains(m.err.Error(), "missing") {
		t.Fatalf("expected non-live error, cmd=%v err=%v", cmd, m.err)
	}
}

func TestLoadSelectedSwarmTimelineUsesDurableTimelineAPI(t *testing.T) {
	local := &fakeLocal{swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "durable event"}}}
	msg := loadSelectedSwarmTimeline(local, "backend-fix")()
	loaded, ok := msg.(swarmTimelineLoaded)
	if !ok || loaded.Err != nil {
		t.Fatalf("timeline msg = %#v", msg)
	}
	if local.getSwarmTimelineCalls != 1 || local.lastSwarmName != "backend-fix" || len(loaded.Messages) != 1 || loaded.Messages[0].Body != "durable event" {
		t.Fatalf("timeline calls=%d swarm=%q messages=%+v", local.getSwarmTimelineCalls, local.lastSwarmName, loaded.Messages)
	}
}

func TestLoadSwarmTabLoadsSwarmsAndTimelineWithoutWatchLease(t *testing.T) {
	local := &fakeLocal{
		swarms:        []tracker.Swarm{{Name: "backend-fix", Main: tracker.SwarmMember{Name: "planner", TargetAddress: "planner"}}},
		swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "durable event"}},
	}
	cmd := loadSwarmTab(model{mode: swarmView, local: local, swarms: []swarmRow{{Name: "backend-fix"}}})
	batch, ok := cmd().(tea.BatchMsg)
	if !ok || len(batch) != 2 {
		t.Fatalf("loadSwarmTab msg = %#v", batch)
	}
	for _, child := range batch {
		_ = child()
	}
	if local.listSwarmsCalls != 1 || local.getSwarmTimelineCalls != 1 || local.lastSwarmName != "backend-fix" {
		t.Fatalf("list calls=%d timeline calls=%d swarm=%q", local.listSwarmsCalls, local.getSwarmTimelineCalls, local.lastSwarmName)
	}
}

func TestSwarmConfiguredOfflineMembersRenderState(t *testing.T) {
	main := agentRow{Name: "planner", TargetAddress: "planner", Role: "main", Running: boolPtr(true)}
	m := model{mode: swarmView, swarms: []swarmRow{{
		Name: "backend-fix",
		Main: main,
		Members: []agentRow{
			main,
			{Name: "coder-a", Role: "subagent", Configured: boolPtr(true), Running: boolPtr(false), Launchable: boolPtr(true)},
			{Name: "dawnstar/reviewer", Role: "subagent", Scope: "remote", TargetAddress: "dawnstar/reviewer", Running: boolPtr(true), Launchable: boolPtr(false)},
		},
	}}}
	sidebar := m.swarmSidebarView(120, 24)
	for _, want := range []string{"coder-a", "configured offline", "launchable", "dawnstar/reviewer", "non-launchable"} {
		if !strings.Contains(sidebar, want) {
			t.Fatalf("swarm sidebar missing %q:\n%s", want, sidebar)
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
	if local.sentSwarmContext != "backend-fix" {
		t.Fatalf("swarm context = %q, want backend-fix", local.sentSwarmContext)
	}
}

func TestSwarmMissingMainDoesNotSubmitAndPreservesDraft(t *testing.T) {
	local := &fakeLocal{}
	m := model{mode: swarmView, local: local, composer: []rune("keep draft"), swarms: []swarmRow{{Name: "backend-fix", MainMissing: true, Warning: "No main agent configured/running"}}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || string(m.composer) != "keep draft" || local.sentTo != "" || m.err == nil {
		t.Fatalf("missing-main submit cmd=%v composer=%q sentTo=%q err=%v", cmd, string(m.composer), local.sentTo, m.err)
	}
	panel := m.conversationPanel(80, 20)
	if !strings.Contains(panel, "No main agent") || !strings.Contains(panel, "/swarm") || strings.Contains(panel, "/msg") {
		t.Fatalf("missing-main composer should preserve draft and advertise swarm create, not /msg:\n%s", panel)
	}
}

func TestSwarmOfflineMainDoesNotSubmitAndPreservesDraft(t *testing.T) {
	local := &fakeLocal{}
	m := model{mode: swarmView, local: local, composer: []rune("keep draft"), swarms: []swarmRow{{
		Name:    "backend-fix",
		Main:    agentRow{Name: "planner", Role: "main", Configured: boolPtr(true), Running: boolPtr(false), Launchable: boolPtr(true)},
		Members: []agentRow{{Name: "planner", Role: "main", Configured: boolPtr(true), Running: boolPtr(false), Launchable: boolPtr(true)}},
	}}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || string(m.composer) != "keep draft" || local.sentTo != "" || m.err == nil {
		t.Fatalf("offline-main submit cmd=%v composer=%q sentTo=%q err=%v", cmd, string(m.composer), local.sentTo, m.err)
	}
	panel := m.conversationPanel(100, 20)
	if !strings.Contains(panel, "keep draft") || !strings.Contains(panel, "/swarm") || strings.Contains(panel, "/msg") {
		t.Fatalf("offline-main composer should preserve draft and advertise swarm create, not /msg:\n%s", panel)
	}
	view := strings.Join(m.messageLinesForWidth(100), "\n")
	if !strings.Contains(view, "configured offline") || !strings.Contains(view, "Swarm messaging is disabled") {
		t.Fatalf("offline-main view missing state/warning:\n%s", view)
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

func TestSwarmTimelineMessagesUseIncomingBubbleBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}, swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "please fix"}}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")

	assertNoResetToRawSpace(t, "swarm incoming bubble", view)
	assertVisibleCellsHaveBackground(t, "swarm incoming bubble", view)
	assertContains(t, "swarm incoming bubble", view, "48;2;52;72;63", "planner → coder-a", "please fix")
}

func TestSwarmTimelineMarkdownIsRenderedWithBubbleBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}, swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "See [docs](https://example.com/docs) and `code`", ContentType: "text/markdown"}}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")

	assertNoResetToRawSpace(t, "swarm markdown bubble", view)
	assertVisibleCellsHaveBackground(t, "swarm markdown bubble", view)
	assertContains(t, "swarm markdown bubble", view, "48;2;52;72;63", "docs", "code")
}

func TestSwarmTimelineReceiptStaysInsideBubbleBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}, swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "please fix"}}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")
	receipt := renderedLineContaining(t, view, "sent")

	assertContains(t, "swarm timeline receipt", receipt, "48;2;52;72;63", "sent")
	assertNotContains(t, "swarm timeline receipt", receipt, "48;2;45;53;59", "48;2;44;52;59")
	assertNoResetToRawSpace(t, "swarm timeline receipt", receipt)
}

func TestSwarmViewIncludesLocalSentToMainMessages(t *testing.T) {
	forceTrueColor(t)
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
	assertNoResetToRawSpace(t, "swarm local sent bubble", view)
	assertVisibleCellsHaveBackground(t, "swarm local sent bubble", view)
	assertContains(t, "swarm local sent bubble", view, "48;2;52;72;63")
	receipt := renderedLineContaining(t, view, "sent")
	assertContains(t, "swarm local sent receipt", receipt, "48;2;52;72;63", "sent")
	assertNotContains(t, "swarm local sent receipt", receipt, "48;2;45;53;59", "48;2;44;52;59")
}

func TestSwarmPaneCaptureKeepsCaptureBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{mode: swarmView, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}, swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: testPaneCaptureBody(12)}}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")

	assertContains(t, "swarm pane capture", view, "planner → coder-a", "▣ pane capture", "48;2;60;72;77")
	if strings.Contains(view, "48;2;52;72;63") {
		t.Fatalf("swarm pane capture should preserve CapturePaneBg instead of normal incoming bubble background:\n%s", view)
	}
}

func TestSwarmSelectionRailKeepsIncomingBubbleBackground(t *testing.T) {
	forceTrueColor(t)
	m := model{mode: swarmView, messageSelected: 0, swarms: []swarmRow{{Name: "backend-fix", Main: agentRow{Name: "planner", TargetAddress: "planner"}}}, swarmMessages: []tracker.SwarmTimelineMessage{{Sender: "planner", Recipient: "coder-a", Body: "selected body"}}}
	view := strings.Join(m.messageLinesForWidth(100), "\n")

	assertContains(t, "swarm selected rail", view, "┃", "48;2;52;72;63", "selected body")
	assertNoResetToRawSpace(t, "swarm selected rail", view)
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
		Main: tracker.SwarmMember{Name: "planner", Role: "main", TargetAddress: "planner", Configured: boolPtr(true), Running: boolPtr(true), Launchable: boolPtr(true)},
		Members: []tracker.SwarmMember{
			{Name: "planner", Role: "main", TargetAddress: "planner", Configured: boolPtr(true), Running: boolPtr(true), Launchable: boolPtr(true)},
			{Name: "coder-a", Role: "subagent", Configured: boolPtr(true), Running: boolPtr(false), Launchable: boolPtr(true)},
		},
		Warnings: []string{"duplicate main"},
	}})
	if len(rows) != 1 || rows[0].Main.Name != "planner" || len(rows[0].Members) != 2 || !strings.Contains(rows[0].Warning, "duplicate main") {
		t.Fatalf("rows=%+v", rows)
	}
	if rows[0].Main.TargetAddress != "planner" || !boolPtrTrue(rows[0].Main.Running) || !boolPtrTrue(rows[0].Main.Launchable) {
		t.Fatalf("main launchability fields not mapped: %+v", rows[0].Main)
	}
	if rows[0].Members[1].TargetAddress != "" || !boolPtrTrue(rows[0].Members[1].Configured) || !boolPtrFalse(rows[0].Members[1].Running) || !boolPtrTrue(rows[0].Members[1].Launchable) {
		t.Fatalf("offline member fields not mapped: %+v", rows[0].Members[1])
	}
}
