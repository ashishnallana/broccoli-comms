package main

import "strings"

type taskParticipant struct {
	ParticipantID string `json:"participant_id"`
	TaskID        string `json:"task_id"`
	TaskChainID   string `json:"task_chain_id"`
	RootTaskID    string `json:"root_task_id"`
	Agent         string `json:"agent"`
	Role          string `json:"role"`
	InstanceID    string `json:"instance_id"`
	Status        string `json:"status"`
	UpdatedAt     string `json:"updated_at"`
	Compatibility bool   `json:"compatibility"`
}

type taskRecord struct {
	TaskID             string            `json:"task_id"`
	Title              string            `json:"title"`
	Description        string            `json:"description"`
	Status             string            `json:"status"`
	Priority           string            `json:"priority"`
	AssignedAgent      string            `json:"assigned_agent"`
	Scope              string            `json:"scope"`
	BlockedReason      string            `json:"blocked_reason"`
	NextStep           string            `json:"next_step"`
	ResultStatus       string            `json:"result_status"`
	ResultSummary      string            `json:"result_summary"`
	DependsOn          []string          `json:"depends_on"`
	AcceptanceCriteria []string          `json:"acceptance_criteria"`
	Participants       []taskParticipant `json:"participants"`
	CreatedAt          string            `json:"created_at"`
	UpdatedAt          string            `json:"updated_at"`
	Version            int               `json:"version"`
}

type taskWorkingState struct {
	TaskID          string   `json:"task_id"`
	Agent           string   `json:"agent"`
	InstanceID      string   `json:"instance_id"`
	Status          string   `json:"status"`
	CurrentActivity string   `json:"current_activity"`
	NextStep        string   `json:"next_step"`
	Notes           string   `json:"notes"`
	TaskChainID     string   `json:"task_chain_id"`
	RootTaskID      string   `json:"root_task_id"`
	Blockers        []string `json:"blockers"`
	UpdatedAt       string   `json:"updated_at"`
	Version         int      `json:"version"`
}

type taskApprovalRecord struct {
	ApprovalID     string `json:"approval_id"`
	TaskID         string `json:"task_id"`
	TaskChainID    string `json:"task_chain_id"`
	RootTaskID     string `json:"root_task_id"`
	Status         string `json:"status"`
	Result         string `json:"result"`
	ResultSummary  string `json:"result_summary"`
	AcceptanceNote string `json:"acceptance_summary"`
	CreatedAt      string `json:"created_at"`
	DecidedAt      string `json:"decided_at"`
}

type taskBucket struct {
	Name  string
	Tasks []taskRecord
}

type taskCounts struct {
	Total     int
	Working   int
	Ready     int
	Queued    int
	Blocked   int
	Review    int
	Completed int
}

type taskChainSummary struct {
	ChainID        string
	RootTaskID     string
	RootTitle      string
	Tasks          []taskRecord
	Buckets        []taskBucket
	Counts         taskCounts
	Participants   []taskParticipant
	Agents         []string
	CurrentTask    taskRecord
	NextTask       taskRecord
	LatestActivity string
	LatestUpdate   string
	Blockers       []string
	Approvals      []taskApprovalRecord
}

type taskManagementData struct {
	SelectedAgent agentRow
	ActiveChainID string
	RootTaskID    string
	CurrentTaskID string
	SelectedIndex int
	Offset        int
	Buckets       []taskBucket
	Counts        taskCounts
	Blockers      []string
	Approvals     []taskApprovalRecord
	Tasks         []taskRecord
	States        []taskWorkingState
	Chains        []taskChainSummary
	SelectedChain taskChainSummary
	ChainFocused  bool
	AgentFilter   string
	FilterAgents  []string
}

func (m model) taskData() taskManagementData {
	selected := m.currentRow()
	stateByTask := latestStateByTask(m.tasksStates)
	approvalByTaskAll := approvalsByTask(m.tasksApprovals)
	items := openTaskRecords(activeTaskRecords(m.tasksItems), stateByTask, approvalByTaskAll)
	filter := strings.TrimSpace(string(m.tasksAgentFilter))
	items = filterTasksByAgent(items, m.tasksStates, selected, filter)
	chains := chainSummaries(items, m.tasksStates, m.tasksApprovals)
	chains = filterChainsByAgent(chains, selected, filter)
	selectedChain := taskChainSummary{}
	chainIndex := m.tasksSelected
	if m.tasksChainFocused {
		chainIndex = m.tasksChainSelected
	}
	if len(chains) > 0 {
		selectedChain = chains[min(max(0, chainIndex), len(chains)-1)]
	}
	buckets := bucketTasks(items, "", stateByTask, approvalByTaskAll)
	if m.tasksChainFocused {
		buckets = selectedChain.Buckets
	}
	approvals := approvalsForTasks(m.tasksApprovals, items)
	blockers := collectTaskBlockers(items, stateByTask)
	if m.tasksChainFocused {
		blockers = selectedChain.Blockers
	}
	rowCount := len(chains)
	if m.tasksChainFocused {
		rowCount = len(orderedTaskRows(buckets))
	}
	currentTaskID := ""
	if selectedChain.CurrentTask.TaskID != "" {
		currentTaskID = selectedChain.CurrentTask.TaskID
	}
	activeChainID := ""
	activeRootID := ""
	activeCurrentTaskID := ""
	if m.tasksChainFocused {
		activeChainID = selectedChain.ChainID
		activeRootID = selectedChain.RootTaskID
		activeCurrentTaskID = currentTaskID
	}
	return taskManagementData{
		SelectedAgent: selected,
		ActiveChainID: activeChainID,
		RootTaskID:    activeRootID,
		CurrentTaskID: activeCurrentTaskID,
		SelectedIndex: min(max(0, m.tasksSelected), max(0, rowCount-1)),
		Offset:        min(max(0, m.tasksOffset), max(0, rowCount-1)),
		Buckets:       buckets,
		Counts:        countTaskBuckets(buckets),
		Blockers:      blockers,
		Approvals:     approvals,
		Tasks:         items,
		States:        m.tasksStates,
		Chains:        chains,
		SelectedChain: selectedChain,
		ChainFocused:  m.tasksChainFocused,
		AgentFilter:   filter,
		FilterAgents:  taskFilterAgents(items, m.tasksStates),
	}
}
