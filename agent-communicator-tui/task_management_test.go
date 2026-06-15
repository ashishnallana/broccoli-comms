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
	if data.ActiveChainID != "chain-1" || data.RootTaskID != "root" || data.CurrentTaskID != "task-current" {
		t.Fatalf("chain/current = %q/%q/%q", data.ActiveChainID, data.RootTaskID, data.CurrentTaskID)
	}
	if len(data.Tasks) != 6 {
		t.Fatalf("chain task count=%d want 6", len(data.Tasks))
	}
	got := []string{}
	for _, bucket := range data.Buckets {
		if len(bucket.Tasks) > 0 {
			got = append(got, bucket.Name+":"+bucket.Tasks[0].TaskID)
		}
	}
	want := []string{"Current:task-current", "Next:root", "Queue:task-blocked", "Review:task-review", "Completed:task-done"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("bucket order=%v want %v", got, want)
	}
	if data.Counts.Blocked != 1 || len(data.Blockers) != 1 || data.Blockers[0] != "needs context" {
		t.Fatalf("blockers/counts = %+v blockers=%v", data.Counts, data.Blockers)
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
			{TaskID: "task-1", Title: "One", Status: "ready"},
			{TaskID: "task-2", Title: "Two", Status: "ready", DependsOn: []string{"task-1"}},
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
		t.Fatalf("down should move task selection without trapping, selected=%d cmd=%v", m.tasksSelected, cmd)
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
	for _, want := range []string{"Tasks", "Task details", "Selected agent", "Agents", "Implement Tasks tab", "agent coder", "chain chain-1", "online", "2 tasks"} {
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
	if !strings.Contains(wide, "✓") {
		t.Fatalf("completed history should render with lower-emphasis check marker:\n%s", wide)
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
	for _, want := range []string{"enter open", "a add after", "n new chain", "p progress", "x/X assign", "d/D archive", "e next step", "u result summary", "form autocomplete: agent, priority, depends refs"} {
		if !strings.Contains(view, want) {
			t.Fatalf("tasks hints missing %q:\n%s", want, view)
		}
	}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("a")})
	m = updated.(model)
	if cmd != nil || !m.tasksForm.Active || m.tasksForm.Action != "add_after" {
		t.Fatalf("advertised a shortcut should open add-after form, form=%+v cmd=%v", m.tasksForm, cmd)
	}
	m.tasksForm = taskChainFormState{}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("n")})
	m = updated.(model)
	if cmd != nil || !m.tasksForm.Active || m.tasksForm.Action != "new_chain" {
		t.Fatalf("advertised n shortcut should open new-chain form, form=%+v cmd=%v", m.tasksForm, cmd)
	}
	m.tasksForm = taskChainFormState{}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("d")})
	m = updated.(model)
	if cmd != nil || !m.tasksConfirm.Active() || m.tasksConfirm.Action != "archive" {
		t.Fatalf("first delete should request confirmation, confirm=%+v cmd=%v", m.tasksConfirm, cmd)
	}
	if view := m.taskManagementView(100, 12); !strings.Contains(view, "Confirm:") || !strings.Contains(view, "esc cancel") {
		t.Fatalf("confirmation should render clearly:\n%s", view)
	}
	updated, cmd = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = updated.(model)
	if cmd != nil || m.tasksConfirm.Active() {
		t.Fatalf("esc should cancel confirmation, confirm=%+v cmd=%v", m.tasksConfirm, cmd)
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
	if msg.Err != nil || len(calls) != 1 || strings.Join(calls[0], " ") != "task create --title Write docs --priority P2 --json --agent coder --depends-on task-1" {
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
	if msg.Err != nil || strings.Join(calls[0], " ") != "task create --title New task after task-1 --priority P2 --json --agent coder --depends-on task-1" {
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
}

func TestLoadTasksCmdParsesTaskStateAndApprovalJSON(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{}, args...))
		switch strings.Join(args, " ") {
		case "task list --include-archived --json":
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
