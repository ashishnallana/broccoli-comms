package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func TestTasksTabRegisteredAndReadOnly(t *testing.T) {
	m := model{mode: memoryView, local: &fakeLocal{}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlT})
	m = updated.(model)
	if m.mode != tasksView || !m.tasksLoading || cmd == nil {
		t.Fatalf("ctrl-t from memory should open/load tasks, mode=%v loading=%v cmd=%v", m.mode, m.tasksLoading, cmd)
	}
	if m.activeTabCanCompose() {
		t.Fatal("tasks tab should disable composer")
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("hello")})
	m = updated.(model)
	if cmd != nil || string(m.composer) != "" {
		t.Fatalf("typing in tasks tab changed composer=%q cmd=%v", string(m.composer), cmd)
	}
}

func TestTaskDataBucketsActiveChainInRequiredOrder(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "coder", CurrentTaskID: "task-current", CurrentTask: "Build feature"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "root", Title: "Root", Status: "ready", CreatedAt: "2026-01-01T00:00:00Z"},
			{TaskID: "task-current", Title: "Current", Status: "ready", DependsOn: []string{"root"}, CreatedAt: "2026-01-01T00:01:00Z"},
			{TaskID: "task-next", Title: "Next", Status: "ready", DependsOn: []string{"task-current"}, CreatedAt: "2026-01-01T00:02:00Z"},
			{TaskID: "task-blocked", Title: "Blocked", Status: "blocked", BlockedReason: "needs context", DependsOn: []string{"task-current"}, CreatedAt: "2026-01-01T00:03:00Z"},
			{TaskID: "task-review", Title: "Review", Status: "review", DependsOn: []string{"task-current"}, CreatedAt: "2026-01-01T00:04:00Z"},
			{TaskID: "task-done", Title: "Done", Status: "done", DependsOn: []string{"task-current"}, CreatedAt: "2026-01-01T00:05:00Z"},
			{TaskID: "other", Title: "Other chain", Status: "ready", CreatedAt: "2026-01-02T00:00:00Z"},
		},
		tasksStates:    []taskWorkingState{{TaskID: "task-current", Agent: "coder", Status: "working", TaskChainID: "chain-1", RootTaskID: "root"}},
		tasksApprovals: []taskApprovalRecord{{ApprovalID: "apr-1", TaskID: "task-review", TaskChainID: "chain-1", RootTaskID: "root", Status: "pending"}},
	}
	data := m.taskData()
	if data.ActiveChainID != "" || data.RootTaskID != "" || data.CurrentTaskID != "" {
		t.Fatalf("task-oriented focus should not treat selection as current = %q/%q/%q", data.ActiveChainID, data.RootTaskID, data.CurrentTaskID)
	}
	if len(data.Tasks) != 6 {
		t.Fatalf("open task count=%d want 6", len(data.Tasks))
	}
	got := []string{}
	for _, bucket := range data.Buckets {
		if len(bucket.Tasks) > 0 {
			got = append(got, bucket.Name+":"+bucket.Tasks[0].TaskID)
		}
	}
	want := []string{"Current:task-current", "Next:root", "Queue:task-blocked", "Review:task-review"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("bucket order=%v want %v", got, want)
	}
	if data.Counts.Blocked != 1 || len(data.Blockers) != 1 || data.Blockers[0] != "needs context" {
		t.Fatalf("blockers/counts = %+v blockers=%v", data.Counts, data.Blockers)
	}
}

func TestTaskSelectionDoesNotChangeStatusBuckets(t *testing.T) {
	m := model{tasksItems: []taskRecord{
		{TaskID: "task-working", Title: "Working", Status: "working"},
		{TaskID: "task-ready", Title: "Ready", Status: "ready"},
		{TaskID: "task-blocked", Title: "Blocked", Status: "blocked"},
	}}
	m.tasksSelected = 1
	data := m.taskData()
	got := []string{}
	for _, bucket := range data.Buckets {
		if len(bucket.Tasks) > 0 {
			got = append(got, bucket.Name+":"+bucket.Tasks[0].TaskID)
		}
	}
	want := []string{"Current:task-working", "Next:task-ready", "Queue:task-blocked"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("bucket order changed with selection=%d: got %v want %v", m.tasksSelected, got, want)
	}
	m.tasksSelected = 2
	data = m.taskData()
	got = got[:0]
	for _, bucket := range data.Buckets {
		if len(bucket.Tasks) > 0 {
			got = append(got, bucket.Name+":"+bucket.Tasks[0].TaskID)
		}
	}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("bucket order changed after moving selection=%d: got %v want %v", m.tasksSelected, got, want)
	}
}

func TestDonePendingReviewHandoffRemainsVisibleInReviewBucket(t *testing.T) {
	m := model{tasksItems: []taskRecord{{
		TaskID: "task-done-review", Title: "Done awaiting review", Status: "done", Participants: []taskParticipant{{Agent: "reviewer", Role: "reviewer", Status: "active"}},
	}}, tasksApprovals: []taskApprovalRecord{{ApprovalID: "apr-1", TaskID: "task-done-review", Status: "pending"}}}
	data := m.taskData()
	if len(data.Tasks) != 1 || data.Tasks[0].TaskID != "task-done-review" {
		t.Fatalf("done review handoff should remain visible: %+v", data.Tasks)
	}
	if len(data.Buckets) < 4 || len(data.Buckets[3].Tasks) != 1 || data.Buckets[3].Name != "Review" {
		t.Fatalf("done review handoff should be bucketed under Review: %+v", data.Buckets)
	}
}

