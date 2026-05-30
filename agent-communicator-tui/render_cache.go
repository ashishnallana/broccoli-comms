package main

import (
	"fmt"
	"hash/fnv"
	"sync"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var messageRenderCache = struct {
	sync.Mutex
	key   string
	lines []string
}{}

func messageRenderCacheKey(m model, messages []tracker.Message, events []tracker.Event, width int) string {
	h := fnv.New64a()
	_, _ = fmt.Fprintf(h, "mode=%d;width=%d;selected=%d;count=%d;events=%d;", m.mode, width, m.messageSelected, len(messages), len(events))
	for _, msg := range messages {
		_, _ = fmt.Fprintf(h, "id=%s;ts=%s;sender=%s;ct=%s;read=%t;del=%t;not=%t;body=%s;",
			msg.MessageID, msg.Timestamp, msg.Sender, msg.ContentType, msg.Read, msg.Delivered, msg.Notified, msg.Body)
	}
	for _, event := range events {
		_, _ = fmt.Fprintf(h, "seq=%d;type=%s;target=%s;sender=%s;status=%s;old=%s;message=%s;",
			event.Seq, event.Type, event.TargetAgentName, event.Sender, event.Status, event.OldStatus, event.Message)
	}
	return fmt.Sprintf("%x", h.Sum64())
}

func cachedMessageLines(key string) ([]string, bool) {
	messageRenderCache.Lock()
	defer messageRenderCache.Unlock()
	if messageRenderCache.key != key || messageRenderCache.lines == nil {
		return nil, false
	}
	return append([]string(nil), messageRenderCache.lines...), true
}

func storeMessageLines(key string, lines []string) {
	messageRenderCache.Lock()
	defer messageRenderCache.Unlock()
	messageRenderCache.key = key
	messageRenderCache.lines = append([]string(nil), lines...)
}
