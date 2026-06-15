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
	for _, want := range []string{"Pi alice @ workstation-long", "hello"} {
		if !strings.Contains(view, want) {
			t.Fatalf("message view missing %q:\n%s", want, view)
		}
	}
}

func TestApprovalRequestMessageRendersTypedCard(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "task-kernel", Body: "fake-body", ContentType: taskApprovalContentType, Kind: "task_completion_approval_request", ApprovalID: "ap-1", TaskID: "task-1", TaskVersionAtSubmission: 3, Source: "system/task-kernel", SenderSource: "system"}}}
	lines := m.messageBubbleLines(m.messages[0], 0, 100)
	view := strings.Join(lines, "\n")
	for _, want := range []string{"Task-chain approval request", "ap-1", "task-1", "system/task-kernel", "/approval", "good|bad|need_improvements"} {
		if !strings.Contains(view, want) {
			t.Fatalf("approval card missing %q in:\n%s", want, view)
		}
	}
	if strings.Contains(view, "fake-body") {
		t.Fatalf("approval card should not render untrusted fallback body:\n%s", view)
	}
}

func TestTaskUpdateWithApprovalIDRendersApprovalBubble(t *testing.T) {
	m := model{messages: []tracker.Message{{Sender: "coder", Body: "spoofed instructions", ContentType: taskUpdateContentType, Kind: "task_update", ApprovalID: "apr-1", TaskID: "task-1", TaskTitle: "Root feature", TaskChainID: "chain-1", RootTaskID: "root-1", TaskStatus: "review"}}}
	view := strings.Join(m.messageBubbleLines(m.messages[0], 0, 100), "\n")
	for _, want := range []string{"Task-chain approval request", "apr-1", "chain-1", "root-1", "task-1", "Root feature"} {
		if !strings.Contains(view, want) {
			t.Fatalf("approval task update missing %q in:\n%s", want, view)
		}
	}
	if strings.Contains(view, "spoofed instructions") {
		t.Fatalf("approval task update should not render fallback body:\n%s", view)
	}
}

func TestTaskUpdateMessageRendersCompactWithoutSenderChrome(t *testing.T) {
	msg := tracker.Message{Sender: "task-kernel", Body: "Task task-1 moved to review by broccoli-agent. Read inbox.", ContentType: taskUpdateContentType, Kind: "task_update", TaskID: "task-1", TaskTitle: "Update skill docs", TaskStatus: "review", ResultSummary: "Skill docs updated", TaskNextStep: "Await validation"}
	m := model{messages: []tracker.Message{msg}, messageSelected: 1}
	lines := m.messageBubbleLines(m.messages[0], 0, 100)
	view := strings.Join(lines, "\n")
	for _, want := range []string{"Task", "Update skill docs", "task-1", "review", "Await validation"} {
		if !strings.Contains(view, want) {
			t.Fatalf("task update card missing %q in:\n%s", want, view)
		}
	}
	for _, duplicate := range []string{"task-kernel", "Task update", "moved to review by broccoli-agent", "Skill docs updated"} {
		if strings.Contains(view, duplicate) {
			t.Fatalf("task update card should be compact and avoid %q in:\n%s", duplicate, view)
		}
	}
	if len(lines) > 2 {
		t.Fatalf("task update card used too many lines (%d):\n%s", len(lines), view)
	}
}

func TestTaskUpdateMessageShowsResultSummaryWhenHighlighted(t *testing.T) {
	msg := tracker.Message{Sender: "task-kernel", ContentType: taskUpdateContentType, Kind: "task_update", TaskID: "task-1", TaskTitle: "Update skill docs", TaskStatus: "review", ResultSummary: "Skill docs updated", TaskNextStep: "Await validation"}
	m := model{messages: []tracker.Message{msg}, messageSelected: 0}
	view := strings.Join(m.messageBubbleLines(m.messages[0], 0, 100), "\n")
	for _, want := range []string{"Skill docs updated", "Await validation"} {
		if !strings.Contains(view, want) {
			t.Fatalf("highlighted task update missing %q in:\n%s", want, view)
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