func TestTaskOrientedViewShowsOpenTasksIndependentOfSelectedAgent(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "coder"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-review", Title: "Reviewer task", Status: "ready", AssignedAgent: "reviewer"},
		},
		tasksApprovals: []taskApprovalRecord{{ApprovalID: "apr-review", TaskID: "task-review", Status: "pending"}},
	}
	data := m.taskData()
	if len(data.Tasks) != 1 || data.Tasks[0].TaskID != "task-review" {
		t.Fatalf("task-oriented view should show open tasks independent of selected agent: %+v", data.Tasks)
	}
	if len(data.Approvals) != 1 {
		t.Fatalf("task-oriented view should include open task approvals: %+v", data.Approvals)
	}
	view := m.taskManagementView(100, 12)
	if !strings.Contains(view, "Reviewer task") {
		t.Fatalf("view missing open task:\n%s", view)
	}
}

func TestTaskOrientedViewShowsOpenApprovals(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "coder"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-queued", Title: "Queued", Status: "queued", AssignedAgent: "coder"},
			{TaskID: "task-done", Title: "Done", Status: "done", AssignedAgent: "coder"},
			{TaskID: "task-other", Title: "Other", Status: "ready", AssignedAgent: "reviewer"},
		},
		tasksApprovals: []taskApprovalRecord{{ApprovalID: "apr-coder", TaskID: "task-queued", Status: "pending"}, {ApprovalID: "apr-other", TaskID: "task-other", Status: "pending"}},
	}
	data := m.taskData()
	if len(data.Tasks) != 2 || len(data.Approvals) != 2 {
		t.Fatalf("task-oriented tasks/approvals = tasks=%+v approvals=%+v", data.Tasks, data.Approvals)
	}
	view := m.taskManagementView(120, 20)
	for _, want := range []string{"Queued", "Other", "apr-coder", "apr-other"} {
		if !strings.Contains(view, want) {
			t.Fatalf("task-oriented view missing %q:\n%s", want, view)
		}
	}
	if strings.Contains(view, "Done") {
		t.Fatalf("completed task leaked into open task view:\n%s", view)
	}
}

func TestTaskOrientedTaskDataIncludesOpenTasksOnly(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "coder", CurrentTaskID: "task-current"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-current", Title: "Current", Status: "working", AssignedAgent: "coder"},
			{TaskID: "task-queued", Title: "Queued", Status: "ready", AssignedAgent: "coder"},
			{TaskID: "task-done", Title: "Done", Status: "done", AssignedAgent: "coder"},
			{TaskID: "task-other", Title: "Other agent task", Status: "ready", AssignedAgent: "reviewer"},
		},
		tasksStates:    []taskWorkingState{{TaskID: "task-current", Agent: "coder", Status: "working", TaskChainID: "chain-1", RootTaskID: "root"}},
		tasksApprovals: []taskApprovalRecord{{ApprovalID: "apr-coder", TaskID: "task-queued", Status: "pending"}, {ApprovalID: "apr-other", TaskID: "task-other", Status: "pending"}},
	}
	data := m.taskData()
	if len(data.Tasks) != 3 {
		t.Fatalf("task-oriented open tasks = %+v", data.Tasks)
	}
	view := m.taskManagementView(120, 20)
	if strings.Contains(view, "Done") || strings.Contains(view, "Completed") {
		t.Fatalf("completed task leaked into open task view:\n%s", view)
	}
	for _, want := range []string{"Current", "Queued", "Other agent task"} {
		if !strings.Contains(view, want) {
			t.Fatalf("task-oriented view missing %q:\n%s", want, view)
		}
	}
}

func TestArchivedTasksAreHiddenFromActiveQueueAndCounts(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "coder", CurrentTaskID: "task-current"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-current", Title: "Current", Status: "working", AssignedAgent: "coder"},
			{TaskID: "task-ready", Title: "Ready", Status: "ready", AssignedAgent: "coder", DependsOn: []string{"task-current"}},
			{TaskID: "task-archived", Title: "Archived", Status: "archived", AssignedAgent: "coder", DependsOn: []string{"task-current"}},
		},
		tasksStates: []taskWorkingState{{TaskID: "task-current", Agent: "coder", Status: "working", TaskChainID: "chain-1", RootTaskID: "task-current"}},
	}
	data := m.taskData()
	for _, task := range data.Tasks {
		if task.TaskID == "task-archived" {
			t.Fatalf("archived task leaked into task data: %+v", data.Tasks)
		}
	}
	if data.Counts.Total != 2 {
		t.Fatalf("active counts include archived task: %+v", data.Counts)
	}
	view := m.taskManagementView(120, 20)
	if strings.Contains(view, "Archived") {
		t.Fatalf("archived task leaked into Tasks view:\n%s", view)
	}
	sidebar := strings.Join(m.taskAgentSidebarLines(data, 60, 4), "\n")
	if !strings.Contains(sidebar, "2 tasks") || strings.Contains(sidebar, "3 tasks") {
		t.Fatalf("sidebar counts should exclude archived tasks:\n%s", sidebar)
	}
}

