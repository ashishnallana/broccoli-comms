package tracker

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Client struct {
	SocketPath string
	Dial       func(ctx context.Context, network, address string) (net.Conn, error)
}

type rpcRequest struct {
	JSONRPC string `json:"jsonrpc"`
	Method  string `json:"method"`
	Params  any    `json:"params"`
	ID      int    `json:"id"`
}

type rpcResponse struct {
	Result json.RawMessage `json:"result"`
	Error  *rpcError       `json:"error"`
}

type rpcError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

type RPCErrorData struct {
	ErrorCode string `json:"error_code,omitempty"`
	Agent     string `json:"agent,omitempty"`
	Hostname  string `json:"hostname,omitempty"`
	Operation string `json:"operation,omitempty"`
	Retryable bool   `json:"retryable,omitempty"`
}

type RPCError struct {
	Method  string
	Code    int
	Message string
	Data    *RPCErrorData
}

func (e *RPCError) Error() string {
	return fmt.Sprintf("tracker rpc %s failed: %s", e.Method, e.Message)
}

func DefaultSocketPath() string {
	if path := os.Getenv("AGENT_TRACKER_SOCKET"); path != "" {
		return path
	}
	if runtimeDir := os.Getenv("BROCCOLI_COMMS_RUNTIME_DIR"); runtimeDir != "" {
		return filepath.Join(runtimeDir, "agent-tracker.sock")
	}
	cacheHome := os.Getenv("XDG_CACHE_HOME")
	if cacheHome == "" {
		home, err := os.UserHomeDir()
		if err != nil || home == "" {
			return filepath.Join(".cache", "agent-tracker", "agent-tracker.sock")
		}
		cacheHome = filepath.Join(home, ".cache")
	}
	return filepath.Join(cacheHome, "agent-tracker", "agent-tracker.sock")
}

func New(socketPath string) *Client {
	if socketPath == "" {
		socketPath = DefaultSocketPath()
	}
	return &Client{SocketPath: socketPath}
}

func (c *Client) call(ctx context.Context, method string, params any, timeout time.Duration, out any) error {
	if c.SocketPath == "" {
		return errors.New("tracker socket path is empty")
	}
	dial := c.Dial
	if dial == nil {
		d := net.Dialer{}
		dial = d.DialContext
	}
	conn, err := dial(ctx, "unix", c.SocketPath)
	if err != nil {
		return err
	}
	defer conn.Close()
	deadline := time.Time{}
	if timeout > 0 {
		deadline = time.Now().Add(timeout)
	}
	if ctxDeadline, ok := ctx.Deadline(); ok && (deadline.IsZero() || ctxDeadline.Before(deadline)) {
		deadline = ctxDeadline
	}
	if !deadline.IsZero() {
		_ = conn.SetDeadline(deadline)
	}
	stopCancelWatcher := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			_ = conn.SetDeadline(time.Now())
		case <-stopCancelWatcher:
		}
	}()
	defer close(stopCancelWatcher)
	if err := json.NewEncoder(conn).Encode(rpcRequest{JSONRPC: "2.0", Method: method, Params: params, ID: 1}); err != nil {
		return err
	}
	if unix, ok := conn.(*net.UnixConn); ok {
		_ = unix.CloseWrite()
	}
	respBytes, err := io.ReadAll(bufio.NewReader(conn))
	if err != nil {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return err
	}
	var resp rpcResponse
	if err := json.Unmarshal(respBytes, &resp); err != nil {
		return err
	}
	if resp.Error != nil {
		rpcErr := &RPCError{Method: method, Code: resp.Error.Code, Message: resp.Error.Message}
		if len(resp.Error.Data) > 0 {
			var data RPCErrorData
			if err := json.Unmarshal(resp.Error.Data, &data); err == nil {
				rpcErr.Data = &data
			}
		}
		return rpcErr
	}
	if out == nil {
		return nil
	}
	return json.Unmarshal(resp.Result, out)
}

func (c *Client) EnsureMailbox(ctx context.Context, agentName string) (EnsureMailboxResult, error) {
	var result EnsureMailboxResult
	err := c.call(ctx, "ensure_mailbox", map[string]any{"agent_name": agentName, "preserve_pane": true}, 5*time.Second, &result)
	return result, err
}

