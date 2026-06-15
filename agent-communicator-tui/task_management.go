package main

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
}

func (m model) taskData() taskManagementData {
	selected := m.currentRow()
	stateByTask := latestStateByTask(m.tasksStates)
	approvalByTaskAll := approvalsByTask(m.tasksApprovals)
	items := openTaskRecords(activeTaskRecords(m.tasksItems), stateByTask, approvalByTaskAll)
	chainID, rootID, currentTaskID := taskFocusFromSelection(items, m.tasksSelected)
	approvals := approvalsForTasks(m.tasksApprovals, items)
	approvalByTask := approvalsByTask(approvals)
	buckets := bucketTasks(items, currentTaskID, stateByTask, approvalByTask)
	rowCount := len(orderedTaskRows(buckets))
	return taskManagementData{
		SelectedAgent: selected,
		ActiveChainID: chainID,
		RootTaskID:    rootID,
		CurrentTaskID: currentTaskID,
		SelectedIndex: min(max(0, m.tasksSelected), max(0, rowCount-1)),
		Offset:        min(max(0, m.tasksOffset), max(0, rowCount-1)),
		Buckets:       buckets,
		Counts:        countTaskBuckets(buckets),
		Blockers:      collectTaskBlockers(items, stateByTask),
		Approvals:     approvals,
		Tasks:         items,
		States:        m.tasksStates,
	}
}
