package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var composerBoxStyle = lipgloss.NewStyle().Border(lipgloss.NormalBorder()).BorderForeground(palette.Surface0).Padding(0, 1)
var panelBoxStyle = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(palette.Surface0).Padding(0, 1)
var mobileComposerBoxStyle = lipgloss.NewStyle().Border(lipgloss.Border{Top: "─"}).BorderTop(true).BorderForeground(palette.Surface0).Padding(0, 0)

const composerMaxLines = 5

func (m model) View() string {
	defer debugSince("view", time.Now())
	if m.width == 0 {
		return "loading..."
	}
	footer := m.footer(m.width)
	bodyH := max(3, m.height-lineCount(footer))

	if m.showingSaveForm {
		return m.renderSaveForm() + "\n" + footer
	}
	if m.showingPromptMenu {
		return m.renderPromptMenu(m.width, bodyH) + "\n" + footer
	}
	if m.showingConfigMenu {
		return m.renderConfigMenu(m.width, bodyH) + "\n" + footer
	}

	// Adaptive Mobile/Narrow View
	if m.width < 70 {
		return m.conversationPanel(m.width, bodyH) + "\n" + footer
	}

	leftW, midW, rightW := m.layoutWidths()
	_ = rightW
	left := box(m.sidebarView(panelInnerWidth(leftW), panelInnerHeight(bodyH)), leftW, bodyH)
	mid := m.conversationPanel(midW, bodyH)
	return lipgloss.JoinHorizontal(lipgloss.Top, left, mid) + "\n" + footer
}

func (m model) layoutWidths() (int, int, int) {
	left := max(12, (m.width*30)/100)
	if m.width < 40 {
		left = max(10, m.width/3)
	}
	mid := max(10, m.width-left)
	return left, mid, 0
}

func (m model) sidebarView(width, height int) string {
	if m.mode == savedView {
		body := shellTitleStyle.Render("Agent Communicator") + "\n" + sectionHeaderStyle.Render("Saved") + "\n" + m.savedAgentList(width, max(1, height-2))
		return truncateLines(body, height)
	}
	title := shellTitleStyle.Render("Agent Communicator")
	device := mutedStyle.Render("This device: " + localHostname())
	total, hidden := len(m.rows), m.hiddenCount()
	header := fmt.Sprintf("Agents %d", total)
	if hidden > 0 {
		header = fmt.Sprintf("Agents %d · Hidden %d", total, hidden)
	}
	body := title + "\n" + device + "\n" + sectionHeaderStyle.Render(header) + "\n" + m.agentList(width, max(1, height-3))
	return truncateLines(body, height)
}

func (m model) conversationPanel(width, height int) string {
	defer debugSince("conversation_panel", time.Now())
	innerW := panelInnerWidth(width)
	innerH := panelInnerHeight(height)
	titleText := m.conversationTitle()

	if width < 70 { // Mobile / Narrow view header overrides
		innerW = max(1, width-2)
		innerH = max(1, height)
		viewName := "Chat"
		if m.mode == advancedView {
			viewName = "Advanced Chat"
		} else if m.mode == savedView {
			viewName = "Saved Messages"
		}

		if m.mode == savedView {
			titleText = fmt.Sprintf("View: %s", viewName)
		} else if len(m.rows) > 0 && m.selected >= 0 && m.selected < len(m.rows) {
			row := m.rows[m.selected]
			titleText = fmt.Sprintf("View: %s\nAgent: %s", viewName, row.Name)
		} else {
			titleText = fmt.Sprintf("View: %s\nAgent: None", viewName)
		}
	}

	title := titleStyle.Render(titleText)
	composer := m.composerBox(innerW)
	if m.mode == savedView {
		composer = mutedStyle.Render("c-f unsave selected · c-n/p saved entry")
	}
	messageH := max(1, innerH-lineCount(title)-lineCount(composer)-2)
	if width < 70 {
		messageH = max(1, innerH-lineCount(title)-lineCount(composer))
	}
	body := title + "\n" + m.messageViewWithHeight(innerW, messageH) + "\n" + composer

	if width < 70 {
		return lipgloss.NewStyle().
			Width(width).
			Height(height).
			MaxWidth(width).
			MaxHeight(height).
			Padding(0, 1).
			Render(body)
	}
	return box(body, width, height)
}

