package main

import (
	"context"
	"testing"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type saveLocalStub struct {
	fakeLocal
	targetTrackerID string
	eventType       string
	payload         any
	publishErr      error
}

func (s *saveLocalStub) PublishTrackerEvent(_ context.Context, targetTrackerID, eventType string, payload any) error {
	s.targetTrackerID = targetTrackerID
	s.eventType = eventType
	s.payload = payload
	return s.publishErr
}

func saveInput(value string) textinput.Model {
	input := textinput.New()
	input.SetValue(value)
	return input
}

func TestUpdateSaveFormCtrlSSubmitsRemoteSaveRequest(t *testing.T) {
	local := &saveLocalStub{}
	m := model{
		local:           local,
		rows:            []agentRow{{Name: "tvija/alpha-agent-1", Scope: "remote", TrackerID: "tracker-1", AgentID: "agent-1", AgentName: "alpha-agent-1"}},
		showingSaveForm: true,
		saveFormInputs: []textinput.Model{
			saveInput("alpha"),
			saveInput("desc"),
			saveInput("pi --profile foo"),
			saveInput("/repo"),
		},
	}

	updated, cmd := m.updateSaveForm(tea.KeyMsg{Type: tea.KeyCtrlS})
	m = updated
	if m.showingSaveForm {
		t.Fatal("save form stayed open")
	}
	if cmd == nil {
		t.Fatal("ctrl+s did not return save command")
	}
	msg := cmd().(agentSaved)
	if msg.Err != nil {
		t.Fatalf("save returned error: %v", msg.Err)
	}
	if local.targetTrackerID != "tracker-1" || local.eventType != "save_request" {
		t.Fatalf("publish = tracker=%q event=%q", local.targetTrackerID, local.eventType)
	}
	payload, ok := local.payload.(map[string]any)
	if !ok {
		t.Fatalf("payload type = %T", local.payload)
	}
	if payload["agent_to_save"] != "agent-1" || payload["agent_name"] != "alpha" || payload["command"] != "pi --profile foo" || payload["description"] != "desc" || payload["cwd"] != "/repo" {
		t.Fatalf("payload = %#v", payload)
	}
}

func TestSaveAgentCmdErrorsWhenRemoteTrackerIDMissing(t *testing.T) {
	msg := saveAgentCmd(&saveLocalStub{}, agentRow{Scope: "remote", AgentID: "agent-1", AgentName: "alpha"}, "alpha", "pi", "desc", "/repo")().(agentSaved)
	if msg.Err == nil || msg.Err.Error() != "remote tracker ID unavailable" {
		t.Fatalf("unexpected error = %v", msg.Err)
	}
}

func TestRowFromTrackerAgentPreservesTrackerID(t *testing.T) {
	row := rowFromTrackerAgent("host/alpha", tracker.Agent{Scope: "remote", TargetAddress: "host/alpha", TrackerID: "tracker-1"})
	if row.TrackerID != "tracker-1" {
		t.Fatalf("tracker id = %q", row.TrackerID)
	}
}
