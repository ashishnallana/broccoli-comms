package main

import (
	"strings"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func conversationKey(row agentRow) string {
	if row.Scope == "remote" && row.AgentID != "" && row.TrackerID != "" {
		return "remote:" + row.TrackerID + ":" + row.AgentID
	}
	if row.Scope != "remote" && row.AgentID != "" {
		return "local:" + row.AgentID
	}
	return rowTarget(row)
}

func messageMatchesRow(msg tracker.Message, row agentRow) bool {
	if msg.SenderAgentID != "" && row.AgentID != "" {
		return messageMatchesRowByID(msg, row)
	}
	return senderMatchesRow(msg.Sender, row)
}

func messageMatchesRowByID(msg tracker.Message, row agentRow) bool {
	if msg.SenderAgentID == "" || row.AgentID == "" || msg.SenderAgentID != row.AgentID {
		return false
	}
	if row.Scope == "remote" {
		return row.TrackerID != "" && msg.SenderTrackerID != "" && msg.SenderTrackerID == row.TrackerID
	}
	// Local rows are identified by agent ID. If both sides carry tracker IDs,
	// reject an explicit mismatch so remote agents with duplicate IDs/names do not
	// bleed into local conversations.
	return row.TrackerID == "" || msg.SenderTrackerID == "" || row.TrackerID == msg.SenderTrackerID
}

func outboxRecordMatchesRow(rec outboxRecord, row agentRow) bool {
	if rec.TargetAgentID != "" && row.AgentID != "" {
		return outboxRecordMatchesRowByID(rec, row)
	}
	return rec.TargetAddress != "" && rec.TargetAddress == rowTarget(row)
}

func outboxRecordMatchesRowByID(rec outboxRecord, row agentRow) bool {
	if rec.TargetAgentID == "" || row.AgentID == "" || rec.TargetAgentID != row.AgentID {
		return false
	}
	if row.Scope == "remote" || rec.TargetTrackerID != "" || row.TrackerID != "" {
		return rec.TargetTrackerID != "" && row.TrackerID != "" && rec.TargetTrackerID == row.TrackerID
	}
	return true
}

func messageRowIDKeys(msg tracker.Message) []string {
	if msg.SenderAgentID == "" {
		return nil
	}
	if _, _, remote := parseRemoteSender(msg.Sender); remote {
		if msg.SenderTrackerID == "" {
			return nil
		}
		return []string{"remote:" + msg.SenderTrackerID + ":" + msg.SenderAgentID}
	}
	return []string{"local:" + msg.SenderAgentID}
}

func rowKeyMatchesSenderString(row agentRow, sender string) bool {
	sender = strings.TrimSpace(sender)
	return sender != "" && (senderMatchesRow(sender, row) || sender == row.Name || sender == rowTarget(row))
}
