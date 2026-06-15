package main

import tea "github.com/charmbracelet/bubbletea"

type taskCommandPaletteState struct {
	Open     bool
	Selected int
}

type taskCommandEntry struct {
	Label   string
	Help    string
	Enabled bool
	Run     func(model) (model, tea.Cmd)
}

func (m model) taskCommandEntries() []taskCommandEntry {
	_, hasTask := m.selectedTaskRecord()
	data := m.taskData()
	hasChain := len(data.Tasks) > 0
	hasAgent := m.currentRow().Name != ""
	return []taskCommandEntry{
		{Label: "Open details", Help: "show selected task details", Enabled: hasTask, Run: func(m model) (model, tea.Cmd) {
			if task, ok := m.selectedTaskRecord(); ok {
				m.directInputStatus = "Task details · " + task.TaskID + " · " + firstNonEmpty(task.Title, "Untitled task")
				m.directInputStatusErr = false
			}
			return m, nil
		}},
		{Label: "Edit next step", Help: "open next step in editor", Enabled: hasTask, Run: func(m model) (model, tea.Cmd) {
			task, _ := m.selectedTaskRecord()
			return m, editTaskFieldInEditor(task, "next_step")
		}},
		{Label: "Edit result summary", Help: "open result summary in editor", Enabled: hasTask, Run: func(m model) (model, tea.Cmd) {
			task, _ := m.selectedTaskRecord()
			return m, editTaskFieldInEditor(task, "result_summary")
		}},
		{Label: "Start / mark working", Help: "mark selected task working", Enabled: hasTask, Run: func(m model) (model, tea.Cmd) {
			task, _ := m.selectedTaskRecord()
			m.tasksLoading = true
			return m, taskActionCmd(task, "start", m.currentRow().Name)
		}},
		{Label: "Reassign task to selected agent", Help: "requires selected agent", Enabled: hasTask && hasAgent, Run: func(m model) (model, tea.Cmd) {
			task, _ := m.selectedTaskRecord()
			return m.confirmOrRunTaskAction(task, "assign")
		}},
		{Label: "Archive task", Help: "requires confirmation", Enabled: hasTask, Run: func(m model) (model, tea.Cmd) {
			task, _ := m.selectedTaskRecord()
			return m.confirmOrRunTaskAction(task, "archive")
		}},
		{Label: "Add task after selected", Help: "open add-after form", Enabled: hasTask, Run: func(m model) (model, tea.Cmd) {
			task, _ := m.selectedTaskRecord()
			return m.startTaskChainForm("add_after", []string{task.TaskID}), nil
		}},
		{Label: "New chain task", Help: "open new-chain form", Enabled: true, Run: func(m model) (model, tea.Cmd) { return m.startTaskChainForm("new_chain", nil), nil }},
		{Label: "Chain progress / summary", Help: "refresh chain summary", Enabled: hasChain, Run: func(m model) (model, tea.Cmd) {
			m.tasksLoading = true
			data := m.taskData()
			return m, summarizeTaskChainCmd(firstNonEmpty(data.ActiveChainID, data.RootTaskID))
		}},
		{Label: "Reassign active chain", Help: "requires selected agent and confirmation", Enabled: hasChain && hasAgent, Run: func(m model) (model, tea.Cmd) { return m.confirmOrRunChainAssign() }},
		{Label: "Archive active chain", Help: "requires confirmation", Enabled: hasChain, Run: func(m model) (model, tea.Cmd) { return m.confirmOrRunChainArchive() }},
	}
}

func (m model) selectedTaskCommand() (taskCommandEntry, bool) {
	entries := m.taskCommandEntries()
	if len(entries) == 0 {
		return taskCommandEntry{}, false
	}
	idx := min(max(0, m.tasksPalette.Selected), len(entries)-1)
	return entries[idx], true
}

func (m model) updateTaskCommandPalette(msg tea.KeyMsg) (model, tea.Cmd) {
	entries := m.taskCommandEntries()
	switch msg.Type {
	case tea.KeyEsc, tea.KeyCtrlK:
		m.tasksPalette = taskCommandPaletteState{}
		return m, nil
	case tea.KeyUp:
		m.tasksPalette.Selected = max(0, m.tasksPalette.Selected-1)
		return m, nil
	case tea.KeyDown:
		m.tasksPalette.Selected = min(max(0, len(entries)-1), m.tasksPalette.Selected+1)
		return m, nil
	case tea.KeyEnter:
		entry, ok := m.selectedTaskCommand()
		m.tasksPalette = taskCommandPaletteState{}
		if !ok || !entry.Enabled || entry.Run == nil {
			m.directInputStatus = "Task command unavailable"
			m.directInputStatusErr = true
			return m, nil
		}
		return entry.Run(m)
	}
	return m, nil
}
