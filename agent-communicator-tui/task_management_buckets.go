package main

import (
	"sort"
	"strings"
)

func latestStateByTask(states []taskWorkingState) map[string]taskWorkingState {
	byTask := map[string]taskWorkingState{}
	for _, state := range states {
		if state.TaskID == "" {
			continue
		}
		prev, ok := byTask[state.TaskID]
		if !ok || state.UpdatedAt >= prev.UpdatedAt {
			byTask[state.TaskID] = state
		}
	}
	return byTask
}

func approvalsByTask(approvals []taskApprovalRecord) map[string][]taskApprovalRecord {
	byTask := map[string][]taskApprovalRecord{}
	for _, approval := range approvals {
		if approval.TaskID != "" {
			byTask[approval.TaskID] = append(byTask[approval.TaskID], approval)
		}
	}
	return byTask
}

func (m model) activeTaskChainFor(selected agentRow, stateByTask map[string]taskWorkingState) (string, string, string) {
	if selected.Name == "" && selected.CurrentTaskID == "" {
		return "", "", ""
	}
	if selected.CurrentTaskID != "" {
		if state, ok := stateByTask[selected.CurrentTaskID]; ok {
			return state.TaskChainID, firstNonEmpty(state.RootTaskID, state.TaskChainID), selected.CurrentTaskID
		}
		return "", "", selected.CurrentTaskID
	}
	for _, state := range m.tasksStates {
		if selected.Name != "" && state.Agent != selected.Name {
			continue
		}
		if state.Status == "working" && state.TaskID != "" {
			return state.TaskChainID, firstNonEmpty(state.RootTaskID, state.TaskChainID), state.TaskID
		}
	}
	for _, task := range m.tasksItems {
		if selected.Name != "" && task.AssignedAgent != selected.Name {
			continue
		}
		if task.Status == "ready" || task.Status == "working" {
			state := stateByTask[task.TaskID]
			return state.TaskChainID, firstNonEmpty(state.RootTaskID, state.TaskChainID), task.TaskID
		}
	}
	return "", "", ""
}

func tasksForChain(tasks []taskRecord, chainID, rootID, currentTaskID string) []taskRecord {
	if chainID == "" && rootID == "" && currentTaskID == "" {
		return append([]taskRecord{}, tasks...)
	}
	ids := map[string]bool{}
	if rootID != "" {
		ids[rootID] = true
	}
	if currentTaskID != "" {
		ids[currentTaskID] = true
	}
	changed := true
	for changed {
		changed = false
		for _, task := range tasks {
			if ids[task.TaskID] {
				continue
			}
			for _, dep := range task.DependsOn {
				if ids[dep] {
					ids[task.TaskID] = true
					changed = true
					break
				}
			}
		}
	}
	var out []taskRecord
	for _, task := range tasks {
		if ids[task.TaskID] {
			out = append(out, task)
		}
	}
	return out
}

func mergeSelectedAgentTasks(items, all []taskRecord, selected agentRow) []taskRecord {
	if selected.Name == "" {
		return items
	}
	seen := map[string]bool{}
	for _, task := range items {
		seen[task.TaskID] = true
	}
	out := append([]taskRecord{}, items...)
	for _, task := range all {
		if !seen[task.TaskID] && task.AssignedAgent == selected.Name {
			seen[task.TaskID] = true
			out = append(out, task)
		}
	}
	return out
}

func bucketTasks(tasks []taskRecord, currentTaskID string, states map[string]taskWorkingState, approvals map[string][]taskApprovalRecord) []taskBucket {
	buckets := []taskBucket{{Name: "Current"}, {Name: "Next"}, {Name: "Queue"}, {Name: "Review"}, {Name: "Completed"}}
	for _, task := range sortedTasks(tasks) {
		idx := 2
		status := normalizedTaskStatus(task, states[task.TaskID])
		switch {
		case task.TaskID != "" && task.TaskID == currentTaskID:
			idx = 0
		case status == "ready":
			idx = 1
		case status == "completed" || status == "done" || status == "validated" || task.ResultStatus == "good":
			idx = 4
		case hasPendingApproval(approvals[task.TaskID]) || status == "review" || status == "pending_review":
			idx = 3
		default:
			idx = 2
		}
		buckets[idx].Tasks = append(buckets[idx].Tasks, task)
	}
	return buckets
}

