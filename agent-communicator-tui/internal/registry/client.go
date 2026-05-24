package registry

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Agent struct {
	AgentID   string   `json:"agent_id"`
	Name      string   `json:"name"`
	Aliases   []string `json:"aliases"`
	TrackerID string   `json:"tracker_id"`
	Hostname  string   `json:"hostname"`
	Status    string   `json:"status"`
	AgentType string   `json:"agent_type"`
	AgentCmd  string   `json:"agent_cmd"`
	LastSeen  float64  `json:"last_seen"`
	CWD       string   `json:"cwd,omitempty"`
}

type Client struct {
	BaseURL    string
	Token      string
	HTTPClient *http.Client
}

func New(baseURL, token string) *Client {
	return &Client{BaseURL: strings.TrimRight(baseURL, "/"), Token: token}
}

func (c *Client) ListAgents(ctx context.Context) ([]Agent, error) {
	return c.listAgents(ctx, url.Values{})
}

func (c *Client) listAgents(ctx context.Context, query url.Values) ([]Agent, error) {
	if c.BaseURL == "" {
		return nil, nil
	}
	endpoint := c.BaseURL + "/agents"
	if encoded := query.Encode(); encoded != "" {
		endpoint += "?" + encoded
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	client := c.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("registry list agents failed: HTTP %d", resp.StatusCode)
	}
	var payload struct {
		Agents []Agent `json:"agents"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}
	return payload.Agents, nil
}

func (c *Client) SaveAgent(ctx context.Context, agentToSave, agentName, command, description, cwd string) error {
	if c.BaseURL == "" {
		return fmt.Errorf("registry URL not configured")
	}
	endpoint := c.BaseURL + "/save-agent"
	payload := map[string]string{
		"agent_to_save": agentToSave,
	}
	if agentName != "" {
		payload["agent_name"] = agentName
	}
	if command != "" {
		payload["command"] = command
	}
	if description != "" {
		payload["description"] = description
	}
	if cwd != "" {
		payload["cwd"] = cwd
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(string(body)))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	client := c.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("registry save agent failed: HTTP %d", resp.StatusCode)
	}
	return nil
}