func (m model) conversationTitle() string {
	if m.mode == savedView {
		return "Saved Messages ⭐"
	}
	label := "Conversation"
	if m.mode == advancedView {
		label = "Advanced Conversation"
	}
	row := m.currentRow()
	if row.Name == "" {
		return label + " · no agent selected"
	}
	view := m.agentView(row)
	parts := []string{label, statusDot(view.Status), view.ModelBadge, view.Name}
	if machine := view.MachineLabel; machine != "" {
		parts = append(parts, "@ "+machine)
	}
	return strings.Join(parts, " ")
}

func (m model) composerBox(width int) string {
	if m.width < 70 {
		return mobileComposerBoxStyle.Width(width).MaxWidth(width).Render(m.composerView(width))
	}
	inner := max(1, width-4)
	return composerBoxStyle.Width(inner).MaxWidth(max(1, width)).Render(m.composerView(inner))
}

func (m model) footer(width int) string {
	directScope := "local only"
	if m.runtime.RemoteDirectInputEnabled {
		directScope = "local+remote enabled"
	}
	status := m.runtimeStatusLine()
	if status == "" {
		status = fmt.Sprintf("rpc · local · agents %d", len(m.rows))
	}
	lines := []string{
		statusBarStyle.Render(status),
		"c-t view · tab section · c-n/p agent · F1-F4 input · c-a read · c-o prompts · c-h hide · c-f save · c-s save agent",
		fmt.Sprintf("↑/↓ select msg · c-u/d scroll · c-e open · c-r config · enter send · /msg message · /text /key pane control (%s) · /broadcast disabled · c-q quit · c-x debug capture", directScope),
	}
	if m.paneCaptureStatus != "" {
		lines = append([]string{m.paneCaptureStatus}, lines...)
	} else if m.directInputStatus != "" {
		statusLine := m.directInputStatus
		if m.directInputStatusErr {
			statusLine = errorBarStyle.Render(statusLine)
		}
		lines = append([]string{statusLine}, lines...)
	}
	if m.err != nil {
		lines = append(lines, errorBarStyle.Render(m.errorStatusLine()))
	}
	for i, text := range lines {
		if lipgloss.Width(text) > width {
			lines[i] = truncateCells(text, max(1, width-1)) + "…"
		}
	}
	return mutedStyle.Render(strings.Join(lines, "\n"))
}

func (m model) errorStatusLine() string {
	text := "error · " + m.err.Error()
	if rpcErr, ok := m.err.(*tracker.RPCError); ok && rpcErr.Data != nil {
		parts := []string{"error"}
		if rpcErr.Data.Operation != "" {
			parts = append(parts, rpcErr.Data.Operation)
		}
		if rpcErr.Data.Agent != "" {
			parts = append(parts, rpcErr.Data.Agent)
		}
		parts = append(parts, rpcErr.Message)
		text = strings.Join(parts, " · ")
	}
	if m.retryOperation != "" {
		text += " · r retry"
	}
	return text
}

func (m model) runtimeStatusLine() string {
	state := "rpc ok"
	if m.agentListLoading {
		state = "rpc refreshing"
	}
	if m.healthErr != nil || m.agentListStale || m.err != nil {
		state = "rpc degraded"
	}
	if m.health.Status != "" && m.health.Status != "ok" && state == "rpc ok" {
		state = "rpc " + m.health.Status
	}
	row := m.currentRow()
	active := "no agent"
	if row.Name != "" {
		activeParts := []string{row.Name}
		if badge := modelBadge(row); badge != "??" {
			activeParts = append(activeParts, badge)
		}
		if machine := rowMachineLabel(row); machine != "" {
			activeParts = append(activeParts, "@ "+machine)
		}
		active = strings.Join(activeParts, " ")
	}
	online, total := m.health.OnlineAgentCount, m.health.AgentCount
	if total == 0 && len(m.rows) > 0 {
		total = len(m.rows)
		online = countOnlineRows(m.rows)
	}
	registry := "registry unknown"
	if m.health.RegistryConnected != nil {
		if *m.health.RegistryConnected {
			registry = "registry online"
		} else {
			registry = "registry offline"
		}
	}
	details := []string{state, "active " + active, fmt.Sprintf("online %d/%d", online, total), registry}
	if m.health.RemoteTrackerCount > 0 {
		details = append(details, fmt.Sprintf("trackers %d/%d", m.health.OnlineRemoteTrackerCount, m.health.RemoteTrackerCount))
	}
	details = append(details, time.Now().In(displayLocation).Format("15:04"))
	if m.runtime.AppRuntime {
		details = append([]string{"Broccoli Comms runtime"}, details...)
	}
	if m.runtime.TrackerSocket != "" {
		details = append(details, "socket "+filepath.Base(m.runtime.TrackerSocket))
	}
	return strings.Join(details, " · ")
}

