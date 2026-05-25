package main

import (
	"encoding/json"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestMessageUnmarshalIncludesSenderIDs(t *testing.T) {
	var msg tracker.Message
	payload := []byte(`{"sender":"old-name","sender_agent_id":"agent-1","sender_tracker_id":"tracker-1","message":"hello"}`)
	if err := json.Unmarshal(payload, &msg); err != nil {
		t.Fatalf("unmarshal message: %v", err)
	}
	if msg.SenderAgentID != "agent-1" || msg.SenderTrackerID != "tracker-1" {
		t.Fatalf("sender ids not decoded: %+v", msg)
	}
}

func TestConversationKeyUsesStableIDsWithLegacyFallback(t *testing.T) {
	if got := conversationKey(agentRow{Name: "renamed", AgentID: "agent-1", Scope: "local"}); got != "local:agent-1" {
		t.Fatalf("local key = %q", got)
	}
	remote := agentRow{Name: "host/agent", Scope: "remote", AgentID: "agent-1", TrackerID: "tracker-1", TargetAddress: "host/agent"}
	if got := conversationKey(remote); got != "remote:tracker-1:agent-1" {
		t.Fatalf("remote key = %q", got)
	}
	if got := conversationKey(agentRow{Name: "legacy", TargetAddress: "legacy"}); got != "legacy" {
		t.Fatalf("legacy key = %q", got)
	}
}

func TestFilterConversationUsesSenderIDsAcrossRename(t *testing.T) {
	row := agentRow{Name: "new-name", Scope: "local", AgentID: "agent-1", TargetAddress: "new-name"}
	messages := []tracker.Message{
		{Sender: "old-name", SenderAgentID: "agent-1", Body: "kept by id"},
		{Sender: "new-name", SenderAgentID: "other-agent", Body: "same display wrong id"},
		{Sender: "new-name", Body: "legacy fallback"},
	}
	filtered := filterConversation(messages, row)
	if len(filtered) != 2 || filtered[0].Body != "kept by id" || filtered[1].Body != "legacy fallback" {
		t.Fatalf("filtered = %+v", filtered)
	}
}

func TestRemoteDuplicateNamesSeparatedByTrackerID(t *testing.T) {
	row1 := agentRow{Name: "r1:host/agent", Scope: "remote", Hostname: "host", AgentName: "agent", AgentID: "agent-1", TrackerID: "tracker-1", TargetAddress: "r1:host/agent"}
	row2 := agentRow{Name: "r2:host/agent", Scope: "remote", Hostname: "host", AgentName: "agent", AgentID: "agent-2", TrackerID: "tracker-2", TargetAddress: "r2:host/agent"}
	messages := []tracker.Message{
		{Sender: "agent (via host)", SenderAgentID: "agent-1", SenderTrackerID: "tracker-1", Body: "for row1"},
		{Sender: "agent (via host)", SenderAgentID: "agent-2", SenderTrackerID: "tracker-2", Body: "for row2"},
	}
	got1 := filterConversation(messages, row1)
	got2 := filterConversation(messages, row2)
	if len(got1) != 1 || got1[0].Body != "for row1" {
		t.Fatalf("row1 filtered = %+v", got1)
	}
	if len(got2) != 1 || got2[0].Body != "for row2" {
		t.Fatalf("row2 filtered = %+v", got2)
	}
}

func TestOutboxTargetIDsSurviveRename(t *testing.T) {
	rec := outboxRecord{ID: "sent-1", TargetAddress: "old-name", TargetAgentID: "agent-1", Body: "persisted"}
	row := agentRow{Name: "new-name", TargetAddress: "new-name", AgentID: "agent-1", Scope: "local"}
	m := model{rows: []agentRow{row}, outbox: []outboxRecord{rec}}
	merged := m.mergeSentMessages(row, nil)
	if len(merged) != 1 || merged[0].Body != "persisted" {
		t.Fatalf("merged = %+v", merged)
	}
}

func TestOutboxTargetIDsSeparateDuplicateRemoteTargets(t *testing.T) {
	row1 := agentRow{Name: "r1:host/agent", Scope: "remote", AgentID: "agent-1", TrackerID: "tracker-1", TargetAddress: "host/agent"}
	row2 := agentRow{Name: "r2:host/agent", Scope: "remote", AgentID: "agent-2", TrackerID: "tracker-2", TargetAddress: "host/agent"}
	rec := outboxRecord{ID: "sent-1", TargetAddress: "host/agent", TargetAgentID: "agent-1", TargetTrackerID: "tracker-1", Body: "for row1"}
	m := model{outbox: []outboxRecord{rec}}
	if got := m.mergeSentMessages(row1, nil); len(got) != 1 || got[0].Body != "for row1" {
		t.Fatalf("row1 merged = %+v", got)
	}
	if got := m.mergeSentMessages(row2, nil); len(got) != 0 {
		t.Fatalf("row2 merged = %+v", got)
	}
}

func TestMakeOutboxRecordPersistsTargetIDs(t *testing.T) {
	row := agentRow{Name: "host/agent", Scope: "remote", TargetAddress: "host/agent", AgentID: "agent-1", TrackerID: "tracker-1"}
	rec := makeOutboxRecord("agent-communicator", row, "hello")
	if rec.TargetAgentID != "agent-1" || rec.TargetTrackerID != "tracker-1" {
		t.Fatalf("outbox target ids = %+v", rec)
	}
}
