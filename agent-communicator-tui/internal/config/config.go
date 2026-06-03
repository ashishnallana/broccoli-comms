package config

import (
	"os"
	"path/filepath"
	"sync"

	"github.com/pelletier/go-toml/v2"
)

var (
	configCache map[string]interface{}
	once        sync.Once
)

func Load() {
	once.Do(func() {
		configCache = make(map[string]interface{})
		configHome := os.Getenv("XDG_CONFIG_HOME")
		if configHome == "" {
			home, err := os.UserHomeDir()
			if err == nil {
				configHome = filepath.Join(home, ".config")
			}
		}
		if configHome != "" {
			configPath := filepath.Join(configHome, "broccoli-comms", "config.toml")
			data, err := os.ReadFile(configPath)
			if err == nil {
				var parsed map[string]interface{}
				if err := toml.Unmarshal(data, &parsed); err == nil {
					configCache = parsed
				}
			}
		}
	})
}

// GetString gets a string value from the TOML config. Sections are passed as variadic keys.
func GetString(fallback string, keys ...string) string {
	Load()
	var current interface{} = configCache
	for _, key := range keys {
		if m, ok := current.(map[string]interface{}); ok {
			current = m[key]
		} else {
			return fallback
		}
	}
	if v, ok := current.(string); ok {
		return v
	}
	return fallback
}

// GetInt gets an integer value from the TOML config.
func GetInt(fallback int, keys ...string) int {
	Load()
	var current interface{} = configCache
	for _, key := range keys {
		if m, ok := current.(map[string]interface{}); ok {
			current = m[key]
		} else {
			return fallback
		}
	}
	switch v := current.(type) {
	case int:
		return v
	case int64:
		return int(v)
	case float64:
		return int(v)
	}
	return fallback
}

// GetBool gets a boolean value from the TOML config.
func GetBool(fallback bool, keys ...string) bool {
	Load()
	var current interface{} = configCache
	for _, key := range keys {
		if m, ok := current.(map[string]interface{}); ok {
			current = m[key]
		} else {
			return fallback
		}
	}
	if v, ok := current.(bool); ok {
		return v
	}
	return fallback
}

// ResetForTest clears the configuration cache so it can be reloaded in tests.
func ResetForTest() {
	once = sync.Once{}
	configCache = nil
}
