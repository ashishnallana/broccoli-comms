package main

import (
	"errors"
	"reflect"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestSuccessfulSendAppendsOutboundMessage(t *testing.T) {
	local := &fakeLocal{}
	m := model{width: 80, height: 20, rows: []agentRow{{Name: "alpha", Scope: "local"}}, local: local}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("hello")})
	m = updated.(model)
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if len(m.sentMessages["alpha"]) != 1 || m.sentMessages["alpha"][0].Body != "hello" {
		t.Fatalf("optimistic sent messages = %+v", m.sentMessages)
	}
	updated, _ = m.Update(cmd())
	m = updated.(model)

	if len(m.sentMessages["alpha"]) != 1 || m.sentMessages["alpha"][0].Body != "hello" {
		t.Fatalf("sent messages = %+v", m.sentMessages)
	}
	if len(m.messages) != 1 || m.messages[0].Sender != "You" || m.messages[0].Body != "hello" {
		t.Fatalf("display messages = %+v", m.messages)
	}
	if local.sentBody != "hello\n\n(PS: Reply in markdown format.)" {
		t.Fatalf("delivered body = %q", local.sentBody)
	}
}

func TestFailedSendRemovesOptimisticMessage(t *testing.T) {
	local := &fakeLocal{sendErr: errors.New("boom")}
	m := model{width: 80, height: 20, rows: []agentRow{{Name: "alpha", Scope: "local"}}, local: local}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("hello")})
	m = updated.(model)
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if len(m.sentMessages["alpha"]) != 1 {
		t.Fatal("optimistic message missing before send completes")
	}
	updated, _ = m.Update(cmd())
	m = updated.(model)
	if len(m.sentMessages["alpha"]) != 0 || string(m.composer) != "hello" {
		t.Fatalf("sent=%+v composer=%q", m.sentMessages, string(m.composer))
	}
}

func TestSentMessagesArePreservedPerConversation(t *testing.T) {
	m := model{
		width: 80, height: 20, selected: 0,
		rows:  []agentRow{{Name: "alpha", Scope: "local"}, {Name: "beta", Scope: "local"}},
		local: &fakeLocal{},
	}
	m.appendSentMessage(m.rows[0], makeOutboxRecord("agent-communicator", m.rows[0], "for alpha"))
	m.appendSentMessage(m.rows[1], makeOutboxRecord("agent-communicator", m.rows[1], "for beta"))

	updated, _ := m.Update(inboxLoaded{})
	m = updated.(model)
	if len(m.messages) != 1 || m.messages[0].Body != "for alpha" {
		t.Fatalf("alpha messages = %+v", m.messages)
	}

	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyCtrlN})
	m = updated.(model)
	updated, _ = m.Update(inboxLoaded{})
	m = updated.(model)
	if len(m.messages) != 1 || m.messages[0].Body != "for beta" {
		t.Fatalf("beta messages = %+v", m.messages)
	}
}

func TestMergedConversationOrdersMessagesByTimestamp(t *testing.T) {
	m := model{sentMessages: map[string][]tracker.Message{
		"alpha": {{Sender: "You", Body: "middle", Timestamp: "2026-05-19T12:01:00Z"}},
	}}
	merged := m.mergeSentMessages(agentRow{Name: "alpha"}, []tracker.Message{
		{Sender: "alpha", Body: "older", Timestamp: "2026-05-19T12:00:00Z"},
		{Sender: "alpha", Body: "newer", Timestamp: "2026-05-19T12:02:00Z"},
	})
	bodies := []string{merged[0].Body, merged[1].Body, merged[2].Body}
	if !reflect.DeepEqual(bodies, []string{"older", "middle", "newer"}) {
		t.Fatalf("bodies = %#v", bodies)
	}
}

func TestRemoteReplyAfterSentOrdersChronologically(t *testing.T) {
	row := agentRow{Name: "tanma/zv2-bmod-agent", TargetAddress: "tanmayvijay.c.googlers.com/zv2-bmod-agent", Scope: "remote"}
	m := model{sentMessages: map[string][]tracker.Message{
		row.TargetAddress: {{Sender: "You", Body: "sent", Timestamp: "2026-05-19T12:00:00Z"}},
	}}
	merged := m.mergeSentMessages(row, []tracker.Message{{Sender: "zv2-bmod-agent (via tanmayvijay.c.googlers.com)", Body: "reply", Timestamp: "2026-05-19T12:00:01Z"}})
	bodies := []string{merged[0].Body, merged[1].Body}
	if !reflect.DeepEqual(bodies, []string{"sent", "reply"}) {
		t.Fatalf("bodies = %#v", bodies)
	}
}

func TestEqualOrUnparsedTimestampsKeepStableOrder(t *testing.T) {
	m := model{sentMessages: map[string][]tracker.Message{
		"alpha": {{Sender: "You", Body: "sent", Timestamp: "not-a-time"}},
	}}
	merged := m.mergeSentMessages(agentRow{Name: "alpha"}, []tracker.Message{{Sender: "alpha", Body: "inbound", Timestamp: "not-a-time"}})
	if merged[0].Body != "inbound" || merged[1].Body != "sent" {
		t.Fatalf("merged = %+v", merged)
	}
}

func TestRemoteConversationShowsInMemorySentMessages(t *testing.T) {
	m := model{width: 80, height: 20, rows: []agentRow{{Name: "host/agent", Scope: "remote"}}}
	m.appendSentMessage(m.rows[0], makeOutboxRecord("agent-communicator", m.rows[0], "remote hello"))
	m.messages = m.mergeSentMessages(m.rows[0], nil)

	view := m.messageView(60)
	if !strings.Contains(view, "You") || !strings.Contains(view, "remote hello") {
		t.Fatalf("message view = %q", view)
	}
}