func countOnlineRows(rows []agentRow) int {
	count := 0
	for _, row := range rows {
		switch strings.ToLower(strings.TrimSpace(row.Status)) {
		case "running", "active", "online", "idle", "ready":
			count++
		}
	}
	return count
}

func (m model) agentListTitle() string {
	title := "Agents"
	if m.mode == savedView {
		title = "Saved"
	}
	if m.agentListLoading {
		frames := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
		title += " " + mutedStyle.Render(frames[m.agentListFrame%len(frames)])
	}
	return titleStyle.Render(title)
}

func (m model) agentCard(row agentRow, selected bool, width int) string {
	cardWidth := max(8, width)
	hidden := m.isHiddenAgent(row)
	inner := max(4, cardWidth-4)
	view := m.agentView(row)
	unread := ""
	if view.UnreadCount > 0 {
		unread = " " + unreadCountBadge(view.UnreadCount)
	}
	prefix := statusDot(view.Status) + " "
	nameBudget := max(1, inner-lipgloss.Width(prefix)-lipgloss.Width(unread))
	nameText := agentStyle(row.Name, true).Render(truncateCells(row.Name, nameBudget))
	nameLine := prefix + nameText + unread
	if lipgloss.Width(nameLine) > inner {
		nameLine = truncateCells(statusDot(view.Status)+" "+view.Name, inner)
	}
	statusLine := strings.Join(nonEmpty([]string{view.ModelBadge, view.StatusLabel, view.RegistryLabel}), " · ")
	hostLine := strings.TrimSpace("host " + view.HostnameLabel)
	lines := nameLine + "\n" + mutedStyle.Render(truncateCells(statusLine, inner)) + "\n" + mutedStyle.Render(truncateCells(hostLine, inner))
	border := lipgloss.RoundedBorder()
	if selected {
		border = lipgloss.DoubleBorder()
	}
	borderColor := palette.AgentColors[agentColorIndex(row.Name)]
	if hidden {
		borderColor = palette.Overlay0
	}
	style := lipgloss.NewStyle().Width(cardWidth-2).Border(border).BorderForeground(borderColor).Padding(0, 1)
	if selected {
		style = style.Background(palette.Surface0).Foreground(palette.Text).Bold(true)
	}
	return style.Render(lines)
}

func (m model) hiddenSeparator(width int) string {
	hidden := max(0, len(m.rows)-m.hiddenStartIndex())
	text := fmt.Sprintf(" hidden / Filtered %d ", hidden)
	lineWidth := max(0, width-lipgloss.Width(text)-2)
	return mutedStyle.Render(strings.Repeat("─", lineWidth/2) + text + strings.Repeat("─", lineWidth-lineWidth/2))
}

func compactCWD(cwd string) string {
	cwd = strings.TrimSpace(cwd)
	if cwd == "" || cwd == "unknown" || cwd == "unavailable" {
		return ""
	}
	cleaned := filepath.Clean(cwd)
	if cleaned == "." || cleaned == string(filepath.Separator) {
		return cleaned
	}
	parts := strings.FieldsFunc(cleaned, func(r rune) bool { return r == '/' || r == '\\' })
	kept := make([]string, 0, len(parts))
	for _, part := range parts {
		if part != "" {
			kept = append(kept, part)
		}
	}
	if len(kept) == 0 {
		return cleaned
	}
	if len(kept) > 2 {
		kept = kept[len(kept)-2:]
	}
	return strings.Join(kept, "/")
}

func (m model) agentList(width, height int) string {
	if m.mode == savedView {
		return m.savedAgentList(width, height)
	}
	if len(m.rows) == 0 {
		return mutedStyle.Render("no agents")
	}
	visible := max(1, height/agentCardHeight)
	offset := min(max(0, m.agentOffset), max(0, len(m.rows)-visible))
	end := min(len(m.rows), offset+visible)
	hiddenStart := m.hiddenStartIndex()
	var b strings.Builder
	lastGroup := ""
	for i := offset; i < end; i++ {
		if i == hiddenStart && hiddenStart > 0 {
			if b.Len() > 0 {
				b.WriteString("\n")
			}
			b.WriteString(m.hiddenSeparator(width) + "\n")
			lastGroup = ""
		}
		group := m.agentView(m.rows[i]).GroupHeader
		if group != "" && group != lastGroup {
			if b.Len() > 0 && !strings.HasSuffix(b.String(), "\n") {
				b.WriteString("\n")
			}
			b.WriteString(sectionHeaderStyle.Render(truncateCells(group, max(1, width-1))) + "\n")
			lastGroup = group
		}
		b.WriteString(m.agentCard(m.rows[i], i == m.selected, width-2))
		if i < end-1 {
			b.WriteString("\n")
		}
	}
	if end < len(m.rows) {
		b.WriteString("\n" + mutedStyle.Render("…"))
	}
	return truncateLines(b.String(), height)
}

