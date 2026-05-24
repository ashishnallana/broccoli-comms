package main

import (
	"fmt"
	"os"
	"os/exec"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type editorClosed struct{ Err error }

func formatMessageForEditor(msg tracker.Message) string {
	return strings.TrimRight(fmt.Sprintf("# Message from %s\n\n_Time: %s_\n\n%s\n", msg.Sender, msg.Timestamp, msg.Body), "\n") + "\n"
}

func openMessageInEditor(msg tracker.Message) tea.Cmd {
	return func() tea.Msg {
		file, err := os.CreateTemp("", "agent-communicator-*.md")
		if err != nil {
			return editorClosed{Err: err}
		}
		path := file.Name()
		if _, err := file.WriteString(formatMessageForEditor(msg)); err != nil {
			file.Close()
			os.Remove(path)
			return editorClosed{Err: err}
		}
		file.Close()
		editor := os.Getenv("EDITOR")
		if editor == "" {
			editor = "vi"
		}
		return tea.ExecProcess(exec.Command(editor, path), func(err error) tea.Msg {
			os.Remove(path)
			return editorClosed{Err: err}
		})()
	}
}

func editPromptTemplate(path string) tea.Cmd {
	return func() tea.Msg {
		content, err := os.ReadFile(path)
		if err != nil {
			return promptEdited{Err: err}
		}
		file, err := os.CreateTemp("", "agent-communicator-prompt-*.md")
		if err != nil {
			return promptEdited{Err: err}
		}
		tempPath := file.Name()
		if _, err := file.Write(content); err != nil {
			file.Close()
			os.Remove(tempPath)
			return promptEdited{Err: err}
		}
		if err := file.Close(); err != nil {
			os.Remove(tempPath)
			return promptEdited{Err: err}
		}
		before, err := os.Stat(tempPath)
		if err != nil {
			os.Remove(tempPath)
			return promptEdited{Err: err}
		}
		// Open prompt templates in Neovim and mark the buffer modified so `:x`
		// performs an actual write even when the user sends the template unchanged.
		// Users can still cancel with `:q!`, which leaves the temp file unwritten.
		return tea.ExecProcess(exec.Command("nvim", "-c", "setlocal modified", tempPath), func(err error) tea.Msg {
			defer os.Remove(tempPath)
			if err != nil {
				return promptEdited{Err: err}
			}
			after, statErr := os.Stat(tempPath)
			if statErr != nil {
				return promptEdited{Err: statErr}
			}
			if !after.ModTime().After(before.ModTime()) {
				return promptEdited{Saved: false}
			}
			body, readErr := os.ReadFile(tempPath)
			if readErr != nil {
				return promptEdited{Err: readErr}
			}
			return promptEdited{Body: string(body), Saved: true}
		})()
	}
}
