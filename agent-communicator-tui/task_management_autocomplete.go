package main

import "strings"

type taskAutocompleteOption struct {
	Kind  string
	Value string
}

func (m model) taskAutocompleteOptions(query string) []taskAutocompleteOption {
	query = strings.ToLower(strings.TrimSpace(query))
	seen := map[string]bool{}
	add := func(options *[]taskAutocompleteOption, kind, value string) {
		if value == "" || seen[kind+"\x00"+value] {
			return
		}
		if query != "" && !strings.Contains(strings.ToLower(value), query) {
			return
		}
		seen[kind+"\x00"+value] = true
		*options = append(*options, taskAutocompleteOption{Kind: kind, Value: value})
	}
	var options []taskAutocompleteOption
	for _, row := range m.rows {
		add(&options, "agent", row.Name)
		add(&options, "task", row.CurrentTaskID)
	}
	for _, task := range m.tasksItems {
		add(&options, "task", task.TaskID)
		add(&options, "status", task.Status)
		add(&options, "priority", task.Priority)
		for _, dep := range task.DependsOn {
			add(&options, "recent", dep)
		}
	}
	for _, state := range m.tasksStates {
		add(&options, "chain", state.TaskChainID)
		add(&options, "root", state.RootTaskID)
		add(&options, "task", state.TaskID)
	}
	for _, value := range []string{"planning", "ready", "working", "blocked", "review", "done", "validated", "archived"} {
		add(&options, "status", value)
	}
	for _, value := range []string{"P0", "P1", "P2", "P3"} {
		add(&options, "priority", value)
	}
	return options
}
