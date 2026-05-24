package main

import (
	"fmt"
	"testing"

	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestSelectionScrollsDownIntoView(t *testing.T) {
	m := model{width: 80, height: 10}
	for i := 0; i < 8; i++ {
		m.messages = append(m.messages, tracker.Message{Sender: "a", Body: fmt.Sprintf("msg %d", i)})
	}
	m.messageSelected = 6
	m.messageOffset = 0
	m.scrollSelectedMessageIntoView()
	start, _ := m.selectedMessageLineRange()
	if start < m.messageOffset || start >= m.messageOffset+m.messageVisibleLines() {
		t.Fatalf("selected start=%d offset=%d visible=%d", start, m.messageOffset, m.messageVisibleLines())
	}
}

func TestSelectionScrollsUpIntoView(t *testing.T) {
	m := model{width: 80, height: 10}
	for i := 0; i < 8; i++ {
		m.messages = append(m.messages, tracker.Message{Sender: "a", Body: fmt.Sprintf("msg %d", i)})
	}
	m.messageSelected = 7
	m.scrollSelectedMessageIntoView()
	m.messageSelected = 1
	m.scrollSelectedMessageIntoView()
	start, _ := m.selectedMessageLineRange()
	if start < m.messageOffset || start >= m.messageOffset+m.messageVisibleLines() {
		t.Fatalf("selected start=%d offset=%d visible=%d", start, m.messageOffset, m.messageVisibleLines())
	}
}
