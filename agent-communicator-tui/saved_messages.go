package main

import (
	"bufio"
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type savedMessageRecord struct {
	ID              string `json:"id"`
	SavedAt         string `json:"saved_at"`
	MessageID       string `json:"message_id,omitempty"`
	Sender          string `json:"sender"`
	ConversationKey string `json:"conversation_key"`
	AgentName       string `json:"agent_name"`
	Body            string `json:"body"`
	Timestamp       string `json:"timestamp"`
	ContentType     string `json:"content_type,omitempty"`
}

type savedMessagesLoaded struct {
	Records []savedMessageRecord
	Err     error
}

type savedMessagesSaved struct{ Err error }

func savedMessagesPath() string {
	base := os.Getenv("XDG_STATE_HOME")
	if base == "" {
		home, _ := os.UserHomeDir()
		base = filepath.Join(home, ".local", "state")
	}
	return filepath.Join(base, "agent-communicator", "saved_messages.jsonl")
}

func loadSavedMessages() ([]savedMessageRecord, error) {
	file, err := os.Open(savedMessagesPath())
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var records []savedMessageRecord
	seen := map[string]int{}
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		var rec savedMessageRecord
		if json.Unmarshal(scanner.Bytes(), &rec) != nil || rec.ID == "" {
			continue
		}
		if idx, ok := seen[rec.ID]; ok {
			records[idx] = rec
			continue
		}
		seen[rec.ID] = len(records)
		records = append(records, rec)
	}
	return records, scanner.Err()
}

func writeSavedMessages(records []savedMessageRecord) error {
	path := savedMessagesPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return err
	}
	defer file.Close()
	for _, rec := range records {
		data, err := json.Marshal(rec)
		if err != nil {
			return err
		}
		if _, err := file.Write(append(data, '\n')); err != nil {
			return err
		}
	}
	return nil
}

func loadSavedMessagesCmd() tea.Cmd {
	return func() tea.Msg {
		records, err := loadSavedMessages()
		return savedMessagesLoaded{Records: records, Err: err}
	}
}

func saveSavedMessagesCmd(records []savedMessageRecord) tea.Cmd {
	copyRecords := append([]savedMessageRecord(nil), records...)
	return func() tea.Msg { return savedMessagesSaved{Err: writeSavedMessages(copyRecords)} }
}

func savedRecordID(msg tracker.Message) string {
	if msg.MessageID != "" {
		return "message:" + msg.MessageID
	}
	h := sha1.Sum([]byte(msg.Sender + "\x00" + msg.Timestamp + "\x00" + msg.Body))
	return "hash:" + hex.EncodeToString(h[:])
}

func savedAgentName(msg tracker.Message) string {
	if isSentMessage(msg) {
		return "You"
	}
	sender := strings.TrimSpace(msg.Sender)
	if strings.Contains(sender, "→") {
		parts := strings.Split(sender, "→")
		sender = strings.TrimSpace(parts[0])
	}
	return fallback(sender, "unknown")
}

func makeSavedRecord(msg tracker.Message) savedMessageRecord {
	agent := savedAgentName(msg)
	return savedMessageRecord{
		ID:              savedRecordID(msg),
		SavedAt:         time.Now().Format(time.RFC3339Nano),
		MessageID:       msg.MessageID,
		Sender:          msg.Sender,
		ConversationKey: agent,
		AgentName:       agent,
		Body:            msg.Body,
		Timestamp:       msg.Timestamp,
		ContentType:     msg.ContentType,
	}
}

func (m model) savedRows() []agentRow {
	counts := map[string]int{}
	for _, rec := range m.savedMessages {
		counts[fallback(rec.AgentName, rec.ConversationKey)]++
	}
	names := make([]string, 0, len(counts))
	for name := range counts {
		names = append(names, name)
	}
	sort.Slice(names, func(i, j int) bool {
		if names[i] == "You" {
			return true
		}
		if names[j] == "You" {
			return false
		}
		return names[i] < names[j]
	})
	rows := make([]agentRow, 0, len(names))
	for _, name := range names {
		rows = append(rows, agentRow{Name: name, Scope: "saved", TargetAddress: name})
	}
	return rows
}

func (m model) savedDisplayMessages() []tracker.Message {
	rows := m.savedRows()
	if len(rows) == 0 || m.savedSelected >= len(rows) {
		return nil
	}
	name := rows[m.savedSelected].Name
	var messages []tracker.Message
	for _, rec := range m.savedMessages {
		if fallback(rec.AgentName, rec.ConversationKey) != name {
			continue
		}
		messages = append(messages, tracker.Message{Sender: rec.Sender, Timestamp: rec.Timestamp, Body: rec.Body, ContentType: rec.ContentType, MessageID: rec.MessageID})
	}
	return uniqueMessagesByID(sortMessagesByTimestamp(messages))
}

func (m *model) clampSavedSelected() {
	rows := m.savedRows()
	if m.savedSelected >= len(rows) {
		m.savedSelected = max(0, len(rows)-1)
	}
}

func (m *model) selectSavedRow(delta int) {
	rows := m.savedRows()
	if len(rows) == 0 {
		m.savedSelected = 0
		return
	}
	m.savedSelected = (m.savedSelected + delta + len(rows)) % len(rows)
}

func (m model) isSavedMessage(msg tracker.Message) bool {
	id := savedRecordID(msg)
	for _, rec := range m.savedMessages {
		if rec.ID == id {
			return true
		}
	}
	return false
}

func (m *model) toggleSaveSelectedMessage() tea.Cmd {
	messages := m.displayOrderedMessages()
	if len(messages) == 0 || m.messageSelected >= len(messages) {
		return nil
	}
	rec := makeSavedRecord(messages[m.messageSelected])
	for i, existing := range m.savedMessages {
		if existing.ID == rec.ID {
			m.savedMessages = append(m.savedMessages[:i], m.savedMessages[i+1:]...)
			m.clampSavedSelected()
			return saveSavedMessagesCmd(m.savedMessages)
		}
	}
	m.savedMessages = append(m.savedMessages, rec)
	return saveSavedMessagesCmd(m.savedMessages)
}
