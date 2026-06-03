package main

import (
	"encoding/json"
	"fmt"
	"strings"
)

const paneCaptureRenderLineLimit = 10

type paneCaptureDetails struct {
	Source   string
	Pane     string
	Session  string
	Captured string
	Content  string
	Detected bool
}

type paneCaptureJSONPayload struct {
	Type            string `json:"type"`
	SourceAgentName string `json:"source_agent_name"`
	TmuxPane        string `json:"tmux_pane"`
	Session         string `json:"session"`
	CapturedAt      string `json:"captured_at"`
	Content         string `json:"content"`
}

func paneCaptureDisplayBody(body string) (string, bool) {
	details := parsePaneCaptureMessage(body)
	if !details.Detected {
		return body, false
	}
	contentLines := strings.Split(strings.TrimRight(details.Content, "\n"), "\n")
	if len(contentLines) == 1 && contentLines[0] == "" {
		contentLines = nil
	}
	hidden := max(0, len(contentLines)-paneCaptureRenderLineLimit)
	if hidden > 0 {
		contentLines = contentLines[hidden:]
	}

	title := "▣ pane capture · terminal snapshot"
	meta := []string{}
	if details.Source != "" {
		meta = append(meta, "from "+details.Source)
	}
	if details.Pane != "" && details.Pane != "unknown" {
		meta = append(meta, "pane "+details.Pane)
	}
	if details.Session != "" && details.Session != "unknown" {
		meta = append(meta, "session "+details.Session)
	}
	if details.Captured != "" {
		meta = append(meta, details.Captured)
	}
	out := []string{title}
	if len(meta) > 0 {
		out = append(out, "  "+strings.Join(meta, " · "))
	}
	if hidden > 0 {
		out = append(out, fmt.Sprintf("… %d earlier lines hidden", hidden))
	}
	if len(contentLines) == 0 {
		out = append(out, "│ <empty capture>")
	} else {
		for _, line := range contentLines {
			out = append(out, "│ "+line)
		}
	}
	return strings.Join(out, "\n"), true
}

func parsePaneCaptureMessage(body string) paneCaptureDetails {
	trimmed := strings.TrimSpace(body)
	if strings.HasPrefix(trimmed, "{") {
		var payload paneCaptureJSONPayload
		if err := json.Unmarshal([]byte(trimmed), &payload); err == nil && payload.Type == "pane_snapshot" {
			return paneCaptureDetails{
				Source:   payload.SourceAgentName,
				Pane:     payload.TmuxPane,
				Session:  payload.Session,
				Captured: payload.CapturedAt,
				Content:  payload.Content,
				Detected: true,
			}
		}
	}

	lines := strings.Split(body, "\n")
	if len(lines) == 0 {
		return paneCaptureDetails{}
	}
	first := strings.TrimSpace(lines[0])
	// TODO: replace this TUI-only string heuristic with robust upstream metadata,
	// e.g. content-type `text/x-pane-capture` or a message `kind: pane_capture` field.
	if !strings.HasPrefix(first, "### Pane Capture Snapshot from") && !strings.HasPrefix(first, "### Mock Pane Capture Snapshot from") {
		return paneCaptureDetails{}
	}
	details := paneCaptureDetails{Detected: true}
	if source, ok := strings.CutPrefix(first, "### Pane Capture Snapshot from "); ok {
		details.Source = strings.TrimSpace(source)
	} else if source, ok := strings.CutPrefix(first, "### Mock Pane Capture Snapshot from "); ok {
		details.Source = strings.TrimSpace(source)
	}
	for _, line := range lines[1:] {
		switch {
		case strings.HasPrefix(line, "- **Pane:**"):
			details.Pane = strings.TrimSpace(strings.TrimPrefix(line, "- **Pane:**"))
		case strings.HasPrefix(line, "- **Session:**"):
			details.Session = strings.TrimSpace(strings.TrimPrefix(line, "- **Session:**"))
		case strings.HasPrefix(line, "- **Captured At:**"):
			details.Captured = strings.TrimSpace(strings.TrimPrefix(line, "- **Captured At:**"))
		}
	}
	start := strings.Index(body, "```\n")
	end := strings.LastIndex(body, "\n```")
	if start >= 0 && end > start {
		details.Content = body[start+4 : end]
		return details
	}
	contentLines := []string{}
	for _, line := range lines[1:] {
		trimmedLine := strings.TrimSpace(line)
		if trimmedLine == "" || strings.HasPrefix(trimmedLine, "-") || strings.HasPrefix(trimmedLine, "```") {
			continue
		}
		contentLines = append(contentLines, line)
	}
	details.Content = strings.Join(contentLines, "\n")
	return details
}