func TestSelectedAgentWithArchivedCurrentTaskShowsNoDurableQueue(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "coder", CurrentTaskID: "task-archived"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-archived", Title: "Archived current", Status: "archived", AssignedAgent: "coder"},
			{TaskID: "task-child", Title: "Archived child", Status: "ready", AssignedAgent: "coder", DependsOn: []string{"task-archived"}},
		},
		tasksStates: []taskWorkingState{{TaskID: "task-archived", Agent: "coder", Status: "working", TaskChainID: "chain-1", RootTaskID: "task-archived"}},
	}
	data := m.taskData()
	if len(data.Tasks) != 0 || data.Counts.Total != 0 {
		t.Fatalf("archived current task should hide durable queue, tasks=%+v counts=%+v", data.Tasks, data.Counts)
	}
	view := m.taskManagementView(120, 20)
	if strings.Contains(view, "Archived current") || strings.Contains(view, "Archived child") {
		t.Fatalf("archived current chain leaked into Tasks view:\n%s", view)
	}
}

func TestSelectedRemoteAgentMatchesAssignedAgentName(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "host/coder", AgentName: "coder", TargetAddress: "host.example/coder", CurrentTaskID: "task-current"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-current", Title: "Current", Status: "working", AssignedAgent: "coder"},
			{TaskID: "task-queued", Title: "Queued", Status: "ready", AssignedAgent: "coder"},
			{TaskID: "task-done", Title: "Done", Status: "validated", ResultStatus: "good", AssignedAgent: "coder"},
			{TaskID: "task-other", Title: "Other", Status: "ready", AssignedAgent: "reviewer"},
		},
		tasksStates: []taskWorkingState{{TaskID: "task-current", Agent: "coder", Status: "working", TaskChainID: "chain-1", RootTaskID: "root"}},
	}
	data := m.taskData()
	if len(data.Tasks) != 3 {
		t.Fatalf("task-oriented remote row data should include all open tasks: %+v", data.Tasks)
	}
	view := m.taskManagementView(120, 20)
	for _, want := range []string{"Current", "Queued", "Other"} {
		if !strings.Contains(view, want) {
			t.Fatalf("task-oriented view missing %q:\n%s", want, view)
		}
	}
	if strings.Contains(view, "Done") || strings.Contains(view, "Completed") {
		t.Fatalf("completed task leaked into open task view:\n%s", view)
	}
}

func TestSelectedRemoteAgentUsesRegistryCurrentTaskWhenTaskListUnavailable(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "host/coder", Scope: "remote", AgentName: "coder", TargetAddress: "host.example/coder", CurrentTaskID: "remote-task", CurrentTask: "Remote feature", CurrentTaskStatus: "working", CurrentTaskNextStep: "ship"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "local-task", Title: "Local only", Status: "ready", AssignedAgent: "local"},
		},
	}
	data := m.taskData()
	if len(data.Tasks) != 1 || data.Tasks[0].TaskID != "local-task" {
		t.Fatalf("task-oriented view should prefer durable open tasks over remote current fallback: %+v", data.Tasks)
	}
	view := m.taskManagementView(120, 20)
	if !strings.Contains(view, "Local only") {
		t.Fatalf("task-oriented view missing durable task:\n%s", view)
	}
}

func TestSelectedRemoteAgentDoesNotUseCollidingLocalCurrentTask(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "host/coder", Scope: "remote", AgentName: "coder", TargetAddress: "host.example/coder", CurrentTaskID: "task-same", CurrentTask: "Remote task"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-same", Title: "Unrelated local", Status: "working", AssignedAgent: "reviewer"},
			{TaskID: "task-child", Title: "Unrelated child", Status: "ready", AssignedAgent: "reviewer", DependsOn: []string{"task-same"}},
		},
		tasksStates:    []taskWorkingState{{TaskID: "task-same", Agent: "reviewer", Status: "working", TaskChainID: "chain-local", RootTaskID: "task-same"}},
		tasksApprovals: []taskApprovalRecord{{ApprovalID: "apr-local", TaskID: "task-same", TaskChainID: "chain-local", RootTaskID: "task-same", Status: "pending"}},
	}
	data := m.taskData()
	if len(data.Tasks) != 2 || len(data.Approvals) != 1 {
		t.Fatalf("task-oriented local tasks/approvals = tasks %+v approvals %+v", data.Tasks, data.Approvals)
	}
	view := m.taskManagementView(120, 20)
	if !strings.Contains(view, "Unrelated local") || !strings.Contains(view, "Unrelated child") {
		t.Fatalf("task-oriented view missing local open tasks:\n%s", view)
	}
}

func TestRemoteAgentSidebarCountsUseAgentName(t *testing.T) {
	m := model{
		rows:       []agentRow{{Name: "host/coder", Scope: "remote", AgentName: "coder", TargetAddress: "host.example/coder"}},
		tasksItems: []taskRecord{{TaskID: "task-1", AssignedAgent: "coder"}, {TaskID: "task-2", AssignedAgent: "coder"}},
	}
	view := strings.Join(m.taskAgentSidebarLines(m.taskData(), 60, 4), "\n")
	if !strings.Contains(view, "2 tasks") {
		t.Fatalf("remote sidebar count should use agent name aliases:\n%s", view)
	}
}

