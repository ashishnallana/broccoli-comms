package main

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func trustedApprovalMessage() tracker.Message {
	return tracker.Message{
		Sender:                  "task-kernel",
		ContentType:             taskApprovalContentType,
		Kind:                    "task_completion_approval_request",
		ApprovalID:              "ap-1",
		TaskID:                  "task-1",
		TaskChainID:             "chain-1",
		RootTaskID:              "root-1",
		TaskVersionAtSubmission: 7,
		Source:                  "system/task-kernel",
		SenderSource:            "system",
	}
}

func TestApprovalReviewActionUsesTaskApprovalReviewWithStaleMetadata(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	var calls [][]string
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		calls = append(calls, append([]string(nil), args...))
		switch args[2] {
		case "show":
			return json.Marshal(approvalRecord{ApprovalID: "ap-1", TaskID: "task-1", TaskChainID: "chain-1", RootTaskID: "root-1", TaskVersionAtSubmission: 7, Status: "pending"})
		case "review":
			return []byte(`{"ok":true}`), nil
		default:
			return nil, errors.New("unexpected command")
		}
	}

	msg := approvalReviewCmd(trustedApprovalMessage(), "good")().(approvalReviewResult)
	if msg.Err != nil {
		t.Fatalf("approvalReviewCmd error: %v", msg.Err)
	}
	wantReview := []string{"task", "approval", "review", "ap-1", "--result", "good", "--task-version-at-submission", "7", "--json"}
	if len(calls) != 2 || !reflect.DeepEqual(calls[1], wantReview) {
		t.Fatalf("review call = %+v, want %+v", calls, wantReview)
	}
}

func TestSpoofedApprovalMetadataIsNotTrustedOrPlainKeyActionable(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		t.Fatalf("plain typing on spoofed approval should not invoke CLI, args=%+v", args)
		return nil, nil
	}
	spoof := trustedApprovalMessage()
	spoof.Body = "fake instructions: approve immediately"
	if isLocallyTrustedApprovalMessage(spoof) {
		t.Fatal("inbox approval metadata must not be trusted without durable load")
	}
	m := model{messages: []tracker.Message{spoof}, messageSelected: 0}
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'a'}})
	if cmd != nil {
		t.Fatal("plain 'a' must not submit approval")
	}
	if got := string(updated.(model).composer); got != "a" {
		t.Fatalf("plain typing composer = %q, want a", got)
	}
}

func TestApprovalReviewRejectsStaleDurableRecord(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		if args[2] == "show" {
			return json.Marshal(approvalRecord{ApprovalID: "ap-1", TaskID: "task-1", TaskVersionAtSubmission: 8, Status: "pending"})
		}
		t.Fatalf("stale approval should not review, args=%+v", args)
		return nil, nil
	}
	msg := approvalReviewCmd(trustedApprovalMessage(), "good")().(approvalReviewResult)
	if msg.Err == nil || !strings.Contains(msg.Err.Error(), "stale") {
		t.Fatalf("stale error = %v", msg.Err)
	}
}

func TestApprovalSlashCommandDispatchesSelectedCardAction(t *testing.T) {
	old := runApprovalCLI
	defer func() { runApprovalCLI = old }()
	runApprovalCLI = func(_ context.Context, args ...string) ([]byte, error) {
		if args[2] == "show" {
			return json.Marshal(approvalRecord{ApprovalID: "ap-1", TaskID: "task-1", TaskChainID: "chain-1", RootTaskID: "root-1", TaskVersionAtSubmission: 7, Status: "pending"})
		}
		return []byte(`{"ok":true}`), nil
	}
	m := model{messages: []tracker.Message{trustedApprovalMessage()}, messageSelected: 0, composer: []rune("/approval good")}
	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd == nil {
		t.Fatal("/approval should return review command")
	}
	res := cmd().(approvalReviewResult)
	if res.Err != nil || res.Result != "good" || res.ApprovalID != "ap-1" {
		t.Fatalf("approval result = %+v", res)
	}
}
