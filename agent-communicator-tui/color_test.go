package main

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
)

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

func TestDefaultThemeUsesANSIColorIndexes(t *testing.T) {
	theme := defaultTerminalTheme()
	for name, color := range map[string]lipgloss.Color{
		"BaseBg":        theme.BaseBg,
		"PanelBg":       theme.PanelBg,
		"PanelBgAlt":    theme.PanelBgAlt,
		"RightColumnBg": theme.RightColumnBg,
		"Text":          theme.Text,
		"TextStrong":    theme.TextStrong,
		"TextSubtle":    theme.TextSubtle,
		"Muted":         theme.Muted,
		"Accent":        theme.Accent,
		"AccentStrong":  theme.AccentStrong,
		"Success":       theme.Success,
		"Warning":       theme.Warning,
		"Error":         theme.Error,
		"Info":          theme.Info,
		"Border":        theme.Border,
		"SelectedBg":    theme.SelectedBg,
		"SelectedFg":    theme.SelectedFg,
		"InputBg":       theme.InputBg,
		"PopupBg":       theme.PopupBg,
		"PopupBorder":   theme.PopupBorder,
		"ReadTick":      theme.ReadTick,
		"DeliveredTick": theme.DeliveredTick,
		"SentTick":      theme.SentTick,
	} {
		if !isANSIIndexColor(color) {
			t.Fatalf("%s = %q, want ANSI color index", name, color)
		}
	}
	for i, color := range theme.AgentColors {
		if !isANSIIndexColor(color) {
			t.Fatalf("AgentColors[%d] = %q, want ANSI color index", i, color)
		}
	}
}

func TestStatusColorsUseSemanticThemeRoles(t *testing.T) {
	cases := []struct {
		status string
		want   lipgloss.Color
	}{
		{"idle", colors.Success},
		{"waiting", colors.Warning},
		{"failed", colors.Error},
		{"mystery", colors.Muted},
	}
	for _, tc := range cases {
		got := statusDotStyle(tc.status).GetForeground()
		if got == nil || string(got.(lipgloss.Color)) != string(tc.want) {
			t.Fatalf("status %q color = %v, want %s", tc.status, got, tc.want)
		}
	}
}

func TestNoRawHexColorsOutsideThemeFile(t *testing.T) {
	hex := regexp.MustCompile(`#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})`)
	entries, err := os.ReadDir(".")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !strings.HasSuffix(name, ".go") || name == "theme.go" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(".", name))
		if err != nil {
			t.Fatal(err)
		}
		if match := hex.Find(data); match != nil {
			t.Fatalf("raw hex color %q found outside theme.go in %s", match, name)
		}
		if strings.Contains(string(data), "lipgloss.Color(\"#") {
			t.Fatalf("direct hex lipgloss.Color found outside theme.go in %s", name)
		}
	}
}

func isANSIIndexColor(color lipgloss.Color) bool {
	value := string(color)
	if value == "" || strings.HasPrefix(value, "#") {
		return false
	}
	for _, r := range value {
		if r < '0' || r > '9' {
			return false
		}
	}
	idx := 0
	for _, r := range value {
		idx = idx*10 + int(r-'0')
	}
	return idx >= 0 && idx <= 15
}
