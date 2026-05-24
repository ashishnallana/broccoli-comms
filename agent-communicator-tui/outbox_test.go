package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "agent-communicator-tests-*")
	if err != nil {
		panic(err)
	}
	os.Setenv("XDG_STATE_HOME", dir)
	code := m.Run()
	os.RemoveAll(dir)
	os.Exit(code)
}

func withStateHome(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("XDG_STATE_HOME", dir)
	return dir
}

func TestOutboxPathHonorsXDGStateHome(t *testing.T) {
	dir := withStateHome(t)
	want := filepath.Join(dir, "agent-communicator", "outbox.jsonl")
	if got := outboxPath(); got != want {
		t.Fatalf("outboxPath = %q, want %q", got, want)
	}
}

func TestAppendLoadOutboxSkipsBlankAndCorruptLines(t *testing.T) {
	withStateHome(t)
	rec := outboxRecord{ID: "id1", Timestamp: "2026-01-01T00:00:00Z", TargetAddress: "alpha", Body: "hello"}
	if err := appendOutbox(rec); err != nil {
		t.Fatalf("appendOutbox: %v", err)
	}
	path := outboxPath()
	file, _ := os.OpenFile(path, os.O_WRONLY|os.O_APPEND, 0o600)
	_, _ = file.WriteString("\nnot-json\n")
	file.Close()
	records, err := loadOutbox()
	if err != nil || len(records) != 1 || records[0].ID != "id1" {
		t.Fatalf("records=%+v err=%v", records, err)
	}
}

func TestSendPersistsOriginalBodyAndDeliversWithPS(t *testing.T) {
	withStateHome(t)
	local := &fakeLocal{}
	row := agentRow{Name: "tanma/agent", TargetAddress: "tanmayvijay.c.googlers.com/agent", Scope: "remote"}
	msg := sendCurrentMessage(local, "agent-communicator", row, "hello")().(messageSent)
	if msg.Err != nil {
		t.Fatalf("send err = %v", msg.Err)
	}
	if !strings.Contains(local.sentBody, markdownReplyInstruction) {
		t.Fatalf("delivered body missing PS: %q", local.sentBody)
	}
	if local.sentID == "" || local.sentID != msg.Record.ID {
		t.Fatalf("sent message_id = %q record=%q", local.sentID, msg.Record.ID)
	}
	records, _ := loadOutbox()
	if len(records) != 1 || records[0].Body != "hello" || strings.Contains(records[0].Body, markdownReplyInstruction) {
		t.Fatalf("records = %+v", records)
	}
	if records[0].TargetAddress != "tanmayvijay.c.googlers.com/agent" || records[0].TargetDisplay != "tanma/agent" {
		t.Fatalf("record target = %+v", records[0])
	}
}

func TestPersistedOutboxShownAfterRestartAndAdvanced(t *testing.T) {
	rec := outboxRecord{ID: "id1", Timestamp: "2026-01-01T00:01:00Z", Sender: "agent-communicator", TargetDisplay: "alpha", TargetAddress: "alpha", Body: "persisted"}
	m := model{ownName: "agent-communicator", rows: []agentRow{{Name: "alpha", TargetAddress: "alpha"}}, outbox: []outboxRecord{rec}}
	merged := m.mergeSentMessages(m.rows[0], []tracker.Message{{Sender: "alpha", Body: "in", Timestamp: "2026-01-01T00:00:00Z"}})
	if len(merged) != 2 || merged[1].Body != "persisted" || merged[1].Sender != "You" {
		t.Fatalf("simple merged = %+v", merged)
	}
	m.mode = advancedView
	all := m.mergeAllMessages(nil)
	if len(all) != 1 || all[0].Sender != "to alpha" {
		t.Fatalf("advanced merged = %+v", all)
	}
}

func TestOutboxMergeAvoidsDuplicateAfterSendReload(t *testing.T) {
	rec := outboxRecord{ID: "same", Timestamp: "2026-01-01T00:00:00Z", TargetAddress: "alpha", Body: "sent"}
	m := model{rows: []agentRow{{Name: "alpha", TargetAddress: "alpha"}}, outbox: []outboxRecord{rec}, sentMessages: map[string][]tracker.Message{"alpha": {outboxMessage(rec, false)}}}
	merged := m.mergeSentMessages(m.rows[0], nil)
	if len(merged) != 1 {
		t.Fatalf("merged = %+v", merged)
	}
}
