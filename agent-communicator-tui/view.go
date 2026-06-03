package main

import (
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"

	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

var composerBoxStyle = lipgloss.NewStyle().Background(colors.InputBg).Foreground(colors.Text).Padding(1, 2)
var panelBoxStyle = lipgloss.NewStyle().Background(colors.PanelBg).Padding(0, 1)
var mobileComposerBoxStyle = lipgloss.NewStyle().Background(colors.InputBg).Padding(1, 1)

const composerMaxLines = 5

func (m model) View() string {
	defer debugSince("view", time.Now())
	if m.width == 0 {
		return "loading..."
	}
	if m.commandPalette.Open {
		return m.commandPaletteView(m.width, m.height)
	}
	return m.baseView()
}

func (m model) baseView() string {
	bodyH := max(3, m.height)
	if m.showingSaveForm {
		return m.renderSaveForm()
	}
	if m.showingPromptMenu {
		return m.renderPromptMenu(m.width, bodyH)
	}
	if m.showingConfigMenu {
		return m.renderConfigMenu(m.width, bodyH)
	}
	if m.width < 70 {
		return truncateLines(m.conversationPanel(m.width, bodyH), bodyH)
	}
	chatW, rightW, _ := m.layoutWidths()
	chat := m.conversationPanel(chatW, bodyH)
	right := m.rightColumn(rightW, bodyH)
	return truncateLines(lipgloss.JoinHorizontal(lipgloss.Top, chat, right), bodyH)
}

func (m model) layoutWidths() (int, int, int) {
	right := min(42, max(28, (m.width*32)/100))
	if m.width < 100 {
		right = min(34, max(24, m.width/3))
	}
	chat := max(10, m.width-right)
	return chat, right, 0
}

func (m model) sidebarView(width, height int) string {
	return m.rightColumn(width, height)
}

func (m model) rightColumn(width, height int) string {
	status := m.registryStatusLine()
	statusH := 2
	currentH := min(7, max(5, height/4))
	listH := max(1, height-currentH-statusH)
	current := m.currentAgentPanel(width, currentH)
	list := m.switcherPanel(width, listH)
	statusView := lipgloss.NewStyle().Width(width).Height(statusH).Padding(0, 2).Background(colors.RightColumnBg).Foreground(colors.Muted).Render(status)
	return lipgloss.JoinVertical(lipgloss.Left, current, list, statusView)
}

func (m model) currentAgentPanel(width, height int) string {
	row := m.currentRow()
	view := m.agentView(row)
	name := fallback(view.Name, "no agent selected")
	host := fallback(view.HostnameLabel, localHostname())
	provider := strings.ToLower(view.ModelBadge)
	if provider == "??" {
		provider = "unknown"
	}
	status := view.StatusLabel
	if row.Name == "" {
		status = "unknown"
	}
	heroW := max(1, width-4)
	heroInnerW := max(1, heroW-2)
	statusBadge := lipgloss.NewStyle().Background(colors.RightColumnBg).Foreground(colors.Accent).Padding(0, 1).Render(status)
	namePrefix := statusDotStyle(status).Background(colors.SelectedBg).Render("●") + bgSpaces(1, colors.SelectedBg)
	nameBudget := max(1, heroInnerW-lipgloss.Width(namePrefix)-lipgloss.Width(statusBadge)-1)
	nameText := fgOnBg(colors.SelectedFg, colors.SelectedBg).Render(truncateCells(name, nameBudget))
	gap := max(1, heroInnerW-lipgloss.Width(namePrefix)-lipgloss.Width(nameText)-lipgloss.Width(statusBadge))
	line1 := namePrefix + nameText + bgSpaces(gap, colors.SelectedBg) + statusBadge
	line2 := lipgloss.NewStyle().Foreground(colors.SelectedFg).Background(colors.SelectedBg).Faint(true).Render(truncateCells("  "+host+" · "+provider, heroInnerW))
	hero := lipgloss.NewStyle().Width(heroW).Background(colors.SelectedBg).Foreground(colors.SelectedFg).Bold(true).Padding(1, 1).Render(line1 + "\n" + line2)
	body := shellTitleStyle.Render("Agent Communicator") + "\n" + hero
	return lipgloss.NewStyle().Width(width).Height(height).Padding(1, 1).Background(colors.RightColumnBg).Render(truncateLines(body, max(1, height-1)))
}

func (m model) switcherPanel(width, height int) string {
	shown := len(m.rows)
	hidden := m.hiddenCount() + m.systemHiddenCount()
	headerRight := fmt.Sprintf("%d shown", shown)
	if hidden > 0 {
		headerRight = fmt.Sprintf("%d shown · %d hidden", shown, hidden)
	}
	headerTitle := fgOnBg(colors.Accent, colors.RightColumnBg).Bold(true).Render("Switch agent")
	headerCount := fgOnBg(colors.Muted, colors.RightColumnBg).Render(headerRight)
	headerGap := bgSpaces(max(1, width-4-lipgloss.Width("Switch agent")-lipgloss.Width(headerRight)), colors.RightColumnBg)
	header := headerTitle + headerGap + headerCount
	filter := lipgloss.NewStyle().Width(max(1, width-4)).Background(colors.PanelBg).Foreground(colors.Muted).Padding(0, 1).Render("⌕ filter agents…")
	list := m.agentList(width-2, max(1, height-lineCount(header)-lineCount(filter)-3))
	body := header + "\n" + filter + "\n" + list
	return lipgloss.NewStyle().Width(width).Height(height).Padding(1, 1).Background(colors.RightColumnBg).Render(truncateLines(body, max(1, height-1)))
}

func (m model) registryStatusLine() string {
	if m.healthErr != nil || m.agentListStale || m.err != nil {
		return "registry degraded"
	}
	if m.health.RegistryConnected != nil {
		if *m.health.RegistryConnected {
			return "registry online"
		}
		return "registry offline"
	}
	if m.health.Status != "" && m.health.Status != "ok" {
		return "registry " + m.health.Status
	}
	return "registry online"
}

func (m model) conversationPanel(width, height int) string {
	defer debugSince("conversation_panel", time.Now())
	padX := 3
	if width < 70 {
		padX = 1
	}
	innerW := max(1, width-(padX*2))
	title := titleStyle.Render(m.conversationTitle())
	composer := m.composerBox(innerW)
	if m.mode == savedView {
		composer = mutedStyle.Render("Saved messages")
	}
	messageH := max(1, height-lineCount(title)-lineCount(composer)-3)
	messages := m.messageViewWithHeight(innerW, messageH)
	body := title + "\n" + composer + "\n" + bgSpaces(innerW, colors.BaseBg) + "\n" + messages
	return lipgloss.NewStyle().
		Width(width).
		Height(height).
		MaxWidth(width).
		MaxHeight(height).
		Padding(1, padX, 0, padX).
		Background(colors.BaseBg).
		Render(body)
}

func (m model) conversationTitle() string {
	if m.mode == savedView {
		return "Saved Messages"
	}
	if m.mode == advancedView {
		return "Conversation"
	}
	return "Conversation"
}

func (m model) composerBox(width int) string {
	input := m.composerInputBox(width)
	controls := m.composerModeControls(width)
	if controls == "" {
		return input
	}
	return input + "\n" + controls
}

func (m model) composerInputBox(width int) string {
	padX := 2
	if m.width < 70 {
		padX = 1
	}
	inner := max(1, width-(padX*2))
	blank := bgSpaces(width, colors.InputBg)
	lines := []string{blank}
	for _, line := range m.composerLines(inner) {
		lines = append(lines, bgSpaces(padX, colors.InputBg)+padStyledLine(line, inner, colors.InputBg)+bgSpaces(padX, colors.InputBg))
	}
	lines = append(lines, blank)
	return strings.Join(lines, "\n")
}

func (m model) footer(width int) string {
	lines := []string{}
	if m.paneCaptureStatus != "" {
		lines = append(lines, m.paneCaptureStatus)
	} else if m.directInputStatus != "" {
		statusLine := m.directInputStatus
		if m.directInputStatusErr {
			statusLine = errorBarStyle.Render(statusLine)
		}
		lines = append(lines, statusLine)
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
	inner := max(4, cardWidth-4)
	view := m.agentView(row)
	provider := strings.ToLower(view.ModelBadge)
	if provider == "??" {
		provider = "unknown"
	}

	bg := colors.RightColumnBg
	if selected {
		bg = colors.SelectedBg
	} else if m.hasUnread(row) {
		bg = colors.PanelBgAlt
	}

	unread := ""
	if view.UnreadCount > 0 {
		unread = bgSpaces(1, bg) + unreadCountBadge(view.UnreadCount)
	}

	limit := max(1, inner-2-lipgloss.Width(unread))
	suffix := ""
	if m.isHiddenAgent(row) {
		suffix = fgOnBg(colors.Muted, bg).Render(" ◌")
		limit = max(1, limit-2)
	}

	dot := agentStatusDotStyle(row).Background(bg).Render("●")
	space := bgSpaces(1, bg)

	nameStyle := fgOnBg(colors.Text, bg)
	if selected {
		nameStyle = fgOnBg(colors.SelectedFg, bg).Bold(true)
	} else if m.hasUnread(row) {
		nameStyle = fgOnBg(colors.TextStrong, bg).Bold(true)
	}
	nameStr := nameStyle.Render(truncateCells(view.Name, limit)) + suffix

	nameLine := dot + space + nameStr + unread

	metaLeft := provider + " · " + fallback(view.HostnameLabel, localHostname())
	metaRight := view.StatusLabel
	gap := max(1, inner-lipgloss.Width(metaLeft)-lipgloss.Width(metaRight))
	metaLine := fgOnBg(colors.Muted, bg).Render(truncateCells(metaLeft+strings.Repeat(" ", gap)+metaRight, inner))

	contentW := max(1, cardWidth-2)
	return strings.Join([]string{
		bgSpaces(1, bg) + padStyledLine(nameLine, contentW, bg) + bgSpaces(1, bg),
		bgSpaces(1, bg) + padStyledLine(metaLine, contentW, bg) + bgSpaces(1, bg),
	}, "\n")
}

func (m model) hiddenSeparator(width int) string {
	return ""
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
	items := make([]struct {
		Index int
		Row   agentRow
	}, 0, len(m.rows))
	localCount, remoteCount := 0, 0
	for i, row := range m.rows {
		if row.Scope == "remote" {
			remoteCount++
		} else {
			localCount++
		}
		items = append(items, struct {
			Index int
			Row   agentRow
		}{Index: i, Row: row})
	}
	if len(items) == 0 {
		return mutedStyle.Render("no agents")
	}
	visible := max(1, height/agentCardHeight)
	offset := min(max(0, m.agentOffset), max(0, len(items)-visible))
	end := min(len(items), offset+visible)
	var b strings.Builder
	lastGroup := ""
	for pos := offset; pos < end; pos++ {
		item := items[pos]
		group := "LOCAL"
		count := localCount
		if item.Row.Scope == "remote" {
			group = "REMOTE"
			count = remoteCount
		}
		heading := fmt.Sprintf("%s (%d)", group, count)
		if heading != lastGroup {
			if b.Len() > 0 {
				b.WriteString("\n")
			}
			b.WriteString(sectionHeaderStyle.Render(truncateCells(heading, max(1, width-1))) + "\n")
			lastGroup = heading
		}
		b.WriteString(m.agentCard(item.Row, item.Index == m.selected, width-2))
		if pos < end-1 {
			b.WriteString("\n")
		}
	}
	if end < len(items) {
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
	return lipgloss.NewStyle().Width(max(1, width)).Height(visible).MaxHeight(visible).Background(colors.BaseBg).Render(strings.Join(lines[offset:end], "\n"))
}

func (m model) messageLinesForWidth(width int) []string {
	start := time.Now()
	wrapWidth := max(10, width)
	messages := m.displayOrderedMessages()
	defer func() {
		debugLogf("message_lines duration=%s messages=%d width=%d", time.Since(start), len(messages), width)
	}()
	systemEvents := m.displayOrderedSystemEvents()
	if len(messages) == 0 && len(systemEvents) == 0 {
		if len(m.rows) > 0 && m.rows[m.selected].Scope == "remote" {
			return wrapBackgroundStyledText("No messages. Remote history is in-memory for sent messages only.", wrapWidth, colors.Muted, colors.BaseBg)
		}
		return wrapBackgroundStyledText("No messages. Inbox history loads for local agents.", wrapWidth, colors.Muted, colors.BaseBg)
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
			lines = append(lines, bgSpaces(wrapWidth, colors.BaseBg))
		}
		lines = append(lines, m.messageBubbleLines(msg, i, wrapWidth)...)
	}
	for _, event := range systemEvents {
		if len(lines) > 0 {
			lines = append(lines, bgSpaces(wrapWidth, colors.BaseBg))
		}
		lines = append(lines, m.systemEventLine(event, wrapWidth))
	}
	storeMessageLines(cacheKey, lines)
	return lines
}

func sentReadMarker(msg tracker.Message, bgOpt ...lipgloss.Color) string {
	if !isSentMessage(msg) {
		return ""
	}
	bg := colors.BaseBg
	if len(bgOpt) > 0 {
		bg = bgOpt[0]
	}
	if msg.Read {
		return fgOnBg(colors.ReadTick, bg).Render("✓✓")
	}
	if msg.Notified {
		return fgOnBg(colors.DeliveredTick, bg).Render("✓✓")
	}
	if msg.Delivered {
		return fgOnBg(colors.DeliveredTick, bg).Render("✓✓")
	}
	return fgOnBg(colors.SentTick, bg).Render("✓")
}

func sentReceiptLine(msg tracker.Message, bg lipgloss.Color) string {
	if !isSentMessage(msg) {
		return ""
	}
	state := "sent"
	if msg.Delivered || msg.Notified {
		state = "delivered"
	}
	if msg.Read {
		state = "read"
	}
	marker := sentReadMarker(msg, bg)
	text := state
	if ts := formatDisplayTime(msg.Timestamp); ts != "" {
		text += " · " + ts
	}
	return marker + bgSpaces(1, bg) + fgOnBg(colors.Muted, bg).Render(text)
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
	return append(append([]string{}, lines[:3]...), "    …")
}

func (m model) messageContentWidth() int {
	chat, _, _ := m.layoutWidths()
	return max(1, chat-6)
}

func (m model) messageChromeHeight() int {
	chat, _, _ := m.layoutWidths()
	return lineCount(titleStyle.Render("Conversation") + "\n" + m.composerBox(max(1, chat-6)))
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
	lineWidth := max(1, width-1)
	prefix := m.composerPrefix()
	prefixW := lipgloss.Width(prefix)
	textStyle := fgOnBg(colors.Text, colors.InputBg)
	placeholderStyle := fgOnBg(colors.Muted, colors.InputBg)
	cursorStyle := fgOnBg(colors.Success, colors.InputBg).Bold(true)
	cursor := ""
	cursorW := 0
	if !m.messageFocused && !m.cursorHidden {
		cursor = cursorStyle.Render("█")
		cursorW = 1
	}

	if len(m.composer) == 0 {
		placeholder := m.composerPlaceholder()
		if m.agentListStale {
			placeholder = "agent tracker unavailable; sending disabled"
		}
		available := max(1, lineWidth-prefixW-cursorW)
		line := prefix + cursor + placeholderStyle.Render(truncateCells(placeholder, available))
		return []string{padStyledLine(line, lineWidth, colors.InputBg)}
	}

	chunks := wrapCells(string(m.composer), max(1, lineWidth-prefixW), lineWidth)
	if len(chunks) == 0 {
		chunks = []string{""}
	}
	if cursor != "" {
		last := len(chunks) - 1
		limit := lineWidth
		if last == 0 {
			limit = max(1, lineWidth-prefixW)
		}
		if lipgloss.Width(chunks[last])+cursorW > limit {
			chunks = append(chunks, "")
		}
	}

	lines := make([]string, 0, len(chunks))
	for i, chunk := range chunks {
		content := textStyle.Render(chunk)
		if i == len(chunks)-1 {
			content += cursor
		}
		line := content
		if i == 0 {
			line = prefix + content
		}
		lines = append(lines, padStyledLine(line, lineWidth, colors.InputBg))
	}
	bodyMaxLines := max(1, composerMaxLines)
	if len(lines) > bodyMaxLines {
		lines = lines[len(lines)-bodyMaxLines:]
	}
	return lines
}

func (m model) composerPrefix() string {
	label := "/" + m.activeComposerModeName()
	if label == "/key" {
		label = "/keys"
	}
	return lipgloss.NewStyle().Background(colors.InputBg).Foreground(colors.Accent).Bold(true).Padding(0, 1).Render(label) + bgSpaces(1, colors.InputBg)
}

func wrapCells(s string, firstWidth, nextWidth int) []string {
	if s == "" {
		return nil
	}
	widths := []int{max(1, firstWidth)}
	var chunks []string
	var b strings.Builder
	currentWidth := 0
	limit := widths[0]
	for _, r := range s {
		rw := lipgloss.Width(string(r))
		if currentWidth > 0 && currentWidth+rw > limit {
			chunks = append(chunks, b.String())
			b.Reset()
			currentWidth = 0
			limit = max(1, nextWidth)
		}
		b.WriteRune(r)
		currentWidth += rw
	}
	if b.Len() > 0 {
		chunks = append(chunks, b.String())
	}
	return chunks
}

func (m model) composerPlaceholder() string {
	if m.inputMode == inputModeText {
		return "type pane text…"
	}
	if m.inputMode == inputModeKeys {
		return "type key tokens…"
	}
	return ""
}

type inputModeButton struct {
	Mode  inputMode
	Name  string
	Label string
}

func inputModeButtons() []inputModeButton {
	return []inputModeButton{
		{Mode: inputModeMessage, Name: "msg", Label: "/msg"},
		{Mode: inputModeText, Name: "text", Label: "/text"},
		{Mode: inputModeKeys, Name: "key", Label: "/keys"},
	}
}

func (m model) composerModeHint(width int) string {
	return m.composerModeControls(width)
}

func (m model) activeComposerModeName() string {
	action := composerActionForMode(string(m.composer), m.inputMode)
	active := m.inputMode.name()
	if slashComposerCommand(string(m.composer)) {
		switch action.Kind {
		case "direct_text":
			active = "text"
		case "direct_keys":
			active = "key"
		default:
			active = "msg"
		}
	}
	return active
}

func (m model) composerModeControls(width int) string {
	left := fgOnBg(colors.Muted, colors.BaseBg).Render("/msg sends an inbox message")
	right := fgOnBg(colors.Muted, colors.BaseBg).Render("Enter send")
	gap := max(1, width-lipgloss.Width(left)-lipgloss.Width(right))
	return left + bgSpaces(gap, colors.BaseBg) + right
}

func (m model) composerModeButtons(width int) string {
	active := m.activeComposerModeName()
	buttons := []string{}
	for i, button := range inputModeButtons() {
		if i > 0 {
			buttons = append(buttons, lipgloss.NewStyle().Width(1).Height(3).Render(""))
		}
		style := modeTabStyle
		if active == button.Name {
			style = activeModeTabStyle
		}
		buttons = append(buttons, style.Render(button.Label))
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, buttons...)
}

func (m model) composerModeDescription(width int) string {
	description := "Send chat message."
	switch m.activeComposerModeName() {
	case "text":
		description = "Type into agent pane."
	case "key":
		description = "Send keys to agent pane."
	}
	return mutedStyle.Render(truncateCells(description, max(1, width-1)))
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
	if h := config.GetString("", "tracker", "hostname"); h != "" {
		return h
	} else if h := os.Getenv("AGENT_TRACKER_HOSTNAME"); h != "" {
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
			Foreground(colors.Warning).
			Render("No prompt templates found.\nAdd <prompt-name>.md files in ~/.config/agent-communicator/prompts/")
	} else {
		var listLines []string
		for i, prompt := range m.prompts {
			style := lipgloss.NewStyle().Foreground(colors.Text)
			prefix := "  "
			if i == m.promptSelected {
				style = style.Background(colors.SelectedBg).Foreground(colors.SelectedFg)
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
			Foreground(colors.Error).
			Render("No custom agent configurations found.\nPlace config.json in ~/.config/agent-tracker/agents/<name>/")
	} else {
		var listLines []string
		for i, item := range m.configItems {
			style := lipgloss.NewStyle().Foreground(colors.Text)
			prefix := "  "
			if i == m.configSelected {
				style = style.Background(colors.SelectedBg).Foreground(colors.SelectedFg)
				prefix = "> "
			}

			scopePrefix := fmt.Sprintf("[%s] (local) ", shortHost(localHostname()))
			if item.IsRemote {
				scopePrefix = fmt.Sprintf("[%s] ", shortHost(item.Hostname))
			}

			scopeStyle := lipgloss.NewStyle().Foreground(colors.Muted)
			if !item.IsRemote {
				scopeStyle = lipgloss.NewStyle().Foreground(colors.Success)
			}
			if i == m.configSelected {
				scopeStyle = scopeStyle.Background(colors.SelectedBg).Foreground(colors.SelectedFg)
			}

			listLines = append(listLines, prefix+scopeStyle.Render(scopePrefix)+style.Render(item.Name)+" - "+item.Description)
		}
		body = strings.Join(listLines, "\n")
	}

	title := titleStyle.Render("Custom Agent Configurations")
	boxContent := title + "\n\n" + body
	return box(boxContent, width, height)
}
