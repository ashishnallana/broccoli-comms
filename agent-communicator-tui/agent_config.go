package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

type AgentConfig struct {
	Name         string   `json:"-"` // derived from parent directory name
	Directory    string   `json:"directory,omitempty"`
	AgentCommand string   `json:"agent-command"`
	AgentArgs    []string `json:"agent-args"`
	Description  string   `json:"description"`
}

// LoadAgentConfigs scans ~/.config/agent-communicator/agents/ for custom agent configs.
func LoadAgentConfigs() (map[string]AgentConfig, []string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, nil, err
	}

	agentsDir := filepath.Join(home, ".config", "agent-tracker", "agents")
	configs := make(map[string]AgentConfig)
	var keys []string

	// Ensure directory exists
	if err := os.MkdirAll(agentsDir, 0755); err != nil {
		return nil, nil, err
	}

	entries, err := os.ReadDir(agentsDir)
	if err != nil {
		return nil, nil, err
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		configPath := filepath.Join(agentsDir, entry.Name(), "config.json")
		file, err := os.ReadFile(configPath)
		if err != nil {
			continue // Skip invalid directories or directories without config.json
		}

		var cfg AgentConfig
		if err := json.Unmarshal(file, &cfg); err != nil {
			continue // Skip malformed JSON
		}

		cfg.Name = entry.Name()
		configs[cfg.Name] = cfg
		keys = append(keys, cfg.Name)
	}

	sort.Strings(keys)
	return configs, keys, nil
}
