package main

import "testing"

func TestAgentColorIndexIsDeterministicAndVaries(t *testing.T) {
	if agentColorIndex("review-agent") != agentColorIndex("review-agent") {
		t.Fatal("same agent should get stable color")
	}
	if agentColorIndex("review-agent") == agentColorIndex("zv2-bmod-agent") {
		t.Fatal("sample agents should get different colors")
	}
}

func TestSenderColorKeyUsesSenderSideOfAdvancedHeader(t *testing.T) {
	if got := senderColorKey("agent-communicator → review-agent"); got != "agent-communicator" {
		t.Fatalf("senderColorKey = %q", got)
	}
}