func TestTaskOrderingPrefersDependenciesForInsertions(t *testing.T) {
	items := []taskRecord{
		{TaskID: "task-z", Title: "Inserted", Status: "ready", DependsOn: []string{"task-m"}},
		{TaskID: "task-m", Title: "Selected", Status: "ready"},
	}
	buckets := bucketTasks(items, "", map[string]taskWorkingState{}, map[string][]taskApprovalRecord{})
	rows := orderedTaskRows(buckets)
	if len(rows) < 2 || rows[0].TaskID != "task-m" || rows[1].TaskID != "task-z" {
		t.Fatalf("dependency insertion order = %+v, want selected before dependent", rows)
	}
}

func TestTasksTabDoesNotTrapAgentOrTaskNavigation(t *testing.T) {
	m := model{
		mode:     tasksView,
		local:    &fakeLocal{},
		rows:     []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}},
		selected: 0,
		tasksItems: []taskRecord{
			{TaskID: "task-1", Title: "One", Status: "ready", AssignedAgent: "alpha"},
			{TaskID: "task-2", Title: "Two", Status: "ready", AssignedAgent: "alpha", DependsOn: []string{"task-1"}},
			{TaskID: "task-3", Title: "Other chain", Status: "ready", AssignedAgent: "beta"},
		},
	}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	m = updated.(model)
	if m.selected != 1 || !m.tasksLoading || cmd == nil {
		t.Fatalf("ctrl-n should move selected agent and reload tasks, selected=%d loading=%v cmd=%v", m.selected, m.tasksLoading, cmd)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyCtrlP})
	m = updated.(model)
	if m.selected != 0 || !m.tasksLoading || cmd == nil {
		t.Fatalf("ctrl-p should move selected agent and reload tasks, selected=%d loading=%v cmd=%v", m.selected, m.tasksLoading, cmd)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = updated.(model)
	if m.tasksSelected != 1 || cmd != nil {
		t.Fatalf("down should move chain selection without trapping, selected=%d cmd=%v", m.tasksSelected, cmd)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("k")})
	m = updated.(model)
	if m.tasksSelected != 0 || cmd != nil {
		t.Fatalf("k should move task selection up, selected=%d cmd=%v", m.tasksSelected, cmd)
	}
}

func TestTaskSelectionUsesOffsetInSmallViewport(t *testing.T) {
	items := make([]taskRecord, 0, 12)
	for i := 0; i < 12; i++ {
		items = append(items, taskRecord{TaskID: "task-" + string(rune('a'+i)), Title: "Task " + string(rune('A'+i)), Status: "ready"})
	}
	m := model{mode: tasksView, width: 80, height: 12, tasksItems: items}
	for i := 0; i < 8; i++ {
		updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyDown})
		m = updated.(model)
	}
	if m.tasksSelected != 8 || m.tasksOffset != 8 {
		t.Fatalf("selection/offset = %d/%d, want 8/8", m.tasksSelected, m.tasksOffset)
	}
	view := m.taskManagementView(80, 8)
	if !strings.Contains(view, "Task I") {
		t.Fatalf("small viewport should render selected offset task:\n%s", view)
	}
	if strings.Contains(view, "Task A") {
		t.Fatalf("small viewport should scroll past first task after offset:\n%s", view)
	}
}

func TestTaskManagementViewResponsiveStates(t *testing.T) {
	m := model{mode: tasksView, width: 120, height: 24, rows: []agentRow{{Name: "coder", Status: "online", CurrentTaskID: "task-1", CurrentTask: "Implement Tasks tab"}, {Name: "reviewer", Status: "idle"}}, tasksItems: []taskRecord{{TaskID: "task-1", Title: "Implement Tasks tab", Status: "working", AssignedAgent: "coder"}, {TaskID: "task-2", Title: "Follow-up", Status: "ready", AssignedAgent: "coder", DependsOn: []string{"task-1"}}, {TaskID: "task-3", Title: "Reviewed", Status: "done", AssignedAgent: "reviewer", DependsOn: []string{"task-1"}}}, tasksStates: []taskWorkingState{{TaskID: "task-1", Agent: "coder", Status: "working", TaskChainID: "chain-1", RootTaskID: "root"}}}
	wide := m.taskManagementView(120, 20)
	for _, want := range []string{"Tasks", "Task details", "Selected task", "Participants", "Agents", "Implement Tasks tab", "online"} {
		if !strings.Contains(wide, want) {
			t.Fatalf("wide tasks view missing %q:\n%s", want, wide)
		}
	}
	narrow := m.taskManagementView(60, 20)
	if strings.Contains(narrow, "Task details") {
		t.Fatalf("narrow tasks view should hide right details column:\n%s", narrow)
	}
	for i, line := range strings.Split(narrow, "\n") {
		if got := lipgloss.Width(line); got > 60 {
			t.Fatalf("narrow line width=%d > 60 at line %d: %q\n%s", got, i, line, narrow)
		}
	}
	if strings.Contains(wide, "Reviewed") || strings.Contains(wide, "✓") {
		t.Fatalf("completed history should be hidden from default open-task view:\n%s", wide)
	}
	m.tasksLoading = true
	if view := m.taskManagementView(80, 10); !strings.Contains(view, "Loading tasks") {
		t.Fatalf("loading view missing state:\n%s", view)
	}
	m.tasksLoading = false
	m.tasksErr = assertErr("boom")
	if view := m.taskManagementView(80, 10); !strings.Contains(view, "Tasks load failed") {
		t.Fatalf("error view missing state:\n%s", view)
	}
}

