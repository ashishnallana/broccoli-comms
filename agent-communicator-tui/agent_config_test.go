package main

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestLoadAgentConfigs(t *testing.T) {
	// Create a temp dir for the test
	tempDir, err := os.MkdirTemp("", "agent-communicator-test-home")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	// Keep original HOME and restore at the end of the test
	origHome := os.Getenv("HOME")
	defer os.Setenv("HOME", origHome)

	// Set HOME to tempDir so os.UserHomeDir uses it
	os.Setenv("HOME", tempDir)

	// Create the config folder structure
	agentsDir := filepath.Join(tempDir, ".config", "agent-tracker", "agents")
	err = os.MkdirAll(agentsDir, 0755)
	if err != nil {
		t.Fatalf("failed to create agents dir: %v", err)
	}

	// Create config 1: jetski
	jetskiDir := filepath.Join(agentsDir, "jetski")
	err = os.MkdirAll(jetskiDir, 0755)
	if err != nil {
		t.Fatalf("failed to create jetski dir: %v", err)
	}
	err = os.WriteFile(filepath.Join(jetskiDir, "config.json"), []byte(`{
		"directory": "/path/to/project",
		"agent-command": "jetski",
		"agent-args": ["-p", "hello world"],
		"description": "Jetski description"
	}`), 0644)
	if err != nil {
		t.Fatalf("failed to write jetski config: %v", err)
	}

	// Create config 2: pi
	piDir := filepath.Join(agentsDir, "pi")
	err = os.MkdirAll(piDir, 0755)
	if err != nil {
		t.Fatalf("failed to create pi dir: %v", err)
	}
	err = os.WriteFile(filepath.Join(piDir, "config.json"), []byte(`{
		"agent-command": "pi",
		"agent-args": ["--model", "gemini-pro"],
		"description": "Pi description"
	}`), 0644)
	if err != nil {
		t.Fatalf("failed to write pi config: %v", err)
	}

	// Create non-config folder (should be ignored)
	ignoredDir := filepath.Join(agentsDir, "ignored-empty-folder")
	err = os.MkdirAll(ignoredDir, 0755)
	if err != nil {
		t.Fatalf("failed to create ignored dir: %v", err)
	}

	// Call LoadAgentConfigs
	configs, keys, err := LoadAgentConfigs()
	if err != nil {
		t.Fatalf("unexpected error in LoadAgentConfigs: %v", err)
	}

	// Expected configurations
	expectedConfigs := map[string]AgentConfig{
		"jetski": {
			Name:         "jetski",
			Directory:    "/path/to/project",
			AgentCommand: "jetski",
			AgentArgs:    []string{"-p", "hello world"},
			Description:  "Jetski description",
		},
		"pi": {
			Name:         "pi",
			AgentCommand: "pi",
			AgentArgs:    []string{"--model", "gemini-pro"},
			Description:  "Pi description",
		},
	}

	expectedKeys := []string{"jetski", "pi"}

	if !reflect.DeepEqual(configs, expectedConfigs) {
		t.Errorf("configs got %v; want %v", configs, expectedConfigs)
	}

	if !reflect.DeepEqual(keys, expectedKeys) {
		t.Errorf("keys got %v; want %v", keys, expectedKeys)
	}
}
