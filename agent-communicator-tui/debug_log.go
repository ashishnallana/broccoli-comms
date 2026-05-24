package main

import (
	"fmt"
	"os"
	"sync"
	"time"
)

var debugLogMu sync.Mutex

func debugLogf(format string, args ...any) {
	path := os.Getenv("AGENT_COMMUNICATOR_DEBUG_LOG")
	if path == "" {
		return
	}
	debugLogMu.Lock()
	defer debugLogMu.Unlock()
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return
	}
	defer file.Close()
	_, _ = fmt.Fprintf(file, "%s ", time.Now().Format(time.RFC3339Nano))
	_, _ = fmt.Fprintf(file, format, args...)
	_, _ = file.WriteString("\n")
}

func debugSince(name string, start time.Time) {
	debugLogf("%s duration=%s", name, time.Since(start))
}
