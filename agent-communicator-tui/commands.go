package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type localClient interface {
	EnsureMailbox(context.Context, string) (tracker.EnsureMailboxResult, error)
	TrackerInfo(context.Context) (tracker.TrackerInfo, error)
	List(context.Context) (map[string]tracker.Agent, error)
	ReadInbox(context.Context, string, int, bool) (tracker.ReadInboxResult, error)
	ReadInboxForSender(context.Context, string, int, bool, string, string, string) (tracker.ReadInboxResult, error)
	GetUnreadCounts(context.Context, string) (tracker.UnreadCountsResult, error)
	SendMessage(context.Context, string, string, []tracker.Attachment) error
	SendMessageFrom(context.Context, string, string, string, []tracker.Attachment) error
	SendText(context.Context, string, string, bool) error
	SendKeys(context.Context, string, []string) error
	WaitEvents(context.Context, tracker.WaitOptions) (tracker.WaitEventsResult, error)
	ListTrackers(context.Context) ([]tracker.RemoteTracker, error)
	PublishTrackerEvent(ctx context.Context, targetTrackerID, eventType string, payload any) error
}

type messageIDSender interface {
	SendMessageWithID(context.Context, string, string, string, string, []tracker.Attachment) error
}

type agentRow struct{ Name, Scope, Status, CWD, TargetAddress, Hostname, AgentName, TmuxPane, AgentCmd, AgentID, TrackerID, RegistryName, ModelType string }
type mailboxEnsured struct{ Err error }

type agentsLoaded struct {
	Rows []agentRow
	Err  error
}
type healthLoaded struct {
	Info tracker.TrackerInfo
	Err  error
}
type inboxLoaded struct {
	Messages []tracker.Message
	Err      error
}
type allInboxLoaded struct {
	Messages []tracker.Message
	Err      error
}
type unreadCountsLoaded struct {
	Counts map[string]int
	Err    error
}
type messageSent struct {
	Body   string
	Row    agentRow
	Record outboxRecord
	Err    error
}
type directInputSent struct {
	Original string
	Row      agentRow
	Mode     string
	Err      error
}
type eventsLoaded struct {
	Result tracker.WaitEventsResult
	Err    error
}
type refreshTick struct{}
type retryEvents struct{}
type agentListSpinnerTick struct{}
type clearDirectInputStatusTick struct{}

type promptTemplate struct {
	Name string
	Path string
}

type promptsLoaded struct {
	Prompts []promptTemplate
	Err     error
}

type promptEdited struct {
	Body  string
	Saved bool
	Err   error
}

func promptDirectory() string {
	if xdg := os.Getenv("XDG_CONFIG_HOME"); xdg != "" {
		return filepath.Join(xdg, "agent-communicator", "prompts")
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return filepath.Join(".", "prompts")
	}
	return filepath.Join(home, ".config", "agent-communicator", "prompts")
}

func loadPromptsCmd() tea.Cmd {
	return func() tea.Msg {
		prompts, err := loadPromptTemplates(promptDirectory())
		return promptsLoaded{Prompts: prompts, Err: err}
	}
}

func loadPromptTemplates(dir string) ([]promptTemplate, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	prompts := []promptTemplate{}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".md" {
			continue
		}
		name := strings.TrimSuffix(entry.Name(), ".md")
		prompts = append(prompts, promptTemplate{Name: name, Path: filepath.Join(dir, entry.Name())})
	}
	sort.Slice(prompts, func(i, j int) bool { return prompts[i].Name < prompts[j].Name })
	return prompts, nil
}