func (m model) savedAgentList(width, height int) string {
	rows := m.savedRows()
	if len(rows) == 0 {
		return mutedStyle.Render("no saved messages")
	}
	visible := max(1, height/agentCardHeight)
	offset := min(max(0, m.agentOffset), max(0, len(rows)-visible))
	end := min(len(rows), offset+visible)
	var b strings.Builder
	for i := offset; i < end; i++ {
		b.WriteString(m.savedCard(rows[i], i == m.savedSelected, width-2))
		if i < end-1 {
			b.WriteString("\n")
		}
	}
	return truncateLines(b.String(), height)
}

func (m model) savedCard(row agentRow, selected bool, width int) string {
	count := 0
	for _, rec := range m.savedMessages {
		if fallback(rec.AgentName, rec.ConversationKey) == row.Name {
			count++
		}
	}
	copy := row
	copy.Scope = fmt.Sprintf("saved · %d", count)
	return m.agentCard(copy, selected, width)
}

func (m model) messageView(width int) string {
	return m.messageViewWithHeight(width, m.messageVisibleLines())
}

func (m model) messageViewWithHeight(width, visible int) string {
	defer debugSince("message_view", time.Now())
	lines := m.messageLinesForWidth(width)
	visible = max(1, visible)
	if len(lines) == 0 {
		return ""
	}
	offset := clampMessageOffset(m.messageOffset, len(lines), visible)
	end := min(len(lines), offset+visible)
	return lipgloss.NewStyle().Width(max(1, width)).Height(visible).MaxHeight(visible).Render(strings.Join(lines[offset:end], "\n"))
}

func (m model) messageLinesForWidth(width int) []string {
	start := time.Now()
	wrapWidth := max(10, width-1)
	messages := m.displayOrderedMessages()
	defer func() {
		debugLogf("message_lines duration=%s messages=%d width=%d", time.Since(start), len(messages), width)
	}()
	systemEvents := m.displayOrderedSystemEvents()
	if len(messages) == 0 && len(systemEvents) == 0 {
		if len(m.rows) > 0 && m.rows[m.selected].Scope == "remote" {
			return wrapLine(mutedStyle.Render("No messages. Remote history is in-memory for sent messages only."), wrapWidth)
		}
		return wrapLine(mutedStyle.Render("No messages. Inbox history loads for local agents."), wrapWidth)
	}
	cacheKey := messageRenderCacheKey(m, messages, systemEvents, wrapWidth)
	if lines, ok := cachedMessageLines(cacheKey); ok {
		debugLogf("message_lines cache=hit messages=%d width=%d", len(messages), width)
		return lines
	}
	debugLogf("message_lines cache=miss messages=%d width=%d", len(messages), width)
	lines := []string{}
	for i, msg := range messages {
		if len(lines) > 0 {
			lines = append(lines, "")
		}
		lines = append(lines, m.messageBubbleLines(msg, i, wrapWidth)...)
	}
	for _, event := range systemEvents {
		if len(lines) > 0 {
			lines = append(lines, "")
		}
		lines = append(lines, m.systemEventLine(event, wrapWidth))
	}
	storeMessageLines(cacheKey, lines)
	return lines
}

func sentReadMarker(msg tracker.Message) string {
	if msg.Sender != "You" && !strings.Contains(msg.Sender, "→") && !strings.HasPrefix(msg.Sender, "to ") {
		return ""
	}
	if msg.Read {
		return readStatusStyle.Render("✓✓ ")
	}
	if msg.Notified {
		return "✓✓ "
	}
	if msg.Delivered {
		return "✓ "
	}
	return ""
}

func messageBodyLines(body string, wrapWidth int) []string {
	var out []string
	for _, line := range strings.Split(body, "\n") {
		out = append(out, wrapLine("    "+line, wrapWidth)...)
	}
	return out
}

