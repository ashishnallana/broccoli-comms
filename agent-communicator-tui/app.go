package main

import (
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

type viewMode int

const (
	simpleView viewMode = iota
	advancedView
	savedView
)

type runtimeInfo struct {
	AppRuntime               bool
	RuntimeDir               string
	TrackerSocket            string
	TmuxSocket               string
	RemoteDirectInputEnabled bool
}

type model struct {
	width, height, selected int
	agentOffset             int
	mode                    viewMode
	rows                    []agentRow
	allRows                 []agentRow
	showSystemAgents        bool
	messages                []tracker.Message
	allMessages             []tracker.Message
	outbox                  []outboxRecord
	savedMessages           []savedMessageRecord
	savedSelected           int
	sentMessages            map[string][]tracker.Message
	unreadRows              map[string]bool
	unreadCounts            map[string]int
	hiddenAgents            map[string]bool
	agentSection            agentSection
	autoHiddenApplied       bool
	messageOffset           int
	messageSelected         int
	messageFocused          bool
	agentListStale          bool
	agentListLoading        bool
	agentListFrame          int
	composer                []rune
	inputMode               inputMode
	cursorHidden            bool
	err                     error
	eventSeq                int64
	health                  tracker.TrackerInfo
	healthErr               error
	systemEvents            []tracker.Event
	ownName                 string
	local                   localClient
	runtime                 runtimeInfo

	// Custom Agent Configurations (Ctrl-L)
	configItems       []ConfigSelectionItem
	showingConfigMenu bool
	configSelected    int

	// Prompt templates (Ctrl-O)
	prompts           []promptTemplate
	showingPromptMenu bool
	promptSelected    int

	// Command palette (Ctrl-P)
	commandPalette commandPaletteState

	// Save Agent Form (Ctrl-S)
	showingSaveForm bool
	saveFormIndex   int // 0: Name, 1: Description, 2: Command, 3: CWD, 4: Save, 5: Cancel
	saveFormInputs  []textinput.Model

	// Short footer statuses
	paneCaptureStatus    string
	directInputStatus    string
	directInputStatusErr bool
	retryOperation       string
}

func runtimeInfoFromEnv() runtimeInfo {
	info := runtimeInfo{
		RuntimeDir:    os.Getenv("BROCCOLI_COMMS_RUNTIME_DIR"),
		TrackerSocket: os.Getenv("AGENT_TRACKER_SOCKET"),
		TmuxSocket:    firstNonEmpty(os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET"), os.Getenv("AGENT_TRACKER_TMUX_SOCKET")),
	}
	info.AppRuntime = os.Getenv("BROCCOLI_COMMS_APP_RUNTIME") == "1" || info.RuntimeDir != "" || os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET") != ""
	info.RemoteDirectInputEnabled = envEnabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED") || envEnabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_SEND_ENABLED") || envEnabled("AGENT_TRACKER_REMOTE_PANE_INPUT_SEND_ENABLED")
	if info.TrackerSocket == "" && info.RuntimeDir != "" {
		info.TrackerSocket = info.RuntimeDir + "/agent-tracker.sock"
	}
	return info
}

func envEnabled(name string) bool {
	switch strings.ToLower(os.Getenv(name)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func newModel(local localClient, ownName string) model {
	return model{
		local:             local,
		ownName:           ownName,
		runtime:           runtimeInfoFromEnv(),
		sentMessages:      map[string][]tracker.Message{},
		unreadRows:        map[string]bool{},
		unreadCounts:      map[string]int{},
		hiddenAgents:      map[string]bool{},
		showingConfigMenu: false,
	}
}
func (m model) Init() tea.Cmd {
	return ensureMailboxCmd(m.local, m.ownName)
}

func initialLoadCmds(m model) tea.Cmd {
	return tea.Batch(
		loadHealth(m.local),
		loadAgents(m.local),
		loadOutboxCmd(),
		loadSavedMessagesCmd(),
		loadHiddenAgentsCmd(),
		loadPromptsCmd(),
		loadConfigItemsCmd(m.local),
		loadUnreadCounts(m.local, m.ownName),
		tickRefresh(),
		tickCursorBlink(),
		waitEvents(m.local, 0),
	)
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
	case tea.MouseMsg:
		return m.handleMouse(msg)
	case tea.KeyMsg:
		keyStart := time.Now()
		debugLogf("key start type=%v runes=%d", msg.Type, len(msg.Runes))
		defer func() {
			debugLogf("key end type=%v duration=%s composer_len=%d", msg.Type, time.Since(keyStart), len(m.composer))
		}()
		if m.commandPalette.Open {
			return m.updateCommandPalette(msg)
		}
		if m.showingSaveForm {
			return m.updateSaveForm(msg)
		}
		if m.showingPromptMenu {
			switch msg.Type {
			case tea.KeyCtrlC, tea.KeyCtrlQ:
				return m, tea.Quit
			case tea.KeyCtrlO, tea.KeyEsc:
				m.showingPromptMenu = false
				return m, nil
			case tea.KeyUp, tea.KeyCtrlP:
				if m.promptSelected > 0 {
					m.promptSelected--
				}
				return m, nil
			case tea.KeyDown, tea.KeyCtrlN:
				if m.promptSelected < len(m.prompts)-1 {
					m.promptSelected++
				}
				return m, nil
			case tea.KeyEnter:
				m.showingPromptMenu = false
				if len(m.prompts) > 0 && m.canSendCurrent() {
					return m, editPromptTemplate(m.prompts[m.promptSelected].Path)
				}
				return m, nil
			}
			return m, nil
		}
		if m.showingConfigMenu {
			switch msg.Type {
			case tea.KeyCtrlC, tea.KeyCtrlQ:
				return m, tea.Quit
			case tea.KeyCtrlR, tea.KeyEsc:
				m.showingConfigMenu = false
				return m, nil
			case tea.KeyUp, tea.KeyCtrlP:
				if m.configSelected > 0 {
					m.configSelected--
				}
				return m, nil
			case tea.KeyDown, tea.KeyCtrlN:
				if m.configSelected < len(m.configItems)-1 {
					m.configSelected++
				}
				return m, nil
			case tea.KeyEnter:
				m.showingConfigMenu = false
				if len(m.configItems) > 0 {
					item := m.configItems[m.configSelected]
					if item.IsRemote {
						return m, spinRemoteAgentCmd(m.local, item.TrackerID, item.Name)
					} else {
						localConfigs, _, err := LoadAgentConfigs()
						if err == nil {
							if cfg, exists := localConfigs[item.Name]; exists {
								return m, spinAgentCmd(cfg)
							}
						}
					}
				}
				return m, nil
			}
			return m, nil
		}
		if isCommandPaletteOpenKey(msg) {
			m.commandPalette.Open = true
			m.commandPalette.Query = nil
			m.commandPalette.Selected = 0
			return m, nil
		}
		switch msg.Type {
		case tea.KeyCtrlC, tea.KeyCtrlQ:
			return m, tea.Quit
		case tea.KeyCtrlR:
			m.showingConfigMenu = true
			m.configSelected = 0
			return m, loadConfigItemsCmd(m.local)
		case tea.KeyCtrlO:
			m.showingPromptMenu = true
			m.promptSelected = 0
			return m, loadPromptsCmd()
		case tea.KeyCtrlS:
			m.initSaveForm()
			return m, nil
		case tea.KeyCtrlT:
			m.toggleMode()
			m.selectLatestMessage()
			return m, m.reloadMessages()
		case tea.KeyCtrlX:
			if len(m.rows) > 0 && m.selected >= 0 && m.selected < len(m.rows) {
				row := m.rows[m.selected]
				targetAddress := rowTarget(row)
				m.paneCaptureStatus = fmt.Sprintf("Capturing pane snapshot for %s...", row.Name)
				return m, requestPaneCaptureCmd(targetAddress)
			}
		case tea.KeyCtrlF:
			return m, m.toggleSaveSelectedMessage()
		case tea.KeyCtrlP:
			if m.mode == savedView {
				m.selectSavedRow(-1)
				m.selectLatestMessage()
				return m, nil
			}
			if len(m.rows) > 0 {
				m.selectNextInSection(-1)
				m.scrollSelectedAgentIntoView()
				m.selectLatestMessage()
				return m, m.reloadMessages()
			}
		case tea.KeyCtrlN:
			if m.mode == savedView {
				m.selectSavedRow(1)
				m.selectLatestMessage()
				return m, nil
			}
			if len(m.rows) > 0 {
				m.selectNextInSection(1)
				m.scrollSelectedAgentIntoView()
				m.selectLatestMessage()
				return m, m.reloadMessages()
			}
		case tea.KeyTab, tea.KeyShiftTab:
			if len(m.rows) > 0 {
				m.toggleAgentSection()
				m.scrollSelectedAgentIntoView()
				m.selectLatestMessage()
				return m, m.reloadMessages()
			}
		case tea.KeyCtrlH:
			if len(m.rows) > 0 {
				cmd := m.toggleHiddenCurrentAgent()
				m.selectLatestMessage()
				return m, tea.Batch(cmd, m.reloadMessages())
			}
		case tea.KeyCtrlA:
			if m.mode != savedView && len(m.rows) > 0 {
				m.clearUnread(m.rows[m.selected])
				return m, nil
			}
		case tea.KeyUp:
			m.messageFocused = true
			if m.messageSelected > 0 {
				m.messageSelected--
				m.scrollSelectedMessageIntoView()
			}
		case tea.KeyDown:
			m.messageFocused = true
			if m.messageSelected < len(m.displayOrderedMessages())-1 {
				m.messageSelected++
				m.scrollSelectedMessageIntoView()
			}
		case tea.KeyPgUp, tea.KeyCtrlU:
			m.messageOffset = clampMessageOffset(m.messageOffset-messagePageSize(m.height), len(m.messageLinesForWidth(m.messageContentWidth())), m.messageVisibleLines())
		case tea.KeyPgDown, tea.KeyCtrlD:
			m.messageOffset = clampMessageOffset(m.messageOffset+messagePageSize(m.height), len(m.messageLinesForWidth(m.messageContentWidth())), m.messageVisibleLines())
		case tea.KeyF1:
			m.inputMode = inputModeMessage
			return m, nil
		case tea.KeyF2:
			m.inputMode = inputModeText
			return m, nil
		case tea.KeyF3:
			m.inputMode = inputModeKeys
			return m, nil
		case tea.KeyF4:
			return m, nil
		case tea.KeyEnter:
			if m.mode != savedView && m.canSendCurrent() && strings.TrimSpace(string(m.composer)) != "" {
				input := string(m.composer)
				row := m.rows[m.selected]
				action := composerActionForMode(input, m.inputMode)
				if action.Kind == "broadcast" {
					m.directInputStatus = "Broadcast mode is disabled in this milestone; no message was sent"
					m.directInputStatusErr = true
					return m, tea.Tick(4*time.Second, func(time.Time) tea.Msg { return clearDirectInputStatusTick{} })
				}
				if action.Kind == "direct_text" || action.Kind == "direct_keys" {
					m.composer = nil
					m.directInputStatus = fmt.Sprintf("Sending pane control to %s...", row.Name)
					return m, sendDirectInput(m.local, row, action, m.runtime.RemoteDirectInputEnabled)
				}
				if strings.TrimSpace(action.Body) == "" {
					return m, nil
				}
				record := makeOutboxRecord(m.ownName, row, action.Body)
				m.composer = nil
				unhideCmd := m.unhideAgent(row)
				m.clearUnread(row)
				m.appendSentMessage(row, record)
				m.refreshMergedMessages()
				m.selectLatestMessage()
				return m, tea.Batch(unhideCmd, sendOutboxRecord(m.local, m.ownName, row, record))
			}
		case tea.KeyBackspace:
			m.messageFocused = false
			if len(m.composer) > 0 {
				m.composer = m.composer[:len(m.composer)-1]
			}
		case tea.KeyCtrlW:
			m.messageFocused = false
			m.composer = deletePreviousWord(m.composer)
		case tea.KeyCtrlE:
			messages := m.displayOrderedMessages()
			if len(messages) > 0 {
				return m, openMessageInEditor(messages[m.messageSelected])
			}
		case tea.KeyRunes:
			if len(msg.Runes) == 1 && msg.Runes[0] == 'r' && len(m.composer) == 0 && m.err != nil && m.retryOperation != "" {
				return m, m.retryCurrentOperation()
			}
			if len(msg.Runes) == 1 && msg.Runes[0] == 'n' && len(m.composer) == 0 && m.mode != savedView && m.selectNextUnread() {
				m.scrollSelectedAgentIntoView()
				m.selectLatestMessage()
				return m, m.reloadMessages()
			}
			m.messageFocused = false
			m.composer = append(m.composer, msg.Runes...)
			m.messageOffset = 0
		case tea.KeySpace:
			m.messageFocused = false
			m.composer = append(m.composer, ' ')
			m.messageOffset = 0
		}
	case directInputSent:
		if msg.Err != nil {
			m.composer = []rune(msg.Original)
			m.directInputStatus = fmt.Sprintf("Pane control failed for %s: %s", msg.Row.Name, msg.Err.Error())
			m.directInputStatusErr = true
		} else {
			m.directInputStatusErr = false
			if msg.Mode == "direct_text" {
				m.directInputStatus = fmt.Sprintf("Pane text sent to %s", msg.Row.Name)
			} else {
				m.directInputStatus = fmt.Sprintf("Pane key(s) sent to %s", msg.Row.Name)
			}
		}
		return m, tea.Tick(4*time.Second, func(time.Time) tea.Msg { return clearDirectInputStatusTick{} })
	case clearDirectInputStatusTick:
		m.directInputStatus = ""
		m.directInputStatusErr = false
		return m, nil
	case paneCaptured:
		if msg.Err != nil {
			m.paneCaptureStatus = fmt.Sprintf("Failed to capture %s: %s", msg.Target, msg.Err.Error())
		} else {
			m.paneCaptureStatus = fmt.Sprintf("Pane snapshot for %s delivered successfully!", msg.Target)
		}
		return m, tea.Tick(4*time.Second, func(time.Time) tea.Msg {
			return clearPaneCaptureStatusTick{}
		})
	case clearPaneCaptureStatusTick:
		m.paneCaptureStatus = ""
		return m, nil
	case refreshTick:
		m.agentListLoading = true
		return m, tea.Batch(loadHealth(m.local), loadAgents(m.local), loadOutboxCmd(), loadUnreadCounts(m.local, m.ownName), tickRefresh(), tickAgentListSpinner())
	case cursorBlinkTick:
		m.cursorHidden = !m.cursorHidden
		return m, tickCursorBlink()
	case agentListSpinnerTick:
		if m.agentListLoading {
			m.agentListFrame++
			return m, tickAgentListSpinner()
		}
	case retryEvents:
		return m, waitEvents(m.local, m.eventSeq)
	case mailboxEnsured:
		m.err = msg.Err
		if msg.Err != nil {
			m.retryOperation = "mailbox"
			break
		}
		m.retryOperation = ""
		return m, initialLoadCmds(m)
	case healthLoaded:
		m.healthErr = msg.Err
		if msg.Err == nil {
			m.health = msg.Info
		}
	case agentsLoaded:
		m.agentListLoading = false
		m.err = msg.Err
		if msg.Err != nil {
			m.retryOperation = "agents"
			m.agentListStale = true
			break
		}
		m.retryOperation = ""
		m.agentListStale = false
		preserveKey := conversationKey(m.currentRow())
		m.allRows = filterOwnAgent(msg.Rows, m.ownName)
		m.applyAgentVisibility(preserveKey)
		if m.selected >= len(m.rows) {
			m.selected = max(0, len(m.rows)-1)
		}
		m.applyInitialHiddenForNoHistory()
		m.applyAgentVisibility(preserveKey)
		m.scrollSelectedAgentIntoView()
		if len(m.rows) > 0 {
			m.selectLatestMessage()
			return m, m.reloadMessages()
		}
		m.messages = nil
	case inboxLoaded:
		if msg.Err != nil {
			m.err = msg.Err
			m.retryOperation = "inbox"
		} else {
			m.err = nil
			m.retryOperation = ""
			m.messages = m.mergeSentMessages(m.currentRow(), msg.Messages)
			m.selectLatestMessage()
			return m, loadUnreadCounts(m.local, m.ownName)
		}
	case allInboxLoaded:
		if msg.Err != nil {
			m.err = msg.Err
			m.retryOperation = "all_inbox"
		} else {
			m.err = nil
			m.retryOperation = ""
			m.allMessages = m.mergeAllMessages(msg.Messages)
			m.selectLatestMessage()
			return m, loadUnreadCounts(m.local, m.ownName)
		}
	case messageSent:
		m.err = msg.Err
		if msg.Err != nil {
			m.composer = []rune(msg.Body)
			m.removeSentMessage(msg.Row, msg.Record.ID)
			m.refreshMergedMessages()
		} else {
			m.outbox = appendOrReplaceOutbox(m.outbox, msg.Record)
			unhideCmd := m.unhideAgent(msg.Row)
			m.clearUnread(msg.Row)
			m.appendSentMessage(msg.Row, msg.Record)
			m.refreshMergedMessages()
			m.selectLatestMessage()
			if len(m.rows) > 0 {
				return m, tea.Batch(unhideCmd, m.reloadMessages())
			}
			return m, unhideCmd
		}
	case eventsLoaded:
		if msg.Err == nil {
			m.eventSeq = msg.Result.LastSeq
			m.markUnreadFromEvents(msg.Result)
			m.applyStatusEvents(msg.Result)
			m.appendSystemEvents(msg.Result)
			cmds := []tea.Cmd{waitEvents(m.local, m.eventSeq), loadUnreadCounts(m.local, m.ownName)}
			if len(m.rows) > 0 && shouldReloadForEvents(m.ownName, m.rows[m.selected], msg.Result) {
				cmds = append(cmds, m.reloadMessages())
			}
			return m, tea.Batch(cmds...)
		}
		return m, retryWaitEvents()
	case unreadCountsLoaded:
		if msg.Err != nil {
			m.err = msg.Err
		} else {
			m.unreadCounts = msg.Counts
			if m.unreadCounts == nil {
				m.unreadCounts = map[string]int{}
			}
		}
	case promptsLoaded:
		m.err = msg.Err
		if msg.Err == nil {
			m.prompts = msg.Prompts
			if m.promptSelected >= len(m.prompts) {
				m.promptSelected = max(0, len(m.prompts)-1)
			}
		}
	case hiddenAgentsLoaded:
		if msg.Err != nil {
			m.err = msg.Err
		} else {
			m.hiddenAgents = msg.Hidden
			m.applyAgentVisibility("")
			m.scrollSelectedAgentIntoView()
		}
	case hiddenAgentsSaved:
		m.err = msg.Err
	case savedMessagesLoaded:
		if msg.Err != nil {
			m.err = msg.Err
		} else {
			m.savedMessages = msg.Records
			m.clampSavedSelected()
		}
	case savedMessagesSaved:
		m.err = msg.Err
	case outboxLoaded:
		if msg.Err != nil {
			m.err = msg.Err
		} else {
			m.outbox = msg.Records
			m.applyInitialHiddenForNoHistory()
			m.applyAgentVisibility(conversationKey(m.currentRow()))
			m.refreshMergedMessages()
		}
	case paneSwitched:
		m.err = msg.Err
	case configItemsLoaded:
		m.err = msg.Err
		if msg.Err == nil {
			m.configItems = msg.Items
			if m.configSelected >= len(m.configItems) {
				m.configSelected = max(0, len(m.configItems)-1)
			}
		}
	case editorClosed:
		m.err = msg.Err
	case promptEdited:
		m.err = msg.Err
		if msg.Err == nil && msg.Saved && m.canSendCurrent() && strings.TrimSpace(msg.Body) != "" {
			row := m.rows[m.selected]
			record := makeOutboxRecord(m.ownName, row, msg.Body)
			unhideCmd := m.unhideAgent(row)
			m.clearUnread(row)
			m.appendSentMessage(row, record)
			m.refreshMergedMessages()
			m.selectLatestMessage()
			return m, tea.Batch(unhideCmd, sendOutboxRecord(m.local, m.ownName, row, record))
		}
	case agentSaved:
		m.err = msg.Err
	case agentConfigSpun:
		m.err = msg.Err
	}
	return m, nil
}

func (m model) currentRow() agentRow {
	if len(m.rows) == 0 || m.selected < 0 || m.selected >= len(m.rows) {
		return agentRow{}
	}
	return m.rows[m.selected]
}

func (m model) canSendCurrent() bool {
	return len(m.rows) > 0 && !m.agentListStale
}

func (m model) retryCurrentOperation() tea.Cmd {
	switch m.retryOperation {
	case "mailbox":
		return ensureMailboxCmd(m.local, m.ownName)
	case "agents":
		return loadAgents(m.local)
	case "inbox":
		return m.reloadMessages()
	case "all_inbox":
		return loadAllInbox(m.local, m.ownName)
	default:
		return nil
	}
}

func (m *model) selectLatestMessage() {
	m.messageSelected = 0
	m.messageOffset = 0
}

func clampSelectedMessage(selected, count int) int {
	if count <= 0 {
		return 0
	}
	if selected >= count {
		return count - 1
	}
	return max(0, selected)
}

func (m model) mergeSentMessages(row agentRow, inbound []tracker.Message) []tracker.Message {
	merged := append([]tracker.Message{}, inbound...)
	key := conversationKey(row)
	for _, rec := range m.outbox {
		if outboxRecordMatchesRow(rec, row) {
			merged = append(merged, outboxMessage(rec, false))
		}
	}
	for _, sent := range m.sentMessages[key] {
		if !messageIDExists(merged, sent.MessageID) {
			merged = append(merged, sent)
		}
	}
	return uniqueMessagesByID(sortMessagesByTimestamp(merged))
}

func uniqueMessagesByID(messages []tracker.Message) []tracker.Message {
	seen := map[string]bool{}
	out := messages[:0]
	for _, msg := range messages {
		if msg.MessageID != "" {
			if seen[msg.MessageID] {
				continue
			}
			seen[msg.MessageID] = true
		}
		out = append(out, msg)
	}
	return out
}

func sortMessagesByTimestamp(messages []tracker.Message) []tracker.Message {
	sort.SliceStable(messages, func(i, j int) bool {
		ti, okI := parseMessageTime(messages[i].Timestamp)
		tj, okJ := parseMessageTime(messages[j].Timestamp)
		if !okI || !okJ || ti.Equal(tj) {
			return false
		}
		return ti.Before(tj)
	})
	return messages
}

func parseMessageTime(value string) (time.Time, bool) {
	if value == "" {
		return time.Time{}, false
	}
	if t, err := time.Parse(time.RFC3339Nano, value); err == nil {
		return t, true
	}
	if t, err := time.Parse(time.RFC3339, value); err == nil {
		return t, true
	}
	return time.Time{}, false
}

func (m model) inboundMessagesForCurrent() []tracker.Message {
	row := m.currentRow()
	key := conversationKey(row)
	var inbound []tracker.Message
	for _, msg := range m.messages {
		isSent := false
		for _, sent := range m.sentMessages[key] {
			if msg.MessageID != "" && msg.MessageID == sent.MessageID {
				isSent = true
				break
			}
			if msg.MessageID == sent.MessageID && msg.Timestamp == sent.Timestamp && msg.Body == sent.Body {
				isSent = true
				break
			}
		}
		if !isSent {
			inbound = append(inbound, msg)
		}
	}
	return inbound
}

func (m *model) appendSentMessage(row agentRow, rec outboxRecord) {
	if rowTarget(row) == "" || rec.ID == "" {
		return
	}
	if m.sentMessages == nil {
		m.sentMessages = map[string][]tracker.Message{}
	}
	key := conversationKey(row)
	if messageIDExists(m.sentMessages[key], rec.ID) {
		return
	}
	m.sentMessages[key] = append(m.sentMessages[key], outboxMessage(rec, false))
}

func (m *model) removeSentMessage(row agentRow, id string) {
	if id == "" || m.sentMessages == nil {
		return
	}
	key := conversationKey(row)
	kept := m.sentMessages[key][:0]
	for _, msg := range m.sentMessages[key] {
		if msg.MessageID != id {
			kept = append(kept, msg)
		}
	}
	m.sentMessages[key] = kept
}
