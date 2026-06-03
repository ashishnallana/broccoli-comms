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

func TestLoadAgentsProviderReturnsRows(t *testing.T) {
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

func TestLoadAgentsFromRPCIncludesRemoteAndCallerIdentity(t *testing.T) {
	local := &fakeLocal{agents: map[string]tracker.Agent{
		"coding-agent": {Status: "idle", Scope: "local", AgentID: "agent-id"},
		"local:remote-host.example.com/remote-agent": {Scope: "remote", Hostname: "remote-host.example.com", TargetAddress: "local:remote-host.example.com/remote-agent", TrackerID: "tracker-1", RegistryName: "local", AgentID: "remote-id", ModelType: "gemini"},
	}}
	t.Setenv("AGENT_ID", "caller-id")
	t.Setenv("AGENT_NAME", "caller-name")
	rows, err := loadAgentsFromRPC(context.Background(), local)
	if err != nil {
		t.Fatalf("loadAgentsFromRPC: %v", err)
	}
	if !local.listOptions.IncludeRemote || local.listOptions.AgentID != "caller-id" || local.listOptions.AgentName != "caller-name" {
		t.Fatalf("list options = %+v", local.listOptions)
	}
	if len(rows) != 2 || rows[1].Scope != "remote" || rows[1].TrackerID != "tracker-1" || rows[1].RegistryName != "local" || rows[1].AgentID != "remote-id" || rows[1].ModelType != "gemini" {
		t.Fatalf("rows = %+v", rows)
	}
}

func TestRowFromTrackerAgentShortensRemoteDisplayAndKeepsTarget(t *testing.T) {
	row := rowFromTrackerAgent("local:tanmayvijay.c.googlers.com/remote-agent", tracker.Agent{Scope: "remote", Hostname: "tanmayvijay.c.googlers.com", TargetAddress: "local:tanmayvijay.c.googlers.com/remote-agent"})
	if row.Name != "local:tanma/remote-agent" || row.TargetAddress != "local:tanmayvijay.c.googlers.com/remote-agent" {
		t.Fatalf("row = %+v", row)
	}
}
