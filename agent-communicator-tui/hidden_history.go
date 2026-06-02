package main

import (
	"bufio"
	"encoding/json"
	"os"
	"strings"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func (m *model) applyInitialHiddenForNoHistory() {
	if m.autoHiddenApplied || len(m.rows) == 0 {
		return
	}
	if m.hiddenAgents == nil {
		m.hiddenAgents = map[string]bool{}
	}
	inbound := readInboxConversationKeys()
	changed := false
	for _, row := range m.rows {
		key := conversationKey(row)
		if key == "" || m.hiddenAgents[key] || m.rowHasOutbound(row) || inbound[rowHistoryKey(row)] {
			continue
		}
		if strings.HasPrefix(strings.ToLower(row.Name), "zv2") {
			continue // Never auto-hide zv2 agents!
		}
		m.hiddenAgents[key] = true
		changed = true
	}
	m.autoHiddenApplied = true
	if changed {
		selectedKey := conversationKey(m.currentRow())
		m.sortRowsByHidden(selectedKey)
		_ = saveHiddenAgents(m.hiddenAgents)
	}
}

func (m model) rowHasOutbound(row agentRow) bool {
	key := conversationKey(row)
	for _, rec := range m.outbox {
		if outboxRecordMatchesRow(rec, row) {
			return true
		}
	}
	return len(m.sentMessages[key]) > 0
}

func rowHistoryKey(row agentRow) string {
	if key := conversationKey(row); key != "" && key != rowTarget(row) {
		return key
	}
	if row.Scope == "remote" {
		return strings.TrimSpace(row.AgentName + "\x00" + row.Hostname)
	}
	return strings.TrimSpace(row.Name)
}

func readInboxConversationKeys() map[string]bool {
	keys := map[string]bool{}
	file, err := os.Open(communicatorInboxPath())
	if err != nil {
		return keys
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		var msg tracker.Message
		if json.Unmarshal(scanner.Bytes(), &msg) != nil {
			continue
		}
		for _, key := range messageRowIDKeys(msg) {
			keys[key] = true
		}
		sender := strings.TrimSpace(msg.Sender)
		if sender == "" {
			continue
		}
		if name, host, ok := parseRemoteSender(sender); ok {
			keys[name+"\x00"+host] = true
			continue
		}
		keys[sender] = true
	}
	return keys
}

func parseRemoteSender(sender string) (string, string, bool) {
	open := strings.LastIndex(sender, " (via ")
	if open < 0 || !strings.HasSuffix(sender, ")") {
		return "", "", false
	}
	return strings.TrimSpace(sender[:open]), strings.TrimSuffix(sender[open+6:], ")"), true
}
