package main

import (
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestMergeSentMessagesDedupesRepeatedOutboxRecords(t *testing.T) {
	row := agentRow{Name: "alpha", TargetAddress: "alpha"}
	rec := outboxRecord{ID: "m1", Timestamp: "2026-01-01T00:00:00Z", TargetAddress: "alpha", Body: "sent"}
	m := model{rows: []agentRow{row}, outbox: []outboxRecord{rec, rec}, sentMessages: map[string][]tracker.Message{"alpha": {outboxMessage(rec, false)}}}
	merged := m.mergeSentMessages(row, nil)
	if len(merged) != 1 {
		t.Fatalf("merged = %+v", merged)
	}
}

func TestMergeAllMessagesDedupesRepeatedMessageIDs(t *testing.T) {
	rec := outboxRecord{ID: "m1", Timestamp: "2026-01-01T00:00:00Z", TargetAddress: "alpha", TargetDisplay: "alpha", Body: "sent"}
	m := model{outbox: []outboxRecord{rec, rec}}
	merged := m.mergeAllMessages([]tracker.Message{{Sender: "alpha", Body: "reply", MessageID: "r1"}, {Sender: "alpha", Body: "reply", MessageID: "r1"}})
	if len(merged) != 2 {
		t.Fatalf("merged = %+v", merged)
	}
}

func TestLoadOutboxKeepsLatestRecordForDuplicateID(t *testing.T) {
	withStateHome(t)
	first := outboxRecord{ID: "m1", Timestamp: "t1", TargetAddress: "alpha", Body: "old"}
	latest := outboxRecord{ID: "m1", Timestamp: "t2", TargetAddress: "alpha", Body: "new", Read: true}
	if err := appendOutbox(first); err != nil {
		t.Fatal(err)
	}
	if err := appendOutbox(latest); err != nil {
		t.Fatal(err)
	}
	records, err := loadOutbox()
	if err != nil || len(records) != 1 || records[0].Body != "new" || !records[0].Read {
		t.Fatalf("records=%+v err=%v", records, err)
	}
}
