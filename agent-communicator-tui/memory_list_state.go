package main

import "strings"

type memoryFilterOption struct {
	Label string
	Value string
}

var memoryStatusFilters = []memoryFilterOption{{Label: "all", Value: ""}, {Label: "pending", Value: "pending"}, {Label: "active", Value: "active"}}
var memoryTypeFilters = []memoryFilterOption{{Label: "all", Value: ""}, {Label: "fact", Value: "fact"}, {Label: "habit", Value: "habit"}, {Label: "episode", Value: "episode"}, {Label: "expertise", Value: "expertise"}, {Label: "skill", Value: "skill"}}

func (m model) filteredMemoryItems() []memoryRecord {
	query := strings.ToLower(strings.TrimSpace(string(m.memoryQuery)))
	status := strings.ToLower(strings.TrimSpace(m.memoryStatusFilter))
	memoryType := strings.ToLower(strings.TrimSpace(m.memoryTypeFilter))
	agent := strings.ToLower(strings.TrimSpace(m.memoryAgentFilter))
	items := make([]memoryRecord, 0, len(m.memoryItems))
	for _, mem := range m.memoryItems {
		if status != "" && strings.ToLower(mem.Status) != status {
			continue
		}
		if memoryType != "" && strings.ToLower(mem.Type) != memoryType {
			continue
		}
		if agent != "" && !strings.Contains(strings.ToLower(memoryRecordAgentName(mem)), agent) {
			continue
		}
		if query != "" && !memoryRecordMatchesQuery(mem, query) {
			continue
		}
		items = append(items, mem)
	}
	return items
}

func memoryRecordMatchesQuery(mem memoryRecord, query string) bool {
	haystack := strings.ToLower(strings.Join([]string{
		mem.MemoryID,
		mem.Status,
		mem.Type,
		mem.Scope,
		memoryRecordAgentName(mem),
		mem.Title,
		mem.Body,
		strings.Join(mem.Tags, " "),
	}, " "))
	for _, part := range strings.Fields(query) {
		if !strings.Contains(haystack, part) {
			return false
		}
	}
	return true
}

func (m model) selectedFilteredMemoryRecord() (memoryRecord, bool) {
	items := m.filteredMemoryItems()
	if len(items) == 0 || m.memorySelected < 0 || m.memorySelected >= len(items) {
		return memoryRecord{}, false
	}
	return items[m.memorySelected], true
}

func (m *model) clampMemorySelection() {
	items := m.filteredMemoryItems()
	if len(items) == 0 {
		m.memorySelected = 0
		m.memoryOffset = 0
		return
	}
	m.memorySelected = min(max(0, m.memorySelected), len(items)-1)
	m.memoryOffset = min(max(0, m.memoryOffset), max(0, len(items)-1))
}

func (m model) currentMemorySelectionID() string {
	if mem, ok := m.selectedFilteredMemoryRecord(); ok {
		return mem.MemoryID
	}
	return ""
}

func (m *model) preserveMemorySelection(previousID string) {
	items := m.filteredMemoryItems()
	if previousID != "" {
		for i, mem := range items {
			if mem.MemoryID == previousID {
				m.memorySelected = i
				m.scrollSelectedMemoryIntoView(memoryVisibleRowsForHeight(m.memoryListHeight()))
				return
			}
		}
	}
	m.clampMemorySelection()
}

func memoryVisibleRowsForHeight(height int) int { return max(1, height/3) }

func (m model) memoryListHeight() int {
	bodyH := max(1, m.height-lineCount(m.footer(max(1, m.width)))-lineCount(m.bottomTabBar(max(1, m.width))))
	width := m.width
	wide := width >= 70
	if wide {
		width, _ = memoryLayoutWidths(width)
	}
	title := titleStyle.Render("Memory Management")
	query := "x"
	help := "x"
	return max(1, bodyH-lineCount(title)-lineCount(query)-lineCount(help)-3)
}

func (m *model) scrollSelectedMemoryIntoView(visibleRows int) {
	items := m.filteredMemoryItems()
	if len(items) == 0 {
		m.memoryOffset = 0
		return
	}
	visibleRows = min(max(1, visibleRows), len(items))
	if m.memorySelected < m.memoryOffset {
		m.memoryOffset = m.memorySelected
	}
	if m.memorySelected >= m.memoryOffset+visibleRows {
		m.memoryOffset = m.memorySelected - visibleRows + 1
	}
	m.memoryOffset = min(max(0, m.memoryOffset), max(0, len(items)-visibleRows))
}

func (m *model) moveMemorySelection(delta, visibleRows int) {
	items := m.filteredMemoryItems()
	if len(items) == 0 {
		m.memorySelected = 0
		m.memoryOffset = 0
		return
	}
	m.memorySelected = min(max(0, m.memorySelected+delta), len(items)-1)
	m.scrollSelectedMemoryIntoView(visibleRows)
}

func (m *model) cycleMemoryStatusFilter() {
	previousID := m.currentMemorySelectionID()
	m.memoryStatusFilter = nextMemoryFilterValue(memoryStatusFilters, m.memoryStatusFilter)
	m.preserveMemorySelection(previousID)
}

func (m *model) cycleMemoryTypeFilter() {
	previousID := m.currentMemorySelectionID()
	m.memoryTypeFilter = nextMemoryFilterValue(memoryTypeFilters, m.memoryTypeFilter)
	m.preserveMemorySelection(previousID)
}

func (m *model) cycleMemoryAgentFilter() {
	previousID := m.currentMemorySelectionID()
	m.memoryAgentFilter = nextMemoryFilterValue(m.memoryAgentFilterOptions(), m.memoryAgentFilter)
	m.preserveMemorySelection(previousID)
}

func (m model) memoryAgentFilterOptions() []memoryFilterOption {
	seen := map[string]bool{"": true}
	options := []memoryFilterOption{{Label: "all", Value: ""}}
	for _, mem := range m.memoryItems {
		agent := strings.TrimSpace(memoryRecordAgentName(mem))
		if agent == "" || seen[strings.ToLower(agent)] {
			continue
		}
		seen[strings.ToLower(agent)] = true
		options = append(options, memoryFilterOption{Label: agent, Value: agent})
	}
	return options
}

func nextMemoryFilterValue(options []memoryFilterOption, current string) string {
	current = strings.ToLower(strings.TrimSpace(current))
	for i, option := range options {
		if option.Value == current {
			return options[(i+1)%len(options)].Value
		}
	}
	return options[0].Value
}

func memoryFilterLabel(value string) string {
	if strings.TrimSpace(value) == "" {
		return "all"
	}
	return value
}