func ensureMailboxCmd(local localClient, ownName string) tea.Cmd {
	return func() tea.Msg {
		if local == nil || strings.TrimSpace(ownName) == "" {
			return mailboxEnsured{}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_, err := local.EnsureMailbox(ctx, ownName)
		return mailboxEnsured{Err: err}
	}
}

func loadInbox(local localClient, inboxOwner string, row agentRow) tea.Cmd {
	return func() tea.Msg {
		if local == nil || row.Name == "" {
			return inboxLoaded{}
		}
		owner := inboxOwner
		if owner == "" && row.Scope == "local" {
			owner = row.Name
		}
		if owner == "" {
			return inboxLoaded{}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		senderAgentID, senderTrackerID, senderName := rowInboxFilters(row)
		inbox, err := local.ReadInboxForSender(ctx, owner, simpleInboxFetchLimit, false, senderAgentID, senderTrackerID, senderName)
		return inboxLoaded{Messages: filterConversation(inbox.Messages, row), Err: err}
	}
}

func loadAllInbox(local localClient, inboxOwner string) tea.Cmd {
	return func() tea.Msg {
		if local == nil || inboxOwner == "" {
			return allInboxLoaded{}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		inbox, err := local.ReadInbox(ctx, inboxOwner, advancedInboxFetchLimit, false)
		return allInboxLoaded{Messages: inbox.Messages, Err: err}
	}
}

func loadUnreadCounts(local localClient, inboxOwner string) tea.Cmd {
	return func() tea.Msg {
		if local == nil || strings.TrimSpace(inboxOwner) == "" {
			return unreadCountsLoaded{}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		result, err := local.GetUnreadCounts(ctx, inboxOwner)
		return unreadCountsLoaded{Counts: result.Counts, Err: err}
	}
}

func rowInboxFilters(row agentRow) (senderAgentID, senderTrackerID, senderName string) {
	if row.AgentID != "" {
		senderAgentID = row.AgentID
		senderTrackerID = row.TrackerID
		return senderAgentID, senderTrackerID, ""
	}
	if row.Scope == "remote" {
		return "", "", ""
	}
	return "", "", fallback(row.AgentName, row.Name)
}

func filterConversation(messages []tracker.Message, row agentRow) []tracker.Message {
	if row.Name == "" {
		return messages
	}
	filtered := []tracker.Message{}
	for _, msg := range messages {
		if messageMatchesRow(msg, row) {
			filtered = append(filtered, msg)
		}
	}
	return filtered
}

func senderMatchesRow(sender string, row agentRow) bool {
	if sender == row.Name || strings.HasPrefix(sender, row.Name+" ") {
		return true
	}
	if row.Scope == "remote" {
		agentName, hostname := row.AgentName, row.Hostname
		address := rowTarget(row)
		if agentName == "" && strings.Contains(address, "/") {
			parts := strings.SplitN(address, "/", 2)
			hostname, agentName = parts[0], parts[1]
		}
		return agentName != "" && hostname != "" && strings.HasPrefix(sender, agentName+" ") && strings.Contains(sender, "(via "+hostname+")")
	}
	return false
}

func filterOwnAgent(rows []agentRow, ownName string) []agentRow {
	if ownName == "" {
		return rows
	}
	filtered := rows[:0]
	for _, row := range rows {
		if row.Name != ownName {
			filtered = append(filtered, row)
		}
	}
	return filtered
}

func deletePreviousWord(value []rune) []rune {
	end := len(value)
	for end > 0 && value[end-1] == ' ' {
		end--
	}
	start := end
	for start > 0 && value[start-1] != ' ' {
		start--
	}
	return value[:start]
}

const markdownReplyInstruction = "PS: Reply in markdown format."

type composerAction struct {
	Kind     string
	Body     string
	Text     string
	Submit   bool
	Keys     []string
	Original string
}

func parseComposerAction(input string) composerAction {
	trimmed := strings.TrimSpace(input)
	action := composerAction{Kind: "message", Body: input, Submit: true, Original: input}
	if trimmed == "" {
		return action
	}
	if trimmed == "/msg" {
		action.Body = ""
		return action
	}
	if strings.HasPrefix(trimmed, "/msg ") {
		action.Body = strings.TrimSpace(strings.TrimPrefix(trimmed, "/msg"))
		return action
	}
	if trimmed == "/text" {
		return composerAction{Kind: "direct_text", Submit: true, Original: input}
	}
	if strings.HasPrefix(trimmed, "/text ") {
		rest := strings.TrimSpace(strings.TrimPrefix(trimmed, "/text"))
		submit := true
		if rest == "--no-submit" {
			rest = ""
			submit = false
		} else if strings.HasPrefix(rest, "--no-submit ") {
			rest = strings.TrimSpace(strings.TrimPrefix(rest, "--no-submit"))
			submit = false
		}
		return composerAction{Kind: "direct_text", Text: rest, Submit: submit, Original: input}
	}
	if trimmed == "/key" || trimmed == "/keys" {
		return composerAction{Kind: "direct_keys", Original: input}
	}
	if strings.HasPrefix(trimmed, "/key ") {
		rest := strings.TrimSpace(strings.TrimPrefix(trimmed, "/key"))
		return composerAction{Kind: "direct_keys", Keys: strings.Fields(rest), Original: input}
	}
	if strings.HasPrefix(trimmed, "/keys ") {
		rest := strings.TrimSpace(strings.TrimPrefix(trimmed, "/keys"))
		return composerAction{Kind: "direct_keys", Keys: strings.Fields(rest), Original: input}
	}
	if trimmed == "/broadcast" {
		return composerAction{Kind: "broadcast", Original: input}
	}
	if strings.HasPrefix(trimmed, "/broadcast ") {
		rest := strings.TrimSpace(strings.TrimPrefix(trimmed, "/broadcast"))
		return composerAction{Kind: "broadcast", Body: rest, Original: input}
	}
	return action
}

func sendCurrentMessage(local localClient, senderName string, row agentRow, body string) tea.Cmd {
	return sendOutboxRecord(local, senderName, row, makeOutboxRecord(senderName, row, body))
}

func sendOutboxRecord(local localClient, senderName string, row agentRow, record outboxRecord) tea.Cmd {
	return func() tea.Msg {
		if local == nil {
			return messageSent{Body: record.Body, Row: row, Record: record, Err: errors.New("local tracker client unavailable")}
		}
		target := rowTarget(row)
		if strings.TrimSpace(record.Body) == "" || target == "" {
			return messageSent{Body: record.Body, Row: row, Record: record}
		}
		deliveryBody := messageBodyForDelivery(record.Body)
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		var err error
		if withID, ok := local.(messageIDSender); ok {
			err = withID.SendMessageWithID(ctx, senderName, target, deliveryBody, record.ID, nil)
		} else if senderName != "" {
			err = local.SendMessageFrom(ctx, senderName, target, deliveryBody, nil)
		} else {
			err = local.SendMessage(ctx, target, deliveryBody, nil)
		}
		if err == nil {
			err = appendOutbox(record)
		}
		return messageSent{Body: record.Body, Row: row, Record: record, Err: err}
	}
}

func sendDirectInput(local localClient, row agentRow, action composerAction, allowRemote bool) tea.Cmd {
	return func() tea.Msg {
		if local == nil {
			return directInputSent{Original: action.Original, Row: row, Mode: action.Kind, Err: errors.New("local tracker client unavailable")}
		}
		if row.Scope == "remote" && !allowRemote {
			return directInputSent{Original: action.Original, Row: row, Mode: action.Kind, Err: errors.New("remote direct pane input is disabled")}
		}
		target := rowTarget(row)
		if target == "" {
			return directInputSent{Original: action.Original, Row: row, Mode: action.Kind, Err: errors.New("target agent unavailable")}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		var err error
		switch action.Kind {
		case "direct_text":
			if action.Text == "" {
				err = errors.New("/text requires TEXT")
			} else {
				err = local.SendText(ctx, target, action.Text, action.Submit)
			}
		case "direct_keys":
			if len(action.Keys) == 0 {
				err = errors.New("/key requires KEY [KEY...]")
			} else {
				err = local.SendKeys(ctx, target, action.Keys)
			}
		default:
			err = errors.New("unknown direct input command")
		}
		return directInputSent{Original: action.Original, Row: row, Mode: action.Kind, Err: err}
	}
}

func messageBodyForDelivery(body string) string {
	return strings.TrimRight(body, " \t\r\n") + "\n\n(" + markdownReplyInstruction + ")"
}

func waitEvents(local localClient, since int64) tea.Cmd {
	return func() tea.Msg {
		if local == nil {
			return eventsLoaded{}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 35*time.Second)
		defer cancel()
		result, err := local.WaitEvents(ctx, tracker.WaitOptions{Since: since, Timeout: 25 * time.Second})
		return eventsLoaded{Result: result, Err: err}
	}
}

func shouldReloadForEvents(ownName string, row agentRow, result tracker.WaitEventsResult) bool {
	if row.Name == "" {
		return false
	}
	if ownName == "" && row.Scope != "local" {
		return false
	}
	if result.Reset || result.Gap {
		return true
	}
	targetName := row.Name
	if ownName != "" {
		targetName = ownName
	}
	for _, event := range result.Events {
		if event.TargetAgentName == targetName {
			return true
		}
	}
	return false
}

func tickRefresh() tea.Cmd {
	return tea.Tick(refreshInterval, func(time.Time) tea.Msg { return refreshTick{} })
}
func tickAgentListSpinner() tea.Cmd {
	return tea.Tick(150*time.Millisecond, func(time.Time) tea.Msg { return agentListSpinnerTick{} })
}
func retryWaitEvents() tea.Cmd {
	return tea.Tick(2*time.Second, func(time.Time) tea.Msg { return retryEvents{} })
}
func rowTarget(row agentRow) string {
	if row.TargetAddress != "" {
		return row.TargetAddress
	}
	return row.Name
}
func shortHost(hostname string) string {
	if len([]rune(hostname)) <= 5 {
		return hostname
	}
	return string([]rune(hostname)[:5])
}
func fallback(v, d string) string {
	if v == "" {
		return d
	}
	return v
}

type agentConfigSpun struct {
	Name string
	Err  error
}

func spinAgentCmd(cfg AgentConfig) tea.Cmd {
	return func() tea.Msg {
		dir := cfg.Directory
		if dir == "" {
			if d, err := os.Getwd(); err == nil {
				dir = d
			} else {
				dir = "."
			}
		}

		args := append([]string{"spin", dir, cfg.AgentCommand}, cfg.AgentArgs...)
		cmd := exec.Command("agent-tracker-ctl", args...)
		err := cmd.Run()
		return agentConfigSpun{Name: cfg.Name, Err: err}
	}
}

type ConfigSelectionItem struct {
	Name        string
	Description string
	IsRemote    bool
	TrackerID   string
	Hostname    string
}

type configItemsLoaded struct {
	Items []ConfigSelectionItem
	Err   error
}

func loadConfigItemsCmd(local localClient) tea.Cmd {
	return func() tea.Msg {
		var items []ConfigSelectionItem

		// 1. Load Local custom configurations
		localConfigs, localKeys, err := LoadAgentConfigs()
		if err == nil {
			for _, key := range localKeys {
				cfg := localConfigs[key]
				items = append(items, ConfigSelectionItem{
					Name:        cfg.Name,
					Description: cfg.Description,
					IsRemote:    false,
				})
			}
		}

		// 2. Fetch Remote Configurations from Registry
		if local != nil {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			trackers, err := local.ListTrackers(ctx)
			if err == nil {
				ownTrackerID := os.Getenv("AGENT_TRACKER_ID")
				ownHostname := os.Getenv("AGENT_TRACKER_HOSTNAME")
				if ownHostname == "" {
					ownHostname, _ = os.Hostname()
				}
				for _, t := range trackers {
					if t.TrackerID == ownTrackerID || t.Hostname == ownHostname {
						continue // Skip local tracker remote configs
					}
					for _, cfg := range t.AgentConfigs {
						items = append(items, ConfigSelectionItem{
							Name:        cfg.Name,
							Description: cfg.Description,
							IsRemote:    true,
							TrackerID:   t.TrackerID,
							Hostname:    t.Hostname,
						})
					}
				}
			}
		}

		return configItemsLoaded{Items: items, Err: err}
	}
}

func spinRemoteAgentCmd(local localClient, targetTrackerID, configName string) tea.Cmd {
	return func() tea.Msg {
		if local == nil {
			return agentConfigSpun{Name: configName, Err: errors.New("local client unavailable")}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		payload := map[string]any{
			"config_name": configName,
		}

		err := local.PublishTrackerEvent(ctx, targetTrackerID, "spin_request", payload)
		return agentConfigSpun{Name: configName, Err: err}
	}
}

type paneCaptured struct {
	Target string
	Err    error
}

type clearPaneCaptureStatusTick struct{}

func requestPaneCaptureCmd(targetAddress string) tea.Cmd {
	return func() tea.Msg {
		args := []string{"send-pane", "agent-communicator", "--source", targetAddress, "--note", "Requested from agent-communicator"}
		cmd := exec.Command("agent-tracker-ctl", args...)
		out, err := cmd.CombinedOutput()
		if err != nil {
			return paneCaptured{Target: targetAddress, Err: fmt.Errorf("%s: %s", err, string(out))}
		}
		return paneCaptured{Target: targetAddress}
	}
}
