package main

import (
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

func (m model) handleKeyMsg(msg tea.KeyMsg) (model, tea.Cmd) {
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
		return m.handlePromptMenuKey(msg)
	}
	if m.showingConfigMenu {
		return m.handleConfigMenuKey(msg)
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
	case tea.KeyCtrlY:
		m.selectTab(-1)
		m.selectLatestMessage()
		return m, m.reloadMessages()
	case tea.KeyCtrlG:
		if len(m.rows) > 0 {
			m.toggleAgentSection()
			m.scrollSelectedAgentIntoView()
			m.selectLatestMessage()
			return m, m.reloadMessages()
		}
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
		debugLogf("KeyCtrlP matched: mode=%v rows_len=%d", m.mode, len(m.rows))
		if m.mode == swarmView {
			m.selectSwarm(-1)
			return m, loadSelectedSwarmTimeline(m.local, m.selectedSwarmName())
		}
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
		debugLogf("KeyCtrlN matched: mode=%v rows_len=%d", m.mode, len(m.rows))
		if m.mode == swarmView {
			m.selectSwarm(1)
			return m, loadSelectedSwarmTimeline(m.local, m.selectedSwarmName())
		}
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
		if m.activeTabCanCompose() && len(m.rows) > 0 {
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
		if m.activeTabCanCompose() {
			m.inputMode = inputModeMessage
		}
		return m, nil
	case tea.KeyF2:
		if m.activeTabCanCompose() {
			m.inputMode = inputModeText
		}
		return m, nil
	case tea.KeyF3:
		if m.activeTabCanCompose() {
			m.inputMode = inputModeKeys
		}
		return m, nil
	case tea.KeyF4:
		return m, nil
	case tea.KeyEnter:
		return m.handleComposerSubmit()
	case tea.KeyBackspace:
		if m.activeTabCanCompose() {
			m.messageFocused = false
			if len(m.composer) > 0 {
				m.composer = m.composer[:len(m.composer)-1]
			}
		}
	case tea.KeyCtrlW:
		if m.activeTabCanCompose() {
			m.messageFocused = false
			m.composer = deletePreviousWord(m.composer)
		}
	case tea.KeyCtrlE:
		messages := m.displayOrderedMessages()
		if len(messages) > 0 {
			return m, openMessageInEditor(messages[m.messageSelected])
		}
	case tea.KeyRunes:
		if len(msg.Runes) == 1 && msg.Runes[0] == 'r' && len(m.composer) == 0 && m.err != nil && m.retryOperation != "" {
			return m, m.retryCurrentOperation()
		}
		if len(msg.Runes) == 1 && msg.Runes[0] == 'n' && len(m.composer) == 0 && m.activeTabCanCompose() && m.selectNextUnread() {
			m.scrollSelectedAgentIntoView()
			m.selectLatestMessage()
			return m, m.reloadMessages()
		}
		if m.activeTabCanCompose() {
			m.messageFocused = false
			m.composer = append(m.composer, msg.Runes...)
			m.messageOffset = 0
		}
	case tea.KeySpace:
		if m.activeTabCanCompose() {
			m.messageFocused = false
			m.composer = append(m.composer, ' ')
			m.messageOffset = 0
		}
	}
	return m, nil
}

func (m model) handlePromptMenuKey(msg tea.KeyMsg) (model, tea.Cmd) {
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

func (m model) handleConfigMenuKey(msg tea.KeyMsg) (model, tea.Cmd) {
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

func (m model) handleComposerSubmit() (model, tea.Cmd) {
	if !m.activeTabCanCompose() {
		return m, nil
	}
	if strings.TrimSpace(string(m.composer)) != "" {
		input := string(m.composer)
		action := composerActionForMode(input, m.inputMode)
		if action.Kind == "approval_review" {
			if action.Result == "" {
				m.err = fmt.Errorf("/approval requires good|bad|need_improvements")
				return m, nil
			}
			approvalID := action.ApprovalID
			selected, hasSelected := selectedApprovalMessage(m)
			if approvalID == "" && hasSelected {
				approvalID = selected.ApprovalID
			}
			if approvalID == "" {
				m.err = fmt.Errorf("approval id is required")
				return m, nil
			}
			m.composer = nil
			return m, approvalReviewCmd(approvalMessageForReview(approvalID, selected), action.Result)
		}
		row, ok := m.currentSendTarget()
		if !ok || m.agentListStale {
			return m, nil
		}
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
		if m.mode == swarmView {
			record.SwarmContext = m.selectedSwarmName()
		}
		m.composer = nil
		unhideCmd := m.unhideAgent(row)
		m.clearUnread(row)
		m.appendSentMessage(row, record)
		m.refreshMergedMessages()
		m.selectLatestMessage()
		return m, tea.Batch(unhideCmd, sendOutboxRecord(m.local, m.ownName, row, record))
	}
	return m, nil
}