func TestTaskActionHintsAndConfirmation(t *testing.T) {
	m := model{mode: tasksView, tasksItems: []taskRecord{{TaskID: "task-1", Title: "One", Status: "ready"}}}
	view := m.taskManagementView(140, 12)
	for _, want := range []string{"ctrl-k commands", "ctrl-n/ctrl-p agent", "↑/↓ task", "r refresh", "forms use field-aware autocomplete"} {
		if !strings.Contains(view, want) {
			t.Fatalf("tasks hints missing %q:\n%s", want, view)
		}
	}
	for _, dead := range []string{"a add after", "n new chain", "d/D archive", "x/X assign"} {
		if strings.Contains(view, dead) {
			t.Fatalf("tasks hints should not advertise direct action %q:\n%s", dead, view)
		}
	}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyCtrlK})
	m = updated.(model)
	if cmd != nil || !m.tasksPalette.Open {
		t.Fatalf("ctrl-k should open task command palette, palette=%+v cmd=%v", m.tasksPalette, cmd)
	}
	palette := m.taskManagementView(100, 20)
	for _, want := range []string{"Task commands", "Open details", "Edit next step", "Edit title/description", "Mark complete", "Add selected agent as reviewer", "Deactivate selected agent reviewer role", "Change selected agent reviewer to verifier", "Remove task (archive)", "Delete task", "not supported by task CLI", "Add task after selected"} {
		if !strings.Contains(palette, want) {
			t.Fatalf("palette missing %q:\n%s", want, palette)
		}
	}
	m.tasksPalette = taskCommandPaletteState{}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("d")})
	m = updated.(model)
	if cmd != nil || m.tasksConfirm.Active() {
		t.Fatalf("direct d shortcut should be inert outside palette, confirm=%+v cmd=%v", m.tasksConfirm, cmd)
	}
	m.tasksPalette = taskCommandPaletteState{Open: true, Selected: 14}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || !m.tasksConfirm.Active() || m.tasksConfirm.Action != "archive" {
		t.Fatalf("palette remove/archive should request confirmation, confirm=%+v cmd=%v", m.tasksConfirm, cmd)
	}
	if view := m.taskManagementView(140, 12); !strings.Contains(view, "Confirm:") || !strings.Contains(view, "esc cancel") {
		t.Fatalf("confirmation should render clearly:\n%s", view)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = updated.(model)
	if cmd != nil || m.tasksConfirm.Active() {
		t.Fatalf("esc should cancel confirmation, confirm=%+v cmd=%v", m.tasksConfirm, cmd)
	}
	m.tasksPalette = taskCommandPaletteState{Open: true, Selected: 15}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || !m.directInputStatusErr || !strings.Contains(m.directInputStatus, "not supported by task CLI") {
		t.Fatalf("disabled delete should explain unsupported capability, status=%q err=%v cmd=%v", m.directInputStatus, m.directInputStatusErr, cmd)
	}
}

func TestTaskArchiveConfirmationEnterExecutesDocumentedAction(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{}, args...))
		return []byte(`{}`), nil
	}
	m := model{mode: tasksView, tasksItems: []taskRecord{{TaskID: "task-1", Title: "One", Status: "ready"}}}
	m.tasksPalette = taskCommandPaletteState{Open: true, Selected: 14}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || !m.tasksConfirm.Active() || !strings.Contains(m.directInputStatus, "press enter again") {
		t.Fatalf("first remove should arm confirmation, confirm=%+v status=%q cmd=%v", m.tasksConfirm, m.directInputStatus, cmd)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd == nil || m.tasksConfirm.Active() || !m.tasksLoading {
		t.Fatalf("second enter should execute archive, loading=%v confirm=%+v cmd=%v", m.tasksLoading, m.tasksConfirm, cmd)
	}
	msg := cmd().(taskActionResult)
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task update task-1 --json --status archived" {
		t.Fatalf("archive confirmation msg=%+v calls=%v", msg, calls)
	}
}

func TestTaskParticipantAgentNamePrefersCanonicalAgentName(t *testing.T) {
	row := agentRow{Name: "host/coder", AgentName: "coder", TargetAddress: "host.example/coder"}
	if got := taskParticipantAgentName(row); got != "coder" {
		t.Fatalf("participant agent name = %q, want coder", got)
	}
	if got := taskParticipantAgentName(agentRow{Name: "local"}); got != "local" {
		t.Fatalf("local participant agent name = %q", got)
	}
}

