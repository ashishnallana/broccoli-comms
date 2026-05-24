package main

import (
	"os"
	"path/filepath"
	"syscall"
)

const retainedHistoryMessages = 1000
const communicatorAgentID = "00000000-0000-5000-8000-000000000001"

func cleanupHistoryOnStart() error {
	if err := pruneJSONLFile(outboxPath(), retainedHistoryMessages, ""); err != nil {
		return err
	}
	return pruneJSONLFile(communicatorInboxPath(), retainedHistoryMessages, communicatorInboxPath()+".lock")
}

func communicatorInboxPath() string {
	base := os.Getenv("XDG_CACHE_HOME")
	if base == "" {
		home, _ := os.UserHomeDir()
		base = filepath.Join(home, ".cache")
	}
	agentID := os.Getenv("AGENT_ID")
	if agentID == "" {
		agentID = communicatorAgentID
	}
	return filepath.Join(base, "agent-tracker", "inboxes", agentID+".inbox")
}

func pruneJSONLFile(path string, keep int, lockPath string) error {
	if keep <= 0 {
		return nil
	}
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return nil
	} else if err != nil {
		return err
	}
	var lock *os.File
	if lockPath != "" {
		if err := os.MkdirAll(filepath.Dir(lockPath), 0o700); err != nil {
			return err
		}
		var err error
		lock, err = os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o600)
		if err != nil {
			return err
		}
		defer lock.Close()
		if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); err != nil {
			return err
		}
		defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	lines := nonEmptyLines(data)
	if len(lines) <= keep {
		return nil
	}
	lines = lines[len(lines)-keep:]
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+".tmp-")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	for _, line := range lines {
		if _, err := tmp.Write(append(line, '\n')); err != nil {
			tmp.Close()
			os.Remove(tmpName)
			return err
		}
	}
	if err := tmp.Close(); err != nil {
		os.Remove(tmpName)
		return err
	}
	return os.Rename(tmpName, path)
}

func nonEmptyLines(data []byte) [][]byte {
	var lines [][]byte
	start := 0
	for i, b := range data {
		if b != '\n' {
			continue
		}
		if i > start {
			line := append([]byte(nil), data[start:i]...)
			lines = append(lines, line)
		}
		start = i + 1
	}
	if start < len(data) {
		lines = append(lines, append([]byte(nil), data[start:]...))
	}
	return lines
}
