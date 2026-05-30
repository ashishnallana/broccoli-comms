package main

import (
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestAppendSystemEventsAndRenderAnnotationRows(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local", AgentID: "id-1"}}}
	m.appendSystemEvents(tracker.WaitEventsResult{Events: []tracker.Event{
		{Seq: 1, Type: "agent_status_changed", TargetAgentID: "id-1", TargetAgentName: "alpha", OldStatus: "idle", Status: "running"},
		{Seq: 2, Type: "unknown_event", TargetAgentName: "alpha"},
	}})
	if len(m.systemEvents) != 1 {
		t.Fatalf("systemEvents = %+v", m.systemEvents)
	}
	view := strings.Join(m.messageLinesForWidth(90), "\n")
	if !strings.Contains(view, "alpha status idle") || !strings.Contains(view, "╌") {
		t.Fatalf("system annotation missing:\n%s", view)
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