func TestTaskActionCommandsAndEditorOutcomes(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{}, args...))
		return []byte(`{}`), nil
	}
	msg := taskActionCmd(taskRecord{TaskID: "task-1"}, "assign", "coder")().(taskActionResult)
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task update task-1 --json --assign-agent coder" {
		t.Fatalf("assign msg=%+v calls=%v", msg, calls)
	}
	calls = nil
	msg = taskActionCmd(taskRecord{TaskID: "task-1"}, "complete", "coder")().(taskActionResult)
	if msg.Err != nil || msg.Status != "Task marked complete" || len(calls) != 1 || strings.Join(calls[0], " ") != "task update task-1 --json --status done" {
		t.Fatalf("complete msg=%+v calls=%v", msg, calls)
	}
	calls = nil
	msg = taskParticipantActionCmd(taskRecord{TaskID: "task-1"}, "reviewer", "reviewer-agent")().(taskActionResult)
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task participant add task-1 --agent reviewer-agent --role reviewer --json" {
		t.Fatalf("participant reviewer msg=%+v calls=%v", msg, calls)
	}
	calls = nil
	msg = taskParticipantDeactivateCmd(taskRecord{TaskID: "task-1"}, taskParticipant{ParticipantID: "part-1", Agent: "reviewer-agent", Role: "reviewer"})().(taskActionResult)
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task participant update part-1 --status inactive --json" {
		t.Fatalf("participant deactivate msg=%+v calls=%v", msg, calls)
	}
	calls = nil
	msg = taskParticipantChangeRoleCmd(taskRecord{TaskID: "task-1"}, taskParticipant{ParticipantID: "part-1", Agent: "reviewer-agent", Role: "reviewer"}, "verifier", "reviewer-agent")().(taskActionResult)
	if msg.Err != nil || len(calls) != 2 || strings.Join(calls[0], " ") != "task participant update part-1 --status inactive --json" || strings.Join(calls[1], " ") != "task participant add task-1 --agent reviewer-agent --role verifier --json" {
		t.Fatalf("participant change-role msg=%+v calls=%v", msg, calls)
	}
	calls = nil
	edit := updateTaskField("task-1", "next_step", "Run tests")
	if edit.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task update task-1 --json --next-step Run tests" {
		t.Fatalf("edit msg=%+v calls=%v", edit, calls)
	}
	if unchanged := updateTaskField("task-1", "unknown", "x"); unchanged.Err == nil {
		t.Fatalf("unsupported field should fail")
	}
}

func TestTaskFormAutocompleteIsFieldAwareAndPreservesDefaultDepends(t *testing.T) {
	m := model{rows: []agentRow{{Name: "coder"}}, tasksItems: []taskRecord{{TaskID: "task-1", Priority: "P1"}, {TaskID: "task-2", Status: "ready"}}, tasksStates: []taskWorkingState{{TaskID: "task-2", TaskChainID: "chain-1", RootTaskID: "root-1"}}}
	if got := m.taskFormAutocompleteOptions(0, "cod"); len(got) != 0 {
		t.Fatalf("title field should not autocomplete structured refs: %+v", got)
	}
	agents := m.taskFormAutocompleteOptions(1, "cod")
	if len(agents) != 1 || agents[0].Kind != "agent" || agents[0].Value != "coder" {
		t.Fatalf("agent field autocomplete = %+v", agents)
	}
	priorities := m.taskFormAutocompleteOptions(2, "P1")
	if len(priorities) == 0 || priorities[0].Kind != "priority" {
		t.Fatalf("priority field autocomplete = %+v", priorities)
	}
	deps := m.taskFormAutocompleteOptions(3, "task")
	for _, option := range deps {
		if option.Kind != "task" && option.Kind != "recent" && option.Kind != "root" {
			t.Fatalf("depends field should not include invalid kind: %+v in %+v", option, deps)
		}
	}
	_, _, _, parsedDeps, err := parseTaskChainForm("Title | coder | P1 | task-2", taskChainFormState{Depends: []string{"task-1"}}, "fallback")
	if err != nil || strings.Join(parsedDeps, ",") != "task-1,task-2" {
		t.Fatalf("default add-after dependency should be preserved, deps=%v err=%v", parsedDeps, err)
	}
}

func TestTaskChainFormAutocompleteAndSubmit(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{}, args...))
		return []byte(`{}`), nil
	}
	m := model{mode: tasksView, rows: []agentRow{{Name: "coder"}}, tasksItems: []taskRecord{{TaskID: "task-1", Title: "One", Status: "ready", Priority: "P1"}}}
	m = m.startTaskChainForm("add_after", []string{"task-1"})
	for _, r := range []rune("Write docs | cod") {
		updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}})
		m = updated.(model)
	}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyTab})
	m = updated.(model)
	if cmd != nil || !strings.Contains(m.tasksForm.Text(), "coder") {
		t.Fatalf("tab should autocomplete form token, form=%q cmd=%v", m.tasksForm.Text(), cmd)
	}
	for _, r := range []rune(" | P2") {
		updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}})
		m = updated.(model)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if !m.tasksLoading || cmd == nil || m.tasksForm.Active {
		t.Fatalf("enter should submit form, loading=%v form=%+v cmd=%v", m.tasksLoading, m.tasksForm, cmd)
	}
	msg := cmd().(taskActionResult)
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task create --title Write docs --priority P2 --json --agent coder --depends-on task-1 --task-chain-id task-1 --root-task-id task-1" {
		t.Fatalf("submit msg=%+v calls=%v", msg, calls)
	}
}

