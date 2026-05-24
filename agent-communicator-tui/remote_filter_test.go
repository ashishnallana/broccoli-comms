package main

import (
	"context"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestFilterOwnAgentExcludesCommunicator(t *testing.T) {
	rows := filterOwnAgent([]agentRow{{Name: "agent-communicator"}, {Name: "peer"}}, "agent-communicator")
	if len(rows) != 1 || rows[0].Name != "peer" {
		t.Fatalf("rows = %+v", rows)
	}
}

func TestLoadAgentsUsesTrackerRPCRows(t *testing.T) {
	old := agentListProvider
	agentListProvider = func(context.Context, localClient) ([]agentRow, error) {
		return []agentRow{{Name: "coding-agent", Scope: "local", TargetAddress: "coding-agent"}, {Name: "tanma/remote-agent", Scope: "remote", TargetAddress: "tanmayvijay.c.googlers.com/remote-agent"}}, nil
	}
	t.Cleanup(func() { agentListProvider = old })
	loaded := loadAgents(&fakeLocal{})().(agentsLoaded)
	if loaded.Err != nil || len(loaded.Rows) != 2 {
		t.Fatalf("loaded = %+v", loaded)
	}
	if loaded.Rows[1].TargetAddress != "tanmayvijay.c.googlers.com/remote-agent" {
		t.Fatalf("remote row target wrong: %+v", loaded.Rows)
	}
}

func TestRowFromTrackerAgentShortensRemoteDisplayAndKeepsTarget(t *testing.T) {
	row := rowFromTrackerAgent("local:tanmayvijay.c.googlers.com/remote-agent", tracker.Agent{Scope: "remote", Hostname: "tanmayvijay.c.googlers.com", TargetAddress: "local:tanmayvijay.c.googlers.com/remote-agent"})
	if row.Name != "local:tanma/remote-agent" || row.TargetAddress != "local:tanmayvijay.c.googlers.com/remote-agent" {
		t.Fatalf("row = %+v", row)
	}
}
