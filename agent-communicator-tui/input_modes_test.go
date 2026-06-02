package main

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

func TestFunctionKeysSwitchPersistentInputModes(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local", ModelType: "pi", Hostname: "workstation"}}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyF2})
	m = updated.(model)
	if m.inputMode != inputModeText || !strings.Contains(m.composerView(80), "/text") {
		t.Fatalf("text mode not active: mode=%v composer=%q", m.inputMode, m.composerView(80))
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyF3})
	m = updated.(model)
	if m.inputMode != inputModeKeys || !strings.Contains(m.composerView(80), "/keys") {
		t.Fatalf("key mode not active: mode=%v composer=%q", m.inputMode, m.composerView(80))
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyF4})
	m = updated.(model)
	if m.inputMode != inputModeKeys {
		t.Fatalf("F4 should not expose broadcast mode: %v", m.inputMode)
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyF1})
	if updated.(model).inputMode != inputModeMessage {
		t.Fatalf("message mode not restored: %v", updated.(model).inputMode)
	}
}

func TestTextModeSendsDirectPaneInputWithoutSlashPrefix(t *testing.T) {
	local := &fakeLocal{}
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}, local: local, inputMode: inputModeText, sentMessages: map[string][]tracker.Message{}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("hello pane")})
	m = updated.(model)
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	m, _ = mustUpdate(m, cmd())
	if local.directTarget != "alpha" || local.directText != "hello pane" || !local.directSubmit {
		t.Fatalf("direct target/text/submit = %q/%q/%v", local.directTarget, local.directText, local.directSubmit)
	}
	if local.sentBody != "" || len(m.outbox) != 0 {
		t.Fatalf("normal message sent unexpectedly: sentBody=%q outbox=%+v", local.sentBody, m.outbox)
	}
}

func TestKeyModeSendsDirectKeysWithoutSlashPrefix(t *testing.T) {
	local := &fakeLocal{}
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}, local: local, inputMode: inputModeKeys}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("C-c Enter")})
	m = updated.(model)
	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	_ = cmd()
	if local.directTarget != "alpha" || strings.Join(local.directKeys, ",") != "C-c,Enter" {
		t.Fatalf("direct target/keys = %q/%+v", local.directTarget, local.directKeys)
	}
}

func TestKeysSlashAliasSendsDirectKeys(t *testing.T) {
	action := parseComposerAction("/keys C-c Enter")
	if action.Kind != "direct_keys" || strings.Join(action.Keys, ",") != "C-c,Enter" {
		t.Fatalf("/keys action = %+v", action)
	}
}

func TestBroadcastSlashRemainsDisabledInternally(t *testing.T) {
	local := &fakeLocal{}
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}, local: local, sentMessages: map[string][]tracker.Message{}}
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("/broadcast hello all")})
	m = updated.(model)
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = updated.(model)
	if cmd == nil || local.sentBody != "" || local.directText != "" || local.directTarget != "" || len(m.outbox) != 0 {
		t.Fatalf("broadcast should only schedule status clear and not send: cmd=%v sent=%q direct=%q/%q outbox=%+v", cmd, local.sentBody, local.directTarget, local.directText, m.outbox)
	}
	if !m.directInputStatusErr || !strings.Contains(m.directInputStatus, "Broadcast mode is disabled") || string(m.composer) != "/broadcast hello all" {
		t.Fatalf("broadcast disabled status/composer = %q err=%v composer=%q", m.directInputStatus, m.directInputStatusErr, string(m.composer))
	}
}

func TestComposerShowsOnlyMinimalSupportedHelp(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local", ModelType: "pi", Hostname: "workstation"}}, inputMode: inputModeMessage}
	hint := m.composerModeHint(160)
	for _, want := range []string{"/msg sends an inbox message", "Enter send"} {
		if !strings.Contains(hint, want) {
			t.Fatalf("hint missing %q: %s", want, hint)
		}
	}
	for _, unwanted := range []string{"/text", "/keys", "broadcast", "F4", "Ctrl"} {
		if strings.Contains(hint, unwanted) {
			t.Fatalf("hint should not contain %q: %s", unwanted, hint)
		}
	}
}

func TestComposerInputAreaIncludesInlineModeOnly(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}, inputMode: inputModeMessage}
	input := m.composerView(120)
	if !strings.Contains(input, "/msg") {
		t.Fatalf("composer input should contain inline mode: %s", input)
	}
	for _, unwanted := range []string{"/text", "/keys", "Send chat message", "broadcast", "target", "alpha"} {
		if strings.Contains(input, unwanted) {
			t.Fatalf("composer input should not contain %q: %s", unwanted, input)
		}
	}
}

func TestFooterDoesNotAdvertiseShortcuts(t *testing.T) {
	footer := model{width: 160}.footer(160)
	for _, unwanted := range []string{"broadcast", "F4", "F1-F3", "Ctrl", "pane control"} {
		if strings.Contains(footer, unwanted) {
			t.Fatalf("footer should not contain %q: %s", unwanted, footer)
		}
	}
}
