package main

import (
	"fmt"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestSimpleDisplayLimitsLatestMessages(t *testing.T) {
	m := model{}
	for i := 0; i < simpleConversationLimit+10; i++ {
		m.messages = append(m.messages, tracker.Message{Sender: "a", Body: fmt.Sprintf("msg-%02d", i), Timestamp: fmt.Sprintf("2026-01-01T00:%02d:00Z", i)})
	}
	got := m.displayOrderedMessages()
	if len(got) != simpleConversationLimit {
		t.Fatalf("len=%d want %d", len(got), simpleConversationLimit)
	}
	if got[0].Body != "msg-59" || got[len(got)-1].Body != "msg-10" {
		t.Fatalf("did not retain latest messages: first=%s last=%s", got[0].Body, got[len(got)-1].Body)
	}
}

func TestAdvancedDisplayLimitsLatestMessages(t *testing.T) {
	m := model{mode: advancedView}
	for i := 0; i < advancedConversationLimit+10; i++ {
		m.allMessages = append(m.allMessages, tracker.Message{Sender: "a", Body: fmt.Sprintf("msg-%03d", i), Timestamp: fmt.Sprintf("2026-01-01T%02d:%02d:00Z", i/60, i%60)})
	}
	got := m.displayOrderedMessages()
	if len(got) != advancedConversationLimit {
		t.Fatalf("len=%d want %d", len(got), advancedConversationLimit)
	}
	if got[0].Body != "msg-209" || got[len(got)-1].Body != "msg-010" {
		t.Fatalf("did not retain latest messages: first=%s last=%s", got[0].Body, got[len(got)-1].Body)
	}
}
