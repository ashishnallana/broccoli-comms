package main

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var agentListProvider = loadAgentsFromBroccoliComms

func broccoliAgentTrackerCommand(args ...string) *exec.Cmd {
	return broccoliAgentTrackerCommandContext(context.Background(), args...)
}

func broccoliAgentTrackerCommandContext(ctx context.Context, args ...string) *exec.Cmd {
	cli, wrapperStyle := broccoliAgentTrackerCLI()
	cmdArgs := append([]string{}, args...)
	if wrapperStyle {
		cmdArgs = append([]string{"agent-tracker"}, args...)
	}
	return exec.CommandContext(ctx, cli, cmdArgs...)
}

func broccoliAgentTrackerCLI() (string, bool) {
	if cli := os.Getenv("BROCCOLI_COMMS_CLI"); cli != "" {
		return cli, true
	}
	return "broccoli-comms", true
}

func loadHealth(local localClient) tea.Cmd {
	return func() tea.Msg {
		if local == nil {
			return healthLoaded{}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		info, err := local.TrackerInfo(ctx)
		return healthLoaded{Info: info, Err: err}
	}
}

func loadAgents(local localClient) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		rows, err := agentListProvider(ctx, local)
		return agentsLoaded{Rows: rows, Err: err}
	}
}

func loadAgentsFromBroccoliComms(ctx context.Context, local localClient) ([]agentRow, error) {
	cmd := broccoliCommsCommandContext(ctx, "agent", "list", "--include-remote", "--json")
	out, err := cmd.CombinedOutput()
	if err == nil {
		var payload broccoliAgentListPayload
		if err := json.Unmarshal(out, &payload); err == nil {
			rows := make([]agentRow, 0, len(payload.Agents))
			for key, row := range payload.Agents {
				rows = append(rows, rowFromBroccoliAgent(key, row))
			}
			sortRows(rows)
			return rows, nil
		}
	}
	return loadAgentsFromRPC(ctx, local)
}

func loadAgentsFromRPC(ctx context.Context, local localClient) ([]agentRow, error) {
	if local == nil {
		return nil, nil
	}
	agents, err := local.ListWithOptions(ctx, tracker.ListOptions{
		IncludeRemote: true,
		AgentID:       os.Getenv("AGENT_ID"),
		AgentName:     os.Getenv("AGENT_NAME"),
	})
	if err != nil {
		return nil, err
	}
	rows := make([]agentRow, 0, len(agents))
	for key, agent := range agents {
		rows = append(rows, rowFromTrackerAgent(key, agent))
	}
	sortRows(rows)
	return rows, nil
}

func rowFromBroccoliAgent(key string, agent broccoliAgentListRow) agentRow {
	scope := "local"
	if agent.Remote || agent.ScopeKind == "remote" {
		scope = "remote"
	}
	name := fallback(agent.Name, key)
	if scope == "remote" {
		host, remoteName := splitRemoteTarget(fallback(agent.TargetAddress, key))
		if agent.Hostname != "" {
			host = agent.Hostname
		}
		if remoteName == "" {
			remoteName = name
		}
		name = remoteDisplayName(fallback(agent.TargetAddress, key), host, remoteName)
		return agentRow{Name: name, TargetAddress: fallback(agent.TargetAddress, key), AgentName: remoteName, Scope: scope, Status: agent.Status, CWD: fallback(agent.CWD, "unavailable"), Hostname: host, TrackerID: agent.TrackerID, RegistryName: agent.RegistryName, Configured: agentBoolPtr(agent.IsConfigured), Running: agentBoolPtr(agent.Running), Launchable: agentBoolPtr(agent.Launchable), CurrentTask: agent.CurrentTask, CurrentTaskID: agent.CurrentTaskID, CurrentTaskStatus: agent.CurrentTaskStatus, CurrentTaskNextStep: agent.CurrentTaskNextStep}
	}
	return agentRow{Name: name, TargetAddress: fallback(agent.TargetAddress, key), AgentName: name, Scope: scope, Status: agent.Status, CWD: fallback(agent.CWD, "unknown"), Hostname: agent.Hostname, Configured: agentBoolPtr(agent.IsConfigured), Running: agentBoolPtr(agent.Running), Launchable: agentBoolPtr(agent.Launchable), CurrentTask: agent.CurrentTask, CurrentTaskID: agent.CurrentTaskID, CurrentTaskStatus: agent.CurrentTaskStatus, CurrentTaskNextStep: agent.CurrentTaskNextStep}
}

func agentBoolPtr(v bool) *bool { return &v }

func sortRows(rows []agentRow) {
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].Scope != rows[j].Scope {
			return rows[i].Scope < rows[j].Scope
		}
		return rows[i].Name < rows[j].Name
	})
}

func rowFromTrackerAgent(key string, agent tracker.Agent) agentRow {
	scope := fallback(agent.Scope, "local")
	target := fallback(agent.TargetAddress, key)
	if scope != "remote" {
		return agentRow{
			Name:                key,
			TargetAddress:       target,
			AgentName:           key,
			Scope:               "local",
			Status:              agent.Status,
			CWD:                 fallback(agent.CWD, "unknown"),
			Hostname:            agent.Hostname,
			TmuxPane:            agent.TmuxPane,
			AgentCmd:            agent.AgentCmd,
			AgentType:           agent.AgentType,
			AgentID:             agent.AgentID,
			TrackerID:           agent.TrackerID,
			RegistryName:        agent.RegistryName,
			ModelType:           agent.ModelType,
			CurrentTask:         agent.CurrentTask,
			CurrentTaskID:       agent.CurrentTaskID,
			CurrentTaskStatus:   agent.CurrentTaskStatus,
			CurrentTaskNextStep: agent.CurrentTaskNextStep,
			Detection:           agent.Detection,
		}
	}
	host, name := splitRemoteTarget(target)
	if agent.Hostname != "" {
		host = agent.Hostname
	}
	if name == "" {
		name = fallback(agent.Name, key)
	}
	return agentRow{
		Name:                remoteDisplayName(target, host, name),
		TargetAddress:       target,
		Hostname:            host,
		AgentName:           name,
		Scope:               "remote",
		Status:              agent.Status,
		CWD:                 fallback(agent.CWD, "unavailable"),
		TmuxPane:            agent.TmuxPane,
		AgentCmd:            agent.AgentCmd,
		AgentType:           agent.AgentType,
		AgentID:             agent.AgentID,
		TrackerID:           agent.TrackerID,
		RegistryName:        agent.RegistryName,
		ModelType:           agent.ModelType,
		CurrentTask:         agent.CurrentTask,
		CurrentTaskID:       agent.CurrentTaskID,
		CurrentTaskStatus:   agent.CurrentTaskStatus,
		CurrentTaskNextStep: agent.CurrentTaskNextStep,
		Detection:           agent.Detection,
	}
}

func splitRemoteTarget(target string) (string, string) {
	if strings.Contains(target, ":") {
		target = strings.SplitN(target, ":", 2)[1]
	}
	parts := strings.SplitN(target, "/", 2)
	if len(parts) != 2 {
		return "", target
	}
	return parts[0], parts[1]
}

func remoteDisplayName(target, host, name string) string {
	prefix := ""
	if strings.Contains(target, ":") {
		prefix = strings.SplitN(target, ":", 2)[0] + ":"
	}
	return prefix + host + "/" + name
}
