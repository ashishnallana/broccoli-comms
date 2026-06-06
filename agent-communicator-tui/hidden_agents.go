package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

type agentSection int

const (
	activeAgents agentSection = iota
	hiddenAgents
)

type hiddenAgentsLoaded struct {
	Hidden map[string]bool
	Err    error
}

type hiddenAgentsSaved struct{ Err error }

func hiddenAgentsPath() string {
	base := os.Getenv("XDG_STATE_HOME")
	if base == "" {
		home, _ := os.UserHomeDir()
		base = filepath.Join(home, ".local", "state")
	}
	return filepath.Join(base, "agent-communicator", "hidden_agents.json")
}

func loadHiddenAgents() (map[string]bool, error) {
	data, err := os.ReadFile(hiddenAgentsPath())
	if os.IsNotExist(err) {
		return map[string]bool{}, nil
	}
	if err != nil {
		return nil, err
	}
	var values []string
	if err := json.Unmarshal(data, &values); err != nil {
		return nil, err
	}
	hidden := map[string]bool{}
	for _, value := range values {
		if value != "" {
			hidden[value] = true
		}
	}
	return hidden, nil
}

func saveHiddenAgents(hidden map[string]bool) error {
	path := hiddenAgentsPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	values := make([]string, 0, len(hidden))
	for key, ok := range hidden {
		if ok && key != "" {
			values = append(values, key)
		}
	}
	sort.Strings(values)
	data, err := json.MarshalIndent(values, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o600)
}

func loadHiddenAgentsCmd() tea.Cmd {
	return func() tea.Msg {
		hidden, err := loadHiddenAgents()
		return hiddenAgentsLoaded{Hidden: hidden, Err: err}
	}
}

func saveHiddenAgentsCmd(hidden map[string]bool) tea.Cmd {
	copy := map[string]bool{}
	for key, value := range hidden {
		copy[key] = value
	}
	return func() tea.Msg { return hiddenAgentsSaved{Err: saveHiddenAgents(copy)} }
}

func (m model) isHiddenAgent(row agentRow) bool {
	if strings.HasPrefix(strings.ToLower(row.Name), "zv2") {
		return false
	}
	return m.hiddenAgents != nil && m.hiddenAgents[conversationKey(row)]
}

func isSystemAgent(row agentRow) bool {
	name := strings.TrimSpace(row.Name)
	agentName := strings.TrimSpace(row.AgentName)
	target := strings.TrimSpace(row.TargetAddress)
	agentType := strings.ToLower(strings.TrimSpace(row.AgentType))
	agentCmd := strings.ToLower(strings.TrimSpace(row.AgentCmd))
	if name == "agent-communicator" || agentName == "agent-communicator" {
		return true
	}
	for _, value := range []string{name, agentName, target} {
		if strings.HasSuffix(value, "/agent-communicator") {
			return true
		}
	}
	return strings.HasPrefix(agentType, "agent-communicator") || strings.Contains(agentCmd, "agent-communicator")
}

func (m *model) applyAgentVisibility(preserveKey string) {
	if preserveKey == "" {
		preserveKey = conversationKey(m.currentRow())
	}
	source := m.allRows
	if source == nil {
		source = m.rows
	}
	visible := make([]agentRow, 0, len(source))
	for _, row := range source {
		if isSystemAgent(row) && !m.showSystemAgents {
			continue
		}
		visible = append(visible, row)
	}
	m.rows = visible
	m.sortRowsByHidden(preserveKey)
}

func (m model) systemHiddenCount() int {
	count := 0
	for _, row := range m.allRows {
		if isSystemAgent(row) && !m.showSystemAgents {
			count++
		}
	}
	return count
}

func (m *model) sortRowsByHidden(preserveKey string) {
	if preserveKey == "" {
		preserveKey = conversationKey(m.currentRow())
	}
	sort.SliceStable(m.rows, func(i, j int) bool {
		hi, hj := m.isHiddenAgent(m.rows[i]), m.isHiddenAgent(m.rows[j])
		if hi != hj {
			return !hi
		}
		return false
	})
	if preserveKey != "" {
		for i, row := range m.rows {
			if conversationKey(row) == preserveKey {
				m.selected = i
				return
			}
		}
	}
	if m.selected >= len(m.rows) {
		m.selected = max(0, len(m.rows)-1)
	}
}