func TestTaskChainCommandsAndAutocomplete(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{}, args...))
		return []byte(`{}`), nil
	}
	msg := createTaskInChainCmd("New task after task-1", "coder", "P2", []string{"task-1"})().(taskActionResult)
	if msg.Err != nil || strings.Join(calls[0], " ") != "task create --title New task after task-1 --priority P2 --json --agent coder --depends-on task-1 --task-chain-id task-1 --root-task-id task-1" {
		t.Fatalf("create-after msg=%+v calls=%v", msg, calls)
	}
	calls = nil
	msg = summarizeTaskChainCmd("chain-1")().(taskActionResult)
	if msg.Err != nil || strings.Join(calls[0], " ") != "task summarize-chain chain-1 --json" {
		t.Fatalf("summary msg=%+v calls=%v", msg, calls)
	}
	calls = nil
	msg = assignTaskChainCmd([]taskRecord{{TaskID: "task-1"}, {TaskID: "task-2", Status: "done"}}, "coder")().(taskActionResult)
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task update task-1 --assign-agent coder --json" {
		t.Fatalf("assign-chain msg=%+v calls=%v", msg, calls)
	}

	m := model{rows: []agentRow{{Name: "coder", CurrentTaskID: "task-1"}}, tasksItems: []taskRecord{{TaskID: "task-2", Status: "ready", Priority: "P1", DependsOn: []string{"task-1"}}}, tasksStates: []taskWorkingState{{TaskID: "task-2", TaskChainID: "chain-1", RootTaskID: "root-1"}}}
	options := m.taskAutocompleteOptions("")
	for _, want := range []taskAutocompleteOption{{Kind: "agent", Value: "coder"}, {Kind: "task", Value: "task-2"}, {Kind: "chain", Value: "chain-1"}, {Kind: "root", Value: "root-1"}, {Kind: "status", Value: "ready"}, {Kind: "priority", Value: "P1"}, {Kind: "recent", Value: "task-1"}} {
		found := false
		for _, got := range options {
			if got == want {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("autocomplete missing %+v in %+v", want, options)
		}
	}
}

func TestTaskEditorHandlesUnchangedAndFailure(t *testing.T) {
	msg := finishTaskEditorContent("task-1", "next_step", "same", "same\n", nil)
	if msg.Err != nil || !strings.Contains(msg.Status, "unchanged") {
		t.Fatalf("same content should leave unchanged, msg=%+v", msg)
	}
	msg = finishTaskEditorContent("task-1", "next_step", "same", "", assertErr("boom"))
	if msg.Err == nil || !strings.Contains(msg.Err.Error(), "editor failed") {
		t.Fatalf("editor failure should report clearly, msg=%+v", msg)
	}
	initial := taskEditorInitialContentForTask(taskRecord{TaskID: "task-1", Title: "Write docs"}, "next_step", "")
	if strings.TrimSpace(initial) == "" || !strings.Contains(initial, "Lines starting with # are ignored") || !strings.Contains(initial, "task-1") || !strings.Contains(initial, "Write docs") {
		t.Fatalf("empty editor initial content should include task scaffold, got %q", initial)
	}
	t.Setenv("EDITOR", "")
	cmd := taskEditorCommand("/tmp/task.md")
	if cmd.Args[0] != "nvim" || strings.Join(cmd.Args, " ") != "nvim -c setlocal modified /tmp/task.md" {
		t.Fatalf("default task editor command = path %q args %v", cmd.Path, cmd.Args)
	}
	t.Setenv("EDITOR", "nano -w")
	cmd = taskEditorCommand("/tmp/task.md")
	if cmd.Args[0] != "nano" || strings.Join(cmd.Args, " ") != "nano -w /tmp/task.md" {
		t.Fatalf("EDITOR args task editor command = path %q args %v", cmd.Path, cmd.Args)
	}
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{}, args...))
		return []byte(`{}`), nil
	}
	msg = finishTaskEditorContent("task-1", "next_step", "", initial+"Write tests\n", nil)
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task update task-1 --json --next-step Write tests" {
		t.Fatalf("scaffold should be stripped on save, msg=%+v calls=%v", msg, calls)
	}
}

func TestLoadTasksCmdParsesTaskStateAndApprovalJSON(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{}, args...))
		switch strings.Join(args, " ") {
		case "task list --include-archived --include-participants --json":
			return json.Marshal([]taskRecord{{TaskID: "task-1", Title: "One"}})
		case "state list --json":
			return json.Marshal([]taskWorkingState{{TaskID: "task-1", Status: "working", TaskChainID: "chain-1"}})
		case "task approval list --json":
			return json.Marshal([]taskApprovalRecord{{ApprovalID: "apr-1", TaskID: "task-1", Status: "pending"}})
		default:
			t.Fatalf("unexpected args: %v", args)
			return nil, nil
		}
	}
	msg := loadTasksCmd()().(tasksLoaded)
	if msg.Err != nil || len(msg.Tasks) != 1 || len(msg.States) != 1 || len(msg.Approvals) != 1 {
		t.Fatalf("loaded msg=%+v", msg)
	}
	if len(calls) != 3 {
		t.Fatalf("calls=%v", calls)
	}
}

