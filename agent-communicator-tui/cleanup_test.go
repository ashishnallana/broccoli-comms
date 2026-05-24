package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPruneJSONLFileKeepsLatestLines(t *testing.T) {
	path := filepath.Join(t.TempDir(), "history.jsonl")
	var b strings.Builder
	for i := 0; i < 5; i++ {
		fmt.Fprintf(&b, "{\"n\":%d}\n", i)
	}
	if err := os.WriteFile(path, []byte(b.String()), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := pruneJSONLFile(path, 3, ""); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	want := "{\"n\":2}\n{\"n\":3}\n{\"n\":4}\n"
	if string(got) != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestCleanupHistoryOnStartPrunesOutboxAndInbox(t *testing.T) {
	state := t.TempDir()
	cache := t.TempDir()
	t.Setenv("XDG_STATE_HOME", state)
	t.Setenv("XDG_CACHE_HOME", cache)
	t.Setenv("AGENT_ID", communicatorAgentID)
	outbox := outboxPath()
	inbox := communicatorInboxPath()
	for _, path := range []string{outbox, inbox} {
		if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
			t.Fatal(err)
		}
		var b strings.Builder
		for i := 0; i < retainedHistoryMessages+2; i++ {
			fmt.Fprintf(&b, "{\"n\":%d}\n", i)
		}
		if err := os.WriteFile(path, []byte(b.String()), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	if err := cleanupHistoryOnStart(); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{outbox, inbox} {
		got, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if lines := strings.Count(string(got), "\n"); lines != retainedHistoryMessages {
			t.Fatalf("%s has %d lines", path, lines)
		}
		if strings.Contains(string(got), "{\"n\":0}") || !strings.Contains(string(got), "{\"n\":1001}") {
			t.Fatalf("%s did not retain latest lines", path)
		}
	}
}
