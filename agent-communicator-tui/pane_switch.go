package main

import (
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"

	"fmt"
	"os"
	"os/exec"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type paneSwitched struct{ Err error }

func privateTmuxSocket() string {
	return firstNonEmpty(config.GetString("", "paths", "tmux_socket"), os.Getenv("AGENT_TRACKER_TMUX_SOCKET"), os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET"))
}

func tmuxCommandArgs(args ...string) []string {
	cmdArgs := append([]string{}, args...)
	if socket := privateTmuxSocket(); socket != "" {
		cmdArgs = append([]string{"-S", socket}, cmdArgs...)
	}
	return cmdArgs
}

func tmuxCommandEnv(stripInherited bool) []string {
	if !stripInherited {
		return nil
	}
	env := os.Environ()
	filtered := env[:0]
	for _, entry := range env {
		if strings.HasPrefix(entry, "TMUX=") || strings.HasPrefix(entry, "TMUX_PANE=") {
			continue
		}
		filtered = append(filtered, entry)
	}
	return filtered
}

func newTmuxCommand(args ...string) *exec.Cmd {
	cmdArgs := tmuxCommandArgs(args...)
	cmd := exec.Command("tmux", cmdArgs...)
	if len(cmdArgs) >= 2 && cmdArgs[0] == "-S" {
		cmd.Env = tmuxCommandEnv(true)
	}
	return cmd
}

var runTmuxCommand = func(args ...string) error {
	return newTmuxCommand(args...).Run()
}

func switchToAgentPane(row agentRow) tea.Cmd {
	return func() tea.Msg {
		if row.Scope != "local" {
			return paneSwitched{Err: fmt.Errorf("cannot switch to remote agent %s", row.Name)}
		}
		if row.TmuxPane == "" {
			return paneSwitched{Err: fmt.Errorf("agent %s has no tmux pane", row.Name)}
		}
		return paneSwitched{Err: runTmuxCommand("switch-client", "-t", row.TmuxPane)}
	}
}

func messageIDExists(messages []tracker.Message, id string) bool {
	if id == "" {
		return false
	}
	for _, msg := range messages {
		if msg.MessageID == id {
			return true
		}
	}
	return false
}

func (m *model) applyStatusEvents(result tracker.WaitEventsResult) {
	changed := false
	for _, event := range result.Events {
		if event.Sender != m.ownName || event.MessageID == "" {
			continue
		}
		for i := range m.outbox {
			if m.outbox[i].ID != event.MessageID {
				continue
			}
			switch event.Type {
			case "message_delivered":
				if !m.outbox[i].Delivered {
					m.outbox[i].Delivered = true
					changed = true
				}
			case "message_notified":
				if !m.outbox[i].Notified {
					m.outbox[i].Delivered = true
					m.outbox[i].Notified = true
					changed = true
				}
			case "message_read":
				if !m.outbox[i].Read {
					m.outbox[i].Delivered = true
					m.outbox[i].Notified = true
					m.outbox[i].Read = true
					changed = true
				}
			}
		}
	}
	if changed {
		if err := writeOutbox(m.outbox); err != nil {
			m.err = err
		}
		m.refreshMergedMessages()
	}
}

func appendOrReplaceOutbox(records []outboxRecord, rec outboxRecord) []outboxRecord {
	for i, existing := range records {
		if existing.ID == rec.ID {
			records[i] = rec
			return records
		}
	}
	return append(records, rec)
}