func (m model) visibleBodyLines(lines []string, index int) []string {
	if m.mode != advancedView || index == m.messageSelected || index == 0 || len(lines) <= 3 {
		return lines
	}
	return append(append([]string{}, lines[:3]...), mutedStyle.Render("    …"))
}

func (m model) messageContentWidth() int {
	_, mid, _ := m.layoutWidths()
	return panelInnerWidth(mid)
}

func (m model) messageChromeHeight() int {
	_, mid, _ := m.layoutWidths()
	return lineCount(titleStyle.Render("Conversation") + "\n" + m.composerBox(panelInnerWidth(mid)))
}

func (m model) messageVisibleLines() int {
	return max(1, m.height-lineCount(m.footer(max(1, m.width)))-m.messageChromeHeight())
}
func messagePageSize(height int) int             { return max(1, height/2) }
func messageBottomOffset(total, visible int) int { return max(0, total-visible) }
func clampMessageOffset(offset, total, visible int) int {
	maxOffset := messageBottomOffset(total, visible)
	if offset > maxOffset {
		return maxOffset
	}
	return max(0, offset)
}

func (m model) scrollHint() string {
	lines, visible := len(m.messageLinesForWidth(m.messageContentWidth())), m.messageVisibleLines()
	if lines <= visible {
		return mutedStyle.Render("c-u/c-d scroll messages")
	}
	offset := clampMessageOffset(m.messageOffset, lines, visible)
	return mutedStyle.Render(fmt.Sprintf("messages %d-%d/%d · c-u/c-d", offset+1, min(lines, offset+visible), lines))
}

func (m model) composerView(width int) string {
	return lipgloss.NewStyle().Width(max(1, width)).Render(strings.Join(m.composerLines(width), "\n"))
}

func (m model) composerLines(width int) []string {
	focused := !m.messageFocused
	cursor := ""
	if focused {
		cursor = selectedStyle.Render("█")
	}
	prefix := m.composerPrefix()
	prompt := prefix + string(m.composer) + cursor
	if len(m.composer) == 0 {
		placeholder := m.composerPlaceholder()
		if m.agentListStale {
			placeholder = "agent tracker unavailable; sending disabled"
		}
		prompt = prefix + cursor + mutedStyle.Render(placeholder)
	}
	wrapped := wrapLine(prompt, max(1, width-1))
	bodyMaxLines := max(1, composerMaxLines-1)
	if len(wrapped) > bodyMaxLines {
		wrapped = wrapped[len(wrapped)-bodyMaxLines:]
	}
	for i := range wrapped {
		wrapped[i] = truncateCells(wrapped[i], max(1, width-1))
	}
	return append([]string{m.composerModeHint(width)}, wrapped...)
}

func (m model) composerPrefix() string {
	if m.mode == advancedView {
		name := fallback(m.currentRow().Name, "agent")
		return agentStyle(name, true).Render("@"+name) + mutedStyle.Render(": ")
	}
	return mutedStyle.Render("> ")
}

func (m model) composerPlaceholder() string {
	switch m.inputMode {
	case inputModeText:
		return "type pane text (F1 returns to message mode)"
	case inputModeKeys:
		return "type key tokens, e.g. C-c Enter"
	case inputModeBroadcast:
		return "broadcast disabled; F1/F2/F3 to switch modes"
	default:
		return "type message"
	}
}

func (m model) composerModeHint(width int) string {
	action := composerActionForMode(string(m.composer), m.inputMode)
	active := m.inputMode.name()
	if slashComposerCommand(string(m.composer)) {
		switch action.Kind {
		case "direct_text":
			active = "text"
		case "direct_keys":
			active = "key"
		case "broadcast":
			active = "broadcast"
		default:
			active = "msg"
		}
	}
	tab := func(name, label string) string {
		if active == name {
			return activeModeTabStyle.Render(label)
		}
		return modeTabStyle.Render(label)
	}
	context := mutedStyle.Render(" target " + m.sendingContextLine())
	line := tab("msg", "F1 /msg inbox") + " " + tab("text", "F2 /text pane") + " " + tab("key", "F3 /key pane") + " " + tab("broadcast", "F4 /broadcast disabled") + context
	return truncateCells(line, max(1, width-1))
}

func (m model) sendingContextLine() string {
	row := m.currentRow()
	if row.Name == "" {
		return "no target"
	}
	parts := []string{row.Name}
	if badge := modelBadge(row); badge != "??" {
		parts = append(parts, badge)
	}
	if machine := rowMachineLabel(row); machine != "" {
		parts = append(parts, "@ "+machine)
	}
	return strings.Join(parts, " ")
}

