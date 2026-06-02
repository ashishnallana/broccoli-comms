package main

import (
	"strings"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestMessagesUseBubblelessTimelineRail(t *testing.T) {
	m := model{messageSelected: 0, messages: []tracker.Message{{Sender: "alice", Body: "hello"}}}
	view := strings.Join(m.messageLinesForWidth(80), "\n")
	for _, want := range []string{"┃", "alice", "hello"} {
		if !strings.Contains(view, want) {
			t.Fatalf("message view missing %q:\n%s", want, view)
		}
	}
	for _, unwanted := range []string{"╔", "╚", "╭", "╰"} {
		if strings.Contains(view, unwanted) {
			t.Fatalf("bubbleless timeline should not contain %q:\n%s", unwanted, view)
		}
	}
}

func TestOutgoingMessagesShowReceiptTicks(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "You", Body: "hello", Read: true}}}
	view := strings.Join(m.messageLinesForWidth(80), "\n")
	if !strings.Contains(view, "✓✓") || !strings.Contains(view, "read") {
		t.Fatalf("outgoing receipt missing:\n%s", view)
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

func TestMessageHeaderUsesSenderMetadataWhenPresent(t *testing.T) {
	m := model{messages: []tracker.Message{{
		Sender:          "alice",
		SenderHostname:  "workstation-long",
		SenderModelType: "pi",
		Body:            "hello",
	}}}
	view := strings.Join(m.messageLinesForWidth(90), "\n")
	for _, want := range []string{"Pi alice @ works", "hello"} {
		if !strings.Contains(view, want) {
			t.Fatalf("message view missing %q:\n%s", want, view)
		}
	}
}

func TestLegacyMessageHeaderStillRendersSender(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "legacy-agent", Body: "hello"}}}
	view := strings.Join(m.messageLinesForWidth(90), "\n")
	if !strings.Contains(view, "legacy-agent") || strings.Contains(view, "??") {
		t.Fatalf("legacy message header changed unexpectedly:\n%s", view)
	}
}
