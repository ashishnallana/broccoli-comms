package main

import (
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestNormalMessagePaneStoresButDoesNotRenderSystemAnnotations(t *testing.T) {
	m := model{
		rows:     []agentRow{{Name: "alpha", Scope: "local", AgentID: "id-1"}},
		messages: []tracker.Message{{Sender: "alpha", Body: "real user message"}},
	}
	m.appendSystemEvents(tracker.WaitEventsResult{Events: []tracker.Event{
		{Seq: 1, Type: "agent_registered", TargetAgentID: "id-1", TargetAgentName: "alpha"},
		{Seq: 2, Type: "agent_unregistered", TargetAgentID: "id-1", TargetAgentName: "alpha"},
		{Seq: 3, Type: "agent_status_changed", TargetAgentID: "id-1", TargetAgentName: "alpha", OldStatus: "idle", Status: "ready"},
		{Seq: 4, Type: "message_delivered", TargetAgentID: "id-1", TargetAgentName: "alpha"},
		{Seq: 5, Type: "message_read", TargetAgentID: "id-1", TargetAgentName: "alpha"},
		{Seq: 6, Type: "remote_agent_event", TargetAgentID: "id-1", TargetAgentName: "alpha", Message: "alpha notified lifecycle"},
		{Seq: 7, Type: "unknown_event", TargetAgentName: "alpha"},
	}})
	if len(m.systemEvents) != 6 {
		t.Fatalf("systemEvents = %+v", m.systemEvents)
	}
	view := strings.Join(m.messageLinesForWidth(90), "\n")
	if !strings.Contains(view, "real user message") {
		t.Fatalf("real message missing:\n%s", view)
	}
	for _, unwanted := range []string{"alpha joined", "alpha left", "alpha status idle", "message delivered to alpha", "message read by alpha", "alpha notified lifecycle", "╌"} {
		if strings.Contains(view, unwanted) {
			t.Fatalf("normal message pane rendered annotation %q:\n%s", unwanted, view)
		}
	}
}

func TestAdvancedSystemEventsIncludeRemoteAgentEvents(t *testing.T) {
	m := model{mode: advancedView, systemEvents: []tracker.Event{{Seq: 1, Type: "remote_agent_event", TargetAgentName: "remote", Message: "remote activity"}}}
	view := strings.Join(m.messageLinesForWidth(90), "\n")
	if !strings.Contains(view, "remote activity") {
		t.Fatalf("remote system event missing:\n%s", view)
	}
}

func TestRuntimeStatusLineShowsHealthActiveAgentAndClock(t *testing.T) {
	connected := false
	m := model{
		rows:     []agentRow{{Name: "alpha", Scope: "local", Status: "idle", ModelType: "pi", Hostname: "workstation"}},
		health:   tracker.TrackerInfo{Status: "degraded", AgentCount: 4, OnlineAgentCount: 2, RegistryConnected: &connected, RemoteTrackerCount: 3, OnlineRemoteTrackerCount: 1},
		width:    120,
		height:   30,
		selected: 0,
	}
	status := m.runtimeStatusLine()
	for _, want := range []string{"rpc degraded", "active alpha Pi @ works", "online 2/4", "registry offline", "trackers 1/3"} {
		if !strings.Contains(status, want) {
			t.Fatalf("status missing %q: %s", want, status)
		}
	}
}