func truncateLines(s string, height int) string {
	lines := strings.Split(s, "\n")
	if len(lines) > height {
		lines = lines[:height]
	}
	return strings.Join(lines, "\n")
}

func wrapLine(s string, width int) []string {
	if lipgloss.Width(s) <= width {
		return []string{s}
	}
	words := strings.Fields(s)
	if len(words) == 0 {
		return []string{""}
	}
	var lines []string
	current := ""
	for _, word := range words {
		candidate := strings.TrimSpace(current + " " + word)
		if lipgloss.Width(candidate) <= width {
			current = candidate
			continue
		}
		if current != "" {
			lines = append(lines, current)
		}
		for lipgloss.Width(word) > width {
			part := truncateCells(word, width)
			lines = append(lines, part)
			word = strings.TrimPrefix(word, part)
		}
		current = word
	}
	if current != "" {
		lines = append(lines, current)
	}
	return lines
}
func truncateCells(s string, width int) string {
	var b strings.Builder
	for _, r := range s {
		if lipgloss.Width(b.String()+string(r)) > width {
			break
		}
		b.WriteRune(r)
	}
	return b.String()
}
func marker(selected bool) string {
	if selected {
		return ">"
	}
	return " "
}
func panelInnerWidth(w int) int  { return max(1, w-4) }
func panelInnerHeight(h int) int { return max(1, h-2) }

func box(s string, w, h int) string {
	innerW := panelInnerWidth(w)
	innerH := panelInnerHeight(h)
	return panelBoxStyle.Width(innerW).Height(innerH).MaxWidth(max(1, w)).Render(s)
}
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func localHostname() string {
	if h := os.Getenv("AGENT_TRACKER_HOSTNAME"); h != "" {
		return h
	}
	if h, err := os.Hostname(); err == nil {
		return h
	}
	return "local"
}

func (m model) renderPromptMenu(width, height int) string {
	var body string
	if len(m.prompts) == 0 {
		body = lipgloss.NewStyle().
			Foreground(palette.Yellow).
			Render("No prompt templates found.\nAdd <prompt-name>.md files in ~/.config/agent-communicator/prompts/")
	} else {
		var listLines []string
		for i, prompt := range m.prompts {
			style := lipgloss.NewStyle().Foreground(palette.Text)
			prefix := "  "
			if i == m.promptSelected {
				style = style.Background(palette.Surface0).Foreground(palette.Yellow)
				prefix = "> "
			}
			listLines = append(listLines, prefix+style.Render(prompt.Name))
		}
		body = strings.Join(listLines, "\n")
	}

	title := titleStyle.Render("Prompt Templates")
	help := mutedStyle.Render("enter edit/send · esc close · only saved edits are sent")
	boxContent := title + "\n" + help + "\n\n" + body
	return box(boxContent, width, height)
}

func (m model) renderConfigMenu(width, height int) string {
	var body string
	if len(m.configItems) == 0 {
		body = lipgloss.NewStyle().
			Foreground(palette.Red).
			Render("No custom agent configurations found.\nPlace config.json in ~/.config/agent-tracker/agents/<name>/")
	} else {
		var listLines []string
		for i, item := range m.configItems {
			style := lipgloss.NewStyle().Foreground(palette.Text)
			prefix := "  "
			if i == m.configSelected {
				style = style.Background(palette.Surface0).Foreground(palette.Yellow)
				prefix = "> "
			}

			scopePrefix := fmt.Sprintf("[%s] (local) ", shortHost(localHostname()))
			if item.IsRemote {
				scopePrefix = fmt.Sprintf("[%s] ", shortHost(item.Hostname))
			}

			scopeStyle := lipgloss.NewStyle().Foreground(palette.Overlay0)
			if !item.IsRemote {
				scopeStyle = lipgloss.NewStyle().Foreground(palette.Green)
			}
			if i == m.configSelected {
				scopeStyle = scopeStyle.Background(palette.Surface0).Foreground(palette.Peach)
			}

			listLines = append(listLines, prefix+scopeStyle.Render(scopePrefix)+style.Render(item.Name)+" - "+item.Description)
		}
		body = strings.Join(listLines, "\n")
	}

	title := titleStyle.Render("Custom Agent Configurations")
	boxContent := title + "\n\n" + body
	return box(boxContent, width, height)
}
