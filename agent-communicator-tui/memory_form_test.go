package main

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestMemoryNewFormOpenCancelAndValidation(t *testing.T) {
	m := model{mode: memoryView, ownName: "broccoli-agent"}
	updated, cmd := m.updateMemoryManagement(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("n")})
	if cmd != nil || updated.memoryForm.Mode != memoryFormNew {
		t.Fatalf("new form mode=%v cmd=%v", updated.memoryForm.Mode, cmd)
	}
	if got := updated.memoryForm.Inputs[memoryFormAgent].Value(); got != "broccoli-agent" {
		t.Fatalf("agent default=%q", got)
	}
	updated, cmd = updated.updateMemoryForm(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil || updated.memoryForm.Err == nil || !strings.Contains(updated.memoryForm.Err.Error(), "title") {
		t.Fatalf("empty form should validate title, err=%v cmd=%v", updated.memoryForm.Err, cmd)
	}
	updated, cmd = updated.updateMemoryForm(tea.KeyMsg{Type: tea.KeyEsc})
	if cmd != nil || updated.memoryForm.Mode != memoryFormNone {
		t.Fatalf("esc should cancel form mode=%v cmd=%v", updated.memoryForm.Mode, cmd)
	}
}

func TestMemoryNewFormSubmitArgs(t *testing.T) {
	form := filledNewMemoryForm()
	got := memoryFormArgs(form)
	want := []string{"memory", "propose", "--type", "habit", "--title", "Run tests", "--body", "Always run go test", "--agent", "broccoli-agent", "--subject-agent", "broccoli-agent", "--source-task", "task-1", "--tag", "quality", "--tag", "tests", "--json"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("args=%#v want %#v", got, want)
	}
}

func TestMemoryFormCtrlTTrustedManualDoesNotSwitchTabs(t *testing.T) {
	m := model{mode: memoryView}
	m.openNewMemoryForm()
	updated, cmd := m.handleKeyMsg(tea.KeyMsg{Type: tea.KeyCtrlT})
	if cmd != nil {
		t.Fatalf("ctrl-t in memory form should not return tab switch command: %v", cmd)
	}
	if updated.mode != memoryView || updated.memoryForm.Mode != memoryFormNew || !updated.memoryForm.TrustedManual {
		t.Fatalf("ctrl-t should toggle trusted manual inside form, mode=%v form=%+v", updated.mode, updated.memoryForm)
	}
}

func TestMemoryFormHelpDoesNotAdvertiseInlineEditProposal(t *testing.T) {
	m := model{}
	m.openNewMemoryForm()
	view := m.memoryFormView(100, 30)
	if strings.Contains(view, "proposal edit") || strings.Contains(view, "propose-edit") {
		t.Fatalf("new-memory form should not advertise stale inline edit/propose-edit help:\n%s", view)
	}
}

func TestMemoryTabEditUsesEditorInsteadOfInlineForm(t *testing.T) {
	m := model{mode: memoryView, memoryItems: []memoryRecord{{MemoryID: "mem-1", Version: 4, Type: "fact", Title: "Endpoint", Body: "Old body"}}}
	updated, cmd := m.updateMemoryManagement(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("e")})
	if cmd == nil {
		t.Fatalf("edit key should launch editor command")
	}
	if updated.memoryForm.Mode != memoryFormNone {
		t.Fatalf("edit key should not open inline memory form: %+v", updated.memoryForm)
	}
}

func TestMemoryFormSubmitSuccessClosesAndRefreshes(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	calls := [][]string{}
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, args)
		if len(calls) == 1 {
			return json.Marshal(map[string]any{"ok": true})
		}
		return json.Marshal(map[string]any{"pending": []memoryRecord{{MemoryID: "mem-p"}}, "approved": []memoryRecord{}})
	}
	m := model{memoryForm: filledNewMemoryForm()}
	msg := submitMemoryFormCmd(m.memoryForm)().(memoryFormSubmitted)
	updatedModel, cmd := m.Update(msg)
	updated := updatedModel.(model)
	if msg.Err != nil || updated.memoryForm.Mode != memoryFormNone || !updated.memoryLoading || cmd == nil {
		t.Fatalf("success should close/loading/refresh msg=%+v updated=%+v cmd=%v", msg, updated.memoryForm, cmd)
	}
	_ = cmd()
	if len(calls) != 2 {
		t.Fatalf("expected submit+refresh calls, got %d", len(calls))
	}
}

func TestMemoryFormSubmitErrorPreservesInput(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		return []byte("boom"), errors.New("failed")
	}
	m := model{memoryForm: filledNewMemoryForm()}
	msg := submitMemoryFormCmd(m.memoryForm)().(memoryFormSubmitted)
	updatedModel, cmd := m.Update(msg)
	updated := updatedModel.(model)
	if cmd != nil || updated.memoryForm.Mode != memoryFormNew || updated.memoryForm.Inputs[memoryFormTitle].Value() != "Run tests" || updated.memoryErr == nil {
		t.Fatalf("error should preserve form/input and set error, form=%+v err=%v cmd=%v", updated.memoryForm, updated.memoryErr, cmd)
	}
}

func filledNewMemoryForm() memoryFormState {
	m := model{ownName: "broccoli-agent"}
	m.openNewMemoryForm()
	m.memoryForm.Inputs[memoryFormType].SetValue("habit")
	m.memoryForm.Inputs[memoryFormTitle].SetValue("Run tests")
	m.memoryForm.Inputs[memoryFormBody].SetValue("Always run go test")
	m.memoryForm.Inputs[memoryFormAgent].SetValue("broccoli-agent")
	m.memoryForm.Inputs[memoryFormSubjectAgent].SetValue("broccoli-agent")
	m.memoryForm.Inputs[memoryFormTags].SetValue("quality, tests")
	m.memoryForm.Inputs[memoryFormSourceTask].SetValue("task-1")
	return m.memoryForm
}