func sortedTasks(tasks []taskRecord) []taskRecord {
	out := append([]taskRecord{}, tasks...)
	sort.SliceStable(out, func(i, j int) bool {
		if taskDependsOn(out[j], out[i].TaskID) {
			return true
		}
		if taskDependsOn(out[i], out[j].TaskID) {
			return false
		}
		if out[i].CreatedAt == out[j].CreatedAt {
			return out[i].TaskID < out[j].TaskID
		}
		return out[i].CreatedAt < out[j].CreatedAt
	})
	return out
}

func taskDependsOn(task taskRecord, depID string) bool {
	for _, dep := range task.DependsOn {
		if dep == depID {
			return true
		}
	}
	return false
}

func normalizedTaskStatus(task taskRecord, state taskWorkingState) string {
	status := strings.ToLower(strings.TrimSpace(firstNonEmpty(state.Status, task.Status, task.ResultStatus)))
	return strings.ReplaceAll(status, " ", "_")
}

func hasPendingApproval(approvals []taskApprovalRecord) bool {
	for _, approval := range approvals {
		if strings.EqualFold(approval.Status, "pending") {
			return true
		}
	}
	return false
}

func orderedTaskRows(buckets []taskBucket) []taskRecord {
	var rows []taskRecord
	for _, bucket := range buckets {
		rows = append(rows, bucket.Tasks...)
	}
	return rows
}

func (m *model) clampTaskSelection() {
	rows := orderedTaskRows(m.taskData().Buckets)
	if len(rows) == 0 {
		m.tasksSelected = 0
		m.tasksOffset = 0
		return
	}
	m.tasksSelected = min(max(0, m.tasksSelected), len(rows)-1)
	m.tasksOffset = min(max(0, m.tasksOffset), max(0, len(rows)-1))
}

func (m *model) moveTaskSelection(delta int) {
	rows := orderedTaskRows(m.taskData().Buckets)
	if len(rows) == 0 {
		m.tasksSelected = 0
		m.tasksOffset = 0
		return
	}
	m.tasksSelected = min(max(0, m.tasksSelected+delta), len(rows)-1)
	m.tasksOffset = m.tasksSelected
}

func countTaskBuckets(buckets []taskBucket) taskCounts {
	counts := taskCounts{}
	for _, bucket := range buckets {
		counts.Total += len(bucket.Tasks)
		switch bucket.Name {
		case "Current":
			counts.Working += len(bucket.Tasks)
		case "Next":
			counts.Ready += len(bucket.Tasks)
		case "Queue":
			for _, task := range bucket.Tasks {
				if strings.TrimSpace(task.BlockedReason) != "" || strings.EqualFold(task.Status, "blocked") {
					counts.Blocked++
				} else {
					counts.Queued++
				}
			}
		case "Review":
			counts.Review += len(bucket.Tasks)
		case "Completed":
			counts.Completed += len(bucket.Tasks)
		}
	}
	return counts
}

func collectTaskBlockers(tasks []taskRecord, states map[string]taskWorkingState) []string {
	seen := map[string]bool{}
	var blockers []string
	for _, task := range tasks {
		for _, blocker := range append([]string{task.BlockedReason}, states[task.TaskID].Blockers...) {
			blocker = strings.TrimSpace(blocker)
			if blocker != "" && !seen[blocker] {
				seen[blocker] = true
				blockers = append(blockers, blocker)
			}
		}
	}
	return blockers
}

func approvalsForChain(approvals []taskApprovalRecord, chainID, rootID string) []taskApprovalRecord {
	if chainID == "" && rootID == "" {
		return append([]taskApprovalRecord{}, approvals...)
	}
	var out []taskApprovalRecord
	for _, approval := range approvals {
		if (chainID != "" && approval.TaskChainID == chainID) || (rootID != "" && approval.RootTaskID == rootID) {
			out = append(out, approval)
		}
	}
	return out
}

func approvalsForTasks(approvals []taskApprovalRecord, tasks []taskRecord) []taskApprovalRecord {
	visible := map[string]bool{}
	for _, task := range tasks {
		if task.TaskID != "" {
			visible[task.TaskID] = true
		}
	}
	var out []taskApprovalRecord
	for _, approval := range approvals {
		if visible[approval.TaskID] {
			out = append(out, approval)
		}
	}
	return out
}
