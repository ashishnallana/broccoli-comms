package main

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type outboxRecord struct {
	ID              string `json:"id"`
	Timestamp       string `json:"timestamp"`
	Sender          string `json:"sender"`
	TargetDisplay   string `json:"target_display"`
	TargetAddress   string `json:"target_address"`
	TargetScope     string `json:"target_scope"`
	TargetAgentID   string `json:"target_agent_id,omitempty"`
	TargetTrackerID string `json:"target_tracker_id,omitempty"`
	Body            string `json:"body"`
	Delivered       bool   `json:"delivered,omitempty"`
	Notified        bool   `json:"notified,omitempty"`
	Read            bool   `json:"read,omitempty"`
}

type outboxLoaded struct {
	Records []outboxRecord
	Err     error
}

func outboxPath() string {
	base := os.Getenv("XDG_STATE_HOME")
	if base == "" {
		home, _ := os.UserHomeDir()
		base = filepath.Join(home, ".local", "state")
	}
	return filepath.Join(base, "agent-communicator", "outbox.jsonl")
}

func loadOutbox() ([]outboxRecord, error) {
	file, err := os.Open(outboxPath())
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var records []outboxRecord
	scanner := bufio.NewScanner(file)
	seen := map[string]int{}
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var rec outboxRecord
		if json.Unmarshal(line, &rec) == nil && rec.ID != "" {
			if idx, ok := seen[rec.ID]; ok {
				records[idx] = rec
				continue
			}
			seen[rec.ID] = len(records)
			records = append(records, rec)
		}
	}
	return records, scanner.Err()
}

func appendOutbox(rec outboxRecord) error {
	path := outboxPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return err
	}
	defer file.Close()
	encoded, err := json.Marshal(rec)
	if err != nil {
		return err
	}
	_, err = file.Write(append(encoded, '\n'))
	return err
}

func writeOutbox(records []outboxRecord) error {
	path := outboxPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return err
	}
	defer file.Close()
	for _, rec := range records {
		encoded, err := json.Marshal(rec)
		if err != nil {
			return err
		}
		if _, err := file.Write(append(encoded, '\n')); err != nil {
			return err
		}
	}
	return nil
}

func makeOutboxRecord(sender string, row agentRow, body string) outboxRecord {
	now := time.Now()
	return outboxRecord{
		ID:              "sent-" + now.Format("20060102150405.000000000"),
		Timestamp:       now.Format(time.RFC3339Nano),
		Sender:          fallback(sender, "agent-communicator"),
		TargetDisplay:   row.Name,
		TargetAddress:   rowTarget(row),
		TargetScope:     row.Scope,
		TargetAgentID:   row.AgentID,
		TargetTrackerID: row.TrackerID,
		Body:            body,
	}
}

func outboxMessage(rec outboxRecord, advanced bool) tracker.Message {
	sender := "You"
	if advanced {
		sender = "to " + fallback(rec.TargetDisplay, rec.TargetAddress)
	}
	return tracker.Message{Sender: sender, Timestamp: rec.Timestamp, Body: rec.Body, Delivered: rec.Delivered, Notified: rec.Notified, Read: rec.Read, MessageID: rec.ID}
}

func loadOutboxCmd() tea.Cmd {
	return func() tea.Msg {
		records, err := loadOutbox()
		return outboxLoaded{Records: records, Err: err}
	}
}
