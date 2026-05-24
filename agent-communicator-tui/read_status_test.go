package main

import (
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestApplyStatusEventsMarkOutboxRecordStages(t *testing.T) {
	withStateHome(t)
	rec := outboxRecord{ID: "m1", TargetAddress: "alpha", Body: "sent"}
	if err := appendOutbox(rec); err != nil {
		t.Fatalf("appendOutbox: %v", err)
	}
	m := model{ownName: "agent-communicator", rows: []agentRow{{Name: "alpha", TargetAddress: "alpha"}}, outbox: []outboxRecord{rec}}
	m.applyStatusEvents(tracker.WaitEventsResult{Events: []tracker.Event{{Type: "message_delivered", Sender: "agent-communicator", MessageID: "m1"}}})
	if !m.outbox[0].Delivered || m.outbox[0].Notified || m.outbox[0].Read {
		t.Fatalf("after delivered = %+v", m.outbox[0])
	}
	m.applyStatusEvents(tracker.WaitEventsResult{Events: []tracker.Event{{Type: "message_notified", Sender: "agent-communicator", MessageID: "m1"}}})
	if !m.outbox[0].Delivered || !m.outbox[0].Notified || m.outbox[0].Read {
		t.Fatalf("after notified = %+v", m.outbox[0])
	}
	m.applyStatusEvents(tracker.WaitEventsResult{Events: []tracker.Event{{Type: "message_read", Sender: "agent-communicator", MessageID: "m1"}}})
	if !m.outbox[0].Read {
		t.Fatal("outbox record not marked read")
	}
	reloaded, err := loadOutbox()
	if err != nil || len(reloaded) != 1 || !reloaded[0].Read || !reloaded[0].Notified || !reloaded[0].Delivered {
		t.Fatalf("reloaded outbox = %+v err=%v", reloaded, err)
	}
}

func TestSentReadMarkerShowsStages(t *testing.T) {
	if !strings.Contains(sentReadMarker(tracker.Message{Sender: "You", Delivered: true}), "✓") {
		t.Fatal("delivered marker missing")
	}
	if !strings.Contains(sentReadMarker(tracker.Message{Sender: "You", Notified: true}), "✓✓") {
		t.Fatal("notified marker missing")
	}
	if !strings.Contains(sentReadMarker(tracker.Message{Sender: "You", Read: true}), "✓✓") {
		t.Fatal("read marker missing")
	}
	if sentReadMarker(tracker.Message{Sender: "agent"}) != "" {
		t.Fatal("incoming message should not get sent read marker")
	}
}
