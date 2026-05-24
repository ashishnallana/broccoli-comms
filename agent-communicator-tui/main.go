package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/tracker"
)

const appName = "agent-communicator"

var version = "dev"
var refreshInterval = 30 * time.Second

type config struct {
	Version bool
}

func parseArgs(args []string) (config, error) {
	fs := flag.NewFlagSet(appName, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	cfg := config{}
	fs.BoolVar(&cfg.Version, "version", false, "print version and exit")
	if err := fs.Parse(args); err != nil {
		return config{}, err
	}
	return cfg, nil
}

func run(stdout io.Writer, args []string) error {
	cfg, err := parseArgs(args)
	if err != nil {
		return err
	}
	if cfg.Version {
		_, err = fmt.Fprintf(stdout, "%s %s\n", appName, version)
		return err
	}
	// Use alternate screen so only the message viewport scrolls; no mouse capture.
	ownName := os.Getenv("AGENT_NAME")
	if ownName == "" {
		ownName = appName
	}
	_ = cleanupHistoryOnStart()
	p := tea.NewProgram(newModel(tracker.New(""), ownName), tea.WithOutput(stdout), tea.WithAltScreen())
	_, err = p.Run()
	return err
}

func main() {
	if err := run(os.Stdout, os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "%s: %v\n", appName, err)
		os.Exit(2)
	}
}
