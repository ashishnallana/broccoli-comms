package main

import (
	"fmt"
	"strings"
)

type taskChainFormState struct {
	Active  bool
	Action  string
	Input   []rune
	Depends []string
	Err     error
}

func (f taskChainFormState) Text() string { return string(f.Input) }

func (m model) startTaskChainForm(action string, depends []string) model {
	m.tasksForm = taskChainFormState{Active: true, Action: action, Depends: append([]string{}, depends...)}
	m.tasksConfirm = taskActionConfirmation{}
	return m
}

func parseTaskChainForm(text string, defaults taskChainFormState, fallbackAgent string) (title, agent, priority string, depends []string, err error) {
	parts := strings.Split(text, "|")
	title = strings.TrimSpace(parts[0])
	if title == "" {
		return "", "", "", nil, fmt.Errorf("task title is required")
	}
	agent = fallbackAgent
	priority = "P1"
	depends = append([]string{}, defaults.Depends...)
	if len(parts) > 1 && strings.TrimSpace(parts[1]) != "" {
		agent = strings.TrimSpace(parts[1])
	}
	if len(parts) > 2 && strings.TrimSpace(parts[2]) != "" {
		priority = strings.TrimSpace(parts[2])
	}
	if len(parts) > 3 && strings.TrimSpace(parts[3]) != "" {
		depends = mergeTaskDeps(depends, splitCSV(parts[3]))
	}
	return title, agent, priority, depends, nil
}

func mergeTaskDeps(base, extra []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, dep := range append(append([]string{}, base...), extra...) {
		dep = strings.TrimSpace(dep)
		if dep != "" && !seen[dep] {
			seen[dep] = true
			out = append(out, dep)
		}
	}
	return out
}

func splitCSV(value string) []string {
	var out []string
	for _, part := range strings.Split(value, ",") {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func (m model) completeTaskFormToken() model {
	if !m.tasksForm.Active {
		return m
	}
	text := m.tasksForm.Text()
	parts := strings.Split(text, "|")
	last := strings.TrimSpace(parts[len(parts)-1])
	options := m.taskFormAutocompleteOptions(len(parts)-1, last)
	if len(options) == 0 {
		return m
	}
	parts[len(parts)-1] = " " + options[0].Value
	m.tasksForm.Input = []rune(strings.Join(parts, "|"))
	return m
}

func taskChainFormHelp(action string) string {
	verb := "Add task"
	if action == "new_chain" {
		verb = "New chain"
	}
	return verb + ": title | agent | priority | depends · tab completes current field · enter save · esc cancel"
}

func (m model) taskFormAutocompleteOptions(fieldIndex int, query string) []taskAutocompleteOption {
	allowed := map[string]bool{}
	switch fieldIndex {
	case 1:
		allowed["agent"] = true
	case 2:
		allowed["priority"] = true
	case 3:
		allowed["task"] = true
		allowed["recent"] = true
		allowed["root"] = true
	default:
		return nil
	}
	var out []taskAutocompleteOption
	for _, option := range m.taskAutocompleteOptions(query) {
		if allowed[option.Kind] {
			out = append(out, option)
		}
	}
	return out
}