func TestChainInvestigationGroupsByChainAndRoot(t *testing.T) {
	m := model{tasksItems: []taskRecord{
		{TaskID: "root", Title: "Root feature", Status: "working", UpdatedAt: "2026-01-01T00:00:00Z"},
		{TaskID: "child", Title: "Child", Status: "ready", DependsOn: []string{"root"}, UpdatedAt: "2026-01-01T00:01:00Z"},
		{TaskID: "other", Title: "Other root", Status: "ready", UpdatedAt: "2026-01-02T00:00:00Z"},
	}, tasksStates: []taskWorkingState{{TaskID: "root", Agent: "coder", Status: "working", TaskChainID: "chain-a", RootTaskID: "root", UpdatedAt: "2026-01-01T00:02:00Z"}}}
	data := m.taskData()
	if len(data.Chains) != 2 {
		t.Fatalf("chains=%+v, want 2", data.Chains)
	}
	var feature taskChainSummary
	for _, chain := range data.Chains {
		if chain.ChainID == "chain-a" {
			feature = chain
		}
	}
	if feature.ChainID == "" || feature.RootTaskID != "root" || feature.RootTitle != "Root feature" || len(feature.Tasks) != 2 {
		t.Fatalf("feature chain summary = %+v", feature)
	}
	if feature.Counts.Working != 1 || feature.Counts.Ready != 1 || feature.CurrentTask.TaskID != "root" || feature.NextTask.TaskID != "child" {
		t.Fatalf("feature counts/current/next = counts %+v current %+v next %+v", feature.Counts, feature.CurrentTask, feature.NextTask)
	}
}

func TestChainInvestigationAgentFilterMatchesParticipantsAndRemoteAliases(t *testing.T) {
	m := model{
		rows: []agentRow{{Name: "host/coder", AgentName: "coder", TargetAddress: "host.example/coder"}},
		tasksItems: []taskRecord{
			{TaskID: "task-coder", Title: "Coder task", Status: "ready", AssignedAgent: "coder", Participants: []taskParticipant{{Agent: "reviewer", Role: "reviewer", Status: "active"}}},
			{TaskID: "task-other", Title: "Other task", Status: "ready", AssignedAgent: "other"},
		},
		tasksStates:      []taskWorkingState{{TaskID: "task-coder", Agent: "coder", Status: "ready"}},
		tasksAgentFilter: []rune("host/coder"),
	}
	data := m.taskData()
	if len(data.Chains) != 1 || len(data.Tasks) != 1 || data.Tasks[0].TaskID != "task-coder" {
		t.Fatalf("remote alias filter data = chains %+v tasks %+v", data.Chains, data.Tasks)
	}
	m.tasksAgentFilter = []rune("reviewer")
	data = m.taskData()
	if len(data.Tasks) != 1 || data.Tasks[0].TaskID != "task-coder" {
		t.Fatalf("participant filter data = %+v", data.Tasks)
	}
}

func TestChainFocusTimelineEnterEscAndNarrowLayout(t *testing.T) {
	m := model{mode: tasksView, width: 100, height: 20, tasksItems: []taskRecord{
		{TaskID: "task-current", Title: "Current work", Status: "working", AssignedAgent: "coder"},
		{TaskID: "task-next", Title: "Next work", Status: "ready", AssignedAgent: "coder", DependsOn: []string{"task-current"}},
	}, tasksStates: []taskWorkingState{{TaskID: "task-current", Agent: "coder", Status: "working", TaskChainID: "chain-1", RootTaskID: "task-current"}}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd != nil || !m.tasksChainFocused || m.tasksSelected != 0 {
		t.Fatalf("enter should focus selected chain, focused=%v selected=%d cmd=%v", m.tasksChainFocused, m.tasksSelected, cmd)
	}
	view := m.taskManagementView(100, 20)
	for _, want := range []string{"Chain Timeline", "Current (1)", "Next (1)", "Current work", "Next work"} {
		if !strings.Contains(view, want) {
			t.Fatalf("focused timeline missing %q:\n%s", want, view)
		}
	}
	narrow := m.taskManagementView(60, 16)
	if strings.Contains(narrow, "Task details") || !strings.Contains(narrow, "Chain Timeline") {
		t.Fatalf("narrow focused layout should hide right details and keep timeline usable:\n%s", narrow)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = updated.(model)
	if cmd != nil || m.tasksChainFocused {
		t.Fatalf("esc should return to chain list, focused=%v cmd=%v", m.tasksChainFocused, cmd)
	}
}

func TestChainInvestigationFilterEmptyStateAndTabChip(t *testing.T) {
	m := model{mode: tasksView, tasksItems: []taskRecord{{TaskID: "task-1", Title: "One", Status: "ready", AssignedAgent: "coder"}}}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyTab})
	m = updated.(model)
	if cmd != nil || string(m.tasksAgentFilter) != "coder" {
		t.Fatalf("tab should cycle to agent chip, filter=%q cmd=%v", string(m.tasksAgentFilter), cmd)
	}
	m.tasksAgentFilter = []rune("missing")
	view := m.taskManagementView(100, 14)
	if !strings.Contains(view, "No chains matching agent filter.") {
		t.Fatalf("filter empty state missing:\n%s", view)
	}
}
