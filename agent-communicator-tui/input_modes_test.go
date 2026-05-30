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
	if m.inputMode != inputModeText || !strings.Contains(m.composerModeHint(120), "/text") {
		t.Fatalf("text mode not active: mode=%v hint=%q", m.inputMode, m.composerModeHint(120))
	}
	updated, _ = m.Update(tea.KeyMsg{Type: tea.KeyF3})
	m = updated.(model)
	if m.inputMode != inputModeKeys || !strings.Contains(m.composerModeHint(120), "/keys") {
		t.Fatalf("key mode not active: mode=%v hint=%q", m.inputMode, m.composerModeHint(120))
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

func TestComposerModeButtonsExcludeTargetAndBroadcast(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local", ModelType: "pi", Hostname: "workstation"}}, inputMode: inputModeMessage}
	hint := m.composerModeHint(160)
	for _, want := range []string{"/msg", "/text", "/keys", "╭", "╰"} {
		if !strings.Contains(hint, want) {
			t.Fatalf("hint missing %q: %s", want, hint)
		}
	}
	for _, unwanted := range []string{"target", "alpha Pi", "broadcast", "F4"} {
		if strings.Contains(hint, unwanted) {
			t.Fatalf("hint should not contain %q: %s", unwanted, hint)
		}
	}
}

func TestComposerInputAreaDoesNotIncludeModeButtons(t *testing.T) {
	m := model{rows: []agentRow{{Name: "alpha", Scope: "local"}}, inputMode: inputModeMessage}
	input := m.composerView(120)
	for _, unwanted := range []string{"/msg", "/text", "/keys", "broadcast", "target"} {
		if strings.Contains(input, unwanted) {
			t.Fatalf("composer input should not contain %q: %s", unwanted, input)
		}
	}
}

func TestFooterDoesNotAdvertiseBroadcastOrF4(t *testing.T) {
	footer := model{width: 160}.footer(160)
	for _, unwanted := range []string{"broadcast", "F4"} {
		if strings.Contains(footer, unwanted) {
			t.Fatalf("footer should not contain %q: %s", unwanted, footer)
		}
	}
	for _, want := range []string{"F1-F3 input", "/msg message", "/text /key pane control"} {
		if !strings.Contains(footer, want) {
			t.Fatalf("footer missing %q: %s", want, footer)
		}
	}
}
