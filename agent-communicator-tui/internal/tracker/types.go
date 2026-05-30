package tracker

import "time"

type Agent struct {
	Name            string   `json:"name"`
	AgentID         string   `json:"agent_id"`
	UUID            string   `json:"uuid"`
	Session         string   `json:"session"`
	TmuxPane        string   `json:"tmux_pane"`
	Status          string   `json:"status"`
	WaitingApproval bool     `json:"waiting_approval"`
	AgentType       string   `json:"agent_type"`
	AgentCmd        string   `json:"agent_cmd"`
	ModelType       string   `json:"model_type"`
	Aliases         []string `json:"aliases"`
	IsThisMe        bool     `json:"is_this_me"`
	CWD             string   `json:"cwd,omitempty"`
	Scope           string   `json:"scope,omitempty"`
	Hostname        string   `json:"hostname,omitempty"`
	TargetAddress   string   `json:"target_address,omitempty"`
	TrackerID       string   `json:"tracker_id,omitempty"`
	RegistryName    string   `json:"registry_name,omitempty"`
}

type Attachment struct {
	Name        string `json:"name"`
	ContentB64  string `json:"content_b64,omitempty"`
	ContentType string `json:"content_type,omitempty"`
	Path        string `json:"path,omitempty"`
	Size        int64  `json:"size,omitempty"`
}

type Message struct {
	Sender          string       `json:"sender"`
	SenderAgentID   string       `json:"sender_agent_id,omitempty"`
	SenderTrackerID string       `json:"sender_tracker_id,omitempty"`
	SenderHostname  string       `json:"sender_hostname,omitempty"`
	SenderModelType string       `json:"sender_model_type,omitempty"`
	SenderAgentType string       `json:"sender_agent_type,omitempty"`
	SenderAgentCmd  string       `json:"sender_agent_cmd,omitempty"`
	Kind            string       `json:"kind,omitempty"`
	Timestamp       string       `json:"timestamp"`
	Body            string       `json:"message"`
	ContentType     string       `json:"content_type,omitempty"`
	Attachments     []Attachment `json:"attachments,omitempty"`
	Delivered       bool         `json:"delivered,omitempty"`
	Notified        bool         `json:"notified,omitempty"`
	Read            bool         `json:"read"`
	MessageID       string       `json:"message_id,omitempty"`
}

type Event struct {
	Seq             int64   `json:"seq"`
	Type            string  `json:"type"`
	Timestamp       float64 `json:"timestamp"`
	TargetAgentID   string  `json:"target_agent_id,omitempty"`
	TargetAgentName string  `json:"target_agent_name,omitempty"`
	Sender          string  `json:"sender,omitempty"`
	MessageID       string  `json:"message_id,omitempty"`
	HasAttachments  bool    `json:"has_attachments,omitempty"`
}

type WaitEventsResult struct {
	Events  []Event `json:"events"`
	LastSeq int64   `json:"last_seq"`
	Reset   bool    `json:"reset"`
	Gap     bool    `json:"gap"`
}

type ReadInboxResult struct {
	Mode     string    `json:"mode"`
	Messages []Message `json:"messages"`
}

type SendResult struct {
	Success bool   `json:"success,omitempty"`
	Warning string `json:"warning,omitempty"`
}

type EnsureMailboxResult struct {
	Name    string `json:"name"`
	AgentID string `json:"agent_id"`
	UUID    string `json:"uuid"`
}

type WaitOptions struct {
	Since           int64
	Timeout         time.Duration
	TargetAgentID   string
	TargetAgentName string
}

type AgentConfig struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

type RemoteTracker struct {
	TrackerID    string        `json:"tracker_id"`
	Hostname     string        `json:"hostname"`
	Address      string        `json:"address"`
	HTTPPort     int           `json:"http_port"`
	Status       string        `json:"status"`
	AgentConfigs []AgentConfig `json:"agent_configs"`
}