func (m model) hiddenStartIndex() int {
	for i, row := range m.rows {
		if m.isHiddenAgent(row) {
			return i
		}
	}
	return len(m.rows)
}

func (m model) sectionIndices(section agentSection) []int {
	var out []int
	for i, row := range m.rows {
		if (section == hiddenAgents) == m.isHiddenAgent(row) {
			out = append(out, i)
		}
	}
	return out
}

func (m model) effectiveAgentSection() agentSection {
	if len(m.sectionIndices(m.agentSection)) > 0 {
		return m.agentSection
	}
	if len(m.sectionIndices(activeAgents)) > 0 {
		return activeAgents
	}
	return hiddenAgents
}

func (m *model) selectNextInSection(delta int) {
	if len(m.rows) == 0 {
		return
	}
	section := m.effectiveAgentSection()
	indices := m.sectionIndices(section)
	if len(indices) == 0 {
		debugLogf("selectNextInSection fallback start selected=%d delta=%d rows_len=%d", m.selected, delta, len(m.rows))
		m.selected = (m.selected + delta + len(m.rows)) % len(m.rows)
		debugLogf("selectNextInSection fallback end selected=%d", m.selected)
		return
	}
	currentPos := -1
	for pos, idx := range indices {
		if idx == m.selected {
			currentPos = pos
			break
		}
	}
	if currentPos < 0 {
		if delta < 0 {
			m.selected = indices[len(indices)-1]
		} else {
			m.selected = indices[0]
		}
		m.agentSection = section
		return
	}
	m.selected = indices[(currentPos+delta+len(indices))%len(indices)]
	m.agentSection = section
}

func (m *model) toggleAgentSection() {
	if m.effectiveAgentSection() == activeAgents {
		m.agentSection = hiddenAgents
	} else {
		m.agentSection = activeAgents
	}
	indices := m.sectionIndices(m.effectiveAgentSection())
	if len(indices) > 0 {
		m.selected = indices[0]
	}
}

func (m *model) toggleHiddenCurrentAgent() tea.Cmd {
	row := m.currentRow()
	key := conversationKey(row)
	if key == "" {
		return nil
	}
	if m.hiddenAgents == nil {
		m.hiddenAgents = map[string]bool{}
	}
	oldSection := m.effectiveAgentSection()
	oldPos := m.positionInSection(oldSection)
	if m.hiddenAgents[key] {
		delete(m.hiddenAgents, key)
	} else {
		m.hiddenAgents[key] = true
	}
	m.applyAgentVisibility(key)
	m.selectSectionPosition(oldSection, oldPos)
	m.scrollSelectedAgentIntoView()
	return saveHiddenAgentsCmd(m.hiddenAgents)
}

func (m model) positionInSection(section agentSection) int {
	indices := m.sectionIndices(section)
	for i, idx := range indices {
		if idx == m.selected {
			return i
		}
	}
	return 0
}

func (m *model) selectSectionPosition(section agentSection, pos int) {
	indices := m.sectionIndices(section)
	if len(indices) == 0 {
		if section == activeAgents {
			section = hiddenAgents
		} else {
			section = activeAgents
		}
		indices = m.sectionIndices(section)
	}
	m.agentSection = section
	if len(indices) == 0 {
		m.selected = 0
		return
	}
	if pos >= len(indices) {
		pos = len(indices) - 1
	}
	m.selected = indices[max(0, pos)]
}

func (m *model) unhideAgent(row agentRow) tea.Cmd {
	key := conversationKey(row)
	if key == "" || m.hiddenAgents == nil || !m.hiddenAgents[key] {
		return nil
	}
	delete(m.hiddenAgents, key)
	m.applyAgentVisibility(key)
	m.agentSection = activeAgents
	m.scrollSelectedAgentIntoView()
	return saveHiddenAgentsCmd(m.hiddenAgents)
}