func (c *Client) List(ctx context.Context) (map[string]Agent, error) {
	agents := map[string]Agent{}
	if err := c.call(ctx, "list", map[string]any{}, 5*time.Second, &agents); err != nil {
		return nil, err
	}
	for name, agent := range agents {
		agent.Name = name
		agents[name] = agent
	}
	return agents, nil
}

func (c *Client) WaitEvents(ctx context.Context, opts WaitOptions) (WaitEventsResult, error) {
	if opts.Timeout == 0 {
		opts.Timeout = 25 * time.Second
	}
	params := map[string]any{"since": opts.Since, "timeout": opts.Timeout.Seconds()}
	if opts.TargetAgentID != "" {
		params["target_agent_id"] = opts.TargetAgentID
	}
	if opts.TargetAgentName != "" {
		params["target_agent_name"] = opts.TargetAgentName
	}
	var result WaitEventsResult
	err := c.call(ctx, "wait_events", params, opts.Timeout+5*time.Second, &result)
	return result, err
}

func (c *Client) ReadInbox(ctx context.Context, agentName string, last int, clear bool) (ReadInboxResult, error) {
	params := map[string]any{"agent_name": agentName, "clear": clear}
	if last > 0 {
		params["last_n"] = last
	}
	var result ReadInboxResult
	err := c.call(ctx, "get_inbox", params, 5*time.Second, &result)
	return result, err
}

func (c *Client) SendMessage(ctx context.Context, target, body string, attachments []Attachment) error {
	return c.SendMessageFrom(ctx, "", target, body, attachments)
}

func (c *Client) SendMessageFrom(ctx context.Context, senderName, target, body string, attachments []Attachment) error {
	return c.SendMessageWithID(ctx, senderName, target, body, "", attachments)
}

func (c *Client) SendMessageWithID(ctx context.Context, senderName, target, body, messageID string, attachments []Attachment) error {
	params := map[string]any{"message": body}
	if senderName != "" {
		params["sender_name"] = senderName
	}
	if messageID != "" {
		params["message_id"] = messageID
	}
	for key, value := range messageTargetParams(target) {
		params[key] = value
	}
	if len(attachments) > 0 {
		params["attachments"] = attachments
	}
	return c.call(ctx, "send_message", params, 10*time.Second, nil)
}

func (c *Client) SendText(ctx context.Context, target, text string, submit bool) error {
	params := map[string]any{"input_type": "text", "text": text, "submit": submit}
	for key, value := range directInputTargetParams(target) {
		params[key] = value
	}
	return c.call(ctx, "send_input", params, 10*time.Second, nil)
}

func (c *Client) SendKeys(ctx context.Context, target string, keys []string) error {
	params := map[string]any{"input_type": "keys", "keys": keys}
	for key, value := range directInputTargetParams(target) {
		params[key] = value
	}
	return c.call(ctx, "send_input", params, 10*time.Second, nil)
}

func messageTargetParams(target string) map[string]any {
	if strings.Contains(target, "/") {
		return map[string]any{"target_address": target}
	}
	if isUUID(target) {
		return map[string]any{"target_address": "local/" + target}
	}
	return map[string]any{"agent_name": target}
}

func directInputTargetParams(target string) map[string]any {
	if strings.Contains(target, "/") {
		return map[string]any{"target_address": target}
	}
	if isUUID(target) {
		return map[string]any{"agent_id": target}
	}
	return map[string]any{"agent_name": target}
}

func isUUID(value string) bool {
	if len(value) != 36 {
		return false
	}
	for i, r := range value {
		switch i {
		case 8, 13, 18, 23:
			if r != '-' {
				return false
			}
		default:
			if !(r >= '0' && r <= '9') && !(r >= 'a' && r <= 'f') && !(r >= 'A' && r <= 'F') {
				return false
			}
		}
	}
	return true
}

func (c *Client) ListTrackers(ctx context.Context) ([]RemoteTracker, error) {
	var trackers []RemoteTracker
	if err := c.call(ctx, "list_trackers", map[string]any{}, 10*time.Second, &trackers); err != nil {
		return nil, err
	}
	return trackers, nil
}

func (c *Client) PublishTrackerEvent(ctx context.Context, targetTrackerID, eventType string, payload any) error {
	params := map[string]any{
		"target_tracker_id": targetTrackerID,
		"event_type":        eventType,
		"payload":           payload,
	}
	return c.call(ctx, "publish_tracker_event", params, 10*time.Second, nil)
}
