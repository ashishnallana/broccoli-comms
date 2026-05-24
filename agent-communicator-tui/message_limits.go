package main

import "github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"

const (
	simpleConversationLimit   = 50
	advancedConversationLimit = 200
	simpleInboxFetchLimit     = simpleConversationLimit * 2
	advancedInboxFetchLimit   = advancedConversationLimit
)

func limitLatestMessages(messages []tracker.Message, limit int) []tracker.Message {
	if limit <= 0 || len(messages) <= limit {
		return messages
	}
	return messages[:limit]
}
