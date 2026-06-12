package main

import (
	"strconv"
	"strings"
)

type memoryActionConfirmation struct {
	Action   string
	MemoryID string
}

func (c memoryActionConfirmation) Active() bool {
	return strings.TrimSpace(c.Action) != "" && strings.TrimSpace(c.MemoryID) != ""
}

func (m model) clearMemoryConfirmation() model {
	m.memoryConfirm = memoryActionConfirmation{}
	return m
}

func (m model) memoryConfirmationMatches(mem memoryRecord, action string) bool {
	return m.memoryConfirm.Active() && m.memoryConfirm.MemoryID == mem.MemoryID && m.memoryConfirm.Action == action
}

func memoryActionForDelete(mem memoryRecord) (string, bool) {
	switch strings.ToLower(strings.TrimSpace(mem.Status)) {
	case "pending":
		return "reject", true
	case "active", "approved":
		return "revoke", true
	default:
		return "", false
	}
}

func memoryActionAllowed(mem memoryRecord, action string) bool {
	switch action {
	case "approve":
		return strings.EqualFold(strings.TrimSpace(mem.Status), "pending")
	case "reject":
		return strings.EqualFold(strings.TrimSpace(mem.Status), "pending")
	case "revoke":
		status := strings.ToLower(strings.TrimSpace(mem.Status))
		return status == "active" || status == "approved"
	case "rollback":
		status := strings.ToLower(strings.TrimSpace(mem.Status))
		return (status == "active" || status == "approved") && mem.Version > 1
	default:
		return false
	}
}

func memoryActionConfirmText(mem memoryRecord, action string) string {
	switch action {
	case "reject":
		return "Press d again to reject " + mem.MemoryID + " · esc cancels"
	case "revoke":
		return "Press d again to revoke " + mem.MemoryID + " · esc cancels"
	case "rollback":
		return "Press R again to rollback " + mem.MemoryID + " to v" + itoa(mem.Version-1) + " · esc cancels"
	default:
		return ""
	}
}

func itoa(value int) string {
	return strconv.Itoa(value)
}
