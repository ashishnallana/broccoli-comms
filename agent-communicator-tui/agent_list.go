package main

import (
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"

	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var agentListProvider = loadAgentsFromCtlProvider

func broccoliAgentTrackerCommand(args ...string) *exec.Cmd {
	return broccoliAgentTrackerCommandContext(context.Background(), args...)
}

func broccoliAgentTrackerCommandContext(ctx context.Context, args ...string) *exec.Cmd {
	cli := config.GetString("", "executables", "agent_tracker_ctl")
	if cli == "" {
		cli = os.Getenv("BROCCOLI_COMMS_CLI")
	}
	if cli == "" {
		cli = "broccoli-comms"
	}
	trackerArgs := append([]string{"agent-tracker"}, args...)
	return exec.CommandContext(ctx, cli, trackerArgs...)
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

type ctlAgent struct {
	Name          string                  `json:"name"`
	Aliases       []string                `json:"aliases"`
	AgentID       string                  `json:"agent_id"`
	Scope         string                  `json:"scope"`
	Status        string                  `json:"status"`
	CWD           string                  `json:"cwd"`
	Hostname      string                  `json:"hostname"`
	TargetAddress string                  `json:"target_address"`
	TrackerID     string                  `json:"tracker_id"`
	RegistryName  string                  `json:"registry_name"`
	TmuxPane      string                  `json:"tmux_pane"`
	AgentCmd      string                  `json:"agent_cmd"`
	AgentType     string                  `json:"agent_type"`
	ModelType     string                  `json:"model_type"`
	Detection     tracker.DetectionStatus `json:"detection"`
}

func loadAgents(local localClient) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		rows, err := agentListProvider(ctx, local)
		return agentsLoaded{Rows: rows, Err: err}
	}
}

func loadAgentsFromCtlProvider(ctx context.Context, _ localClient) ([]agentRow, error) {
	return loadAgentsFromCtl(ctx)
}

func loadAgentsFromCtlCmd(timeout time.Duration) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), timeout)
		defer cancel()
		rows, err := loadAgentsFromCtl(ctx)
		return agentsLoaded{Rows: rows, Err: err}
	}
}

func loadAgentsFromRPC(ctx context.Context, local localClient) ([]agentRow, error) {
	if local == nil {
		return nil, nil
	}
	agents, err := local.List(ctx)
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

func loadAgentsFromCtl(ctx context.Context) ([]agentRow, error) {
	out, err := broccoliAgentTrackerCommandContext(ctx, "list").Output()
	if err != nil {
		return nil, fmt.Errorf("broccoli-comms agent-tracker list: %w", err)
	}
	var agents map[string]ctlAgent
	if err := json.Unmarshal(out, &agents); err != nil {
		return nil, fmt.Errorf("decode broccoli-comms agent-tracker list: %w", err)
	}
	rows := make([]agentRow, 0, len(agents))
	for key, agent := range agents {
		rows = append(rows, rowFromCtlAgent(key, agent))
	}
	sortRows(rows)
	return rows, nil
}

func rowFromCtlAgent(key string, agent ctlAgent) agentRow {
	return rowFromTrackerAgent(key, tracker.Agent{
		Name:          agent.Name,
		Aliases:       agent.Aliases,
		AgentID:       agent.AgentID,
		Scope:         agent.Scope,
		Status:        agent.Status,
		CWD:           agent.CWD,
		Hostname:      agent.Hostname,
		TargetAddress: agent.TargetAddress,
		TrackerID:     agent.TrackerID,
		RegistryName:  agent.RegistryName,
		TmuxPane:      agent.TmuxPane,
		AgentCmd:      agent.AgentCmd,
		AgentType:     agent.AgentType,
		ModelType:     agent.ModelType,
		Detection:     agent.Detection,
	})
}

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
			Name:          key,
			TargetAddress: target,
			AgentName:     key,
			Scope:         "local",
			Status:        agent.Status,
			CWD:           fallback(agent.CWD, "unknown"),
			Hostname:      agent.Hostname,
			TmuxPane:      agent.TmuxPane,
			AgentCmd:      agent.AgentCmd,
			AgentType:     agent.AgentType,
			AgentID:       agent.AgentID,
			TrackerID:     agent.TrackerID,
			RegistryName:  agent.RegistryName,
			ModelType:     agent.ModelType,
			Detection:     agent.Detection,
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
		Name:          remoteDisplayName(target, host, name),
		TargetAddress: target,
		Hostname:      host,
		AgentName:     name,
		Scope:         "remote",
		Status:        agent.Status,
		CWD:           fallback(agent.CWD, "unavailable"),
		TmuxPane:      agent.TmuxPane,
		AgentCmd:      agent.AgentCmd,
		AgentType:     agent.AgentType,
		AgentID:       agent.AgentID,
		TrackerID:     agent.TrackerID,
		RegistryName:  agent.RegistryName,
		ModelType:     agent.ModelType,
		Detection:     agent.Detection,
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
	return prefix + shortHost(host) + "/" + name
}
