package main

import (
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestMessagesUseBoxesAndWideSelectionBorder(t *testing.T) {
	m := model{messageSelected: 0, messages: []tracker.Message{{Sender: "alice", Body: "hello"}}}
	view := strings.Join(m.messageLinesForWidth(80), "\n")
	for _, want := range []string{"╔", "╚", "║ alice", "hello"} {
		if !strings.Contains(view, want) {
			t.Fatalf("message view missing %q:\n%s", want, view)
		}
	}
	if strings.Contains(view, "●") {
		t.Fatalf("selected message should not render selector dot:\n%s", view)
	}
}

func TestIncomingMessagesAreIndentedFiveCells(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "alice", Body: "hello"}}}
	lines := m.messageLinesForWidth(80)
	if len(lines) == 0 || !strings.HasPrefix(lines[0], "     ") {
		t.Fatalf("incoming bubble not indented:\n%s", strings.Join(lines, "\n"))
	}
}

func TestOutgoingMessagesAreLeftAligned(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "You", Body: "hello"}}}
	lines := m.messageLinesForWidth(80)
	if len(lines) == 0 || strings.HasPrefix(lines[0], "     ") {
		t.Fatalf("outgoing bubble should not be indented:\n%s", strings.Join(lines, "\n"))
	}
}

func TestAdvancedBubblesColorByConversationPartner(t *testing.T) {
	m := model{mode: advancedView, ownName: "agent-communicator"}
	if m.messageColorKey(tracker.Message{Sender: "alice"}) != "alice" {
		t.Fatal("inbound should color by sender")
	}
	if m.messageColorKey(tracker.Message{Sender: "to bob"}) != "bob" {
		t.Fatal("outbound should color by receiver")
	}
	if m.messageColorKey(tracker.Message{Sender: "agent-communicator → carol"}) != "carol" {
		t.Fatal("legacy outbound should color by receiver")
	}
}

func TestOutgoingAndIncomingUseDifferentBorderColors(t *testing.T) {
	m := model{}
	incoming := m.messageBorderColor(tracker.Message{Sender: "alice"}, "alice")
	outgoing := m.messageBorderColor(tracker.Message{Sender: "You"}, "alice")
	if incoming == outgoing {
		t.Fatalf("incoming and outgoing colors should differ: %s", incoming)
	}
}
