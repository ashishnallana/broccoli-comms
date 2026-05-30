package main

import (
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestMessageRenderCacheKeyIgnoresComposer(t *testing.T) {
	messages := []tracker.Message{{Sender: "alice", Body: "**hello**", Timestamp: "2026-01-01T00:00:00Z", MessageID: "1"}}
	m1 := model{width: 80, messageSelected: 0, composer: []rune("a")}
	m2 := m1
	m2.composer = []rune("abcd")
	if k1, k2 := messageRenderCacheKey(m1, messages, nil, 80), messageRenderCacheKey(m2, messages, nil, 80); k1 != k2 {
		t.Fatalf("cache key changed with composer: %s != %s", k1, k2)
	}
}

func TestMessageRenderCacheKeyChangesForSelectionBodyAndEvents(t *testing.T) {
	messages := []tracker.Message{{Sender: "alice", Body: "hello", MessageID: "1"}}
	m := model{}
	base := messageRenderCacheKey(m, messages, nil, 80)
	m.messageSelected = 1
	if got := messageRenderCacheKey(m, messages, nil, 80); got == base {
		t.Fatal("cache key did not change with selected message")
	}
	m.messageSelected = 0
	messages[0].Body = "changed"
	if got := messageRenderCacheKey(m, messages, nil, 80); got == base {
		t.Fatal("cache key did not change with message body")
	}
	messages[0].Body = "hello"
	if got := messageRenderCacheKey(m, messages, []tracker.Event{{Seq: 1, Type: "agent_registered"}}, 80); got == base {
		t.Fatal("cache key did not change with system event")
	}
}

func TestCachedMessageLinesRoundTrip(t *testing.T) {
	storeMessageLines("test-key", []string{"a", "b"})
	lines, ok := cachedMessageLines("test-key")
	if !ok || len(lines) != 2 || lines[0] != "a" || lines[1] != "b" {
		t.Fatalf("lines=%v ok=%v", lines, ok)
	}
	lines[0] = "mutated"
	again, _ := cachedMessageLines("test-key")
	if again[0] != "a" {
		t.Fatalf("cache was mutated: %v", again)
	}
}
