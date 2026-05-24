package tracker

import (
	"context"
	"encoding/json"
	"net"
	"path/filepath"
	"testing"
	"time"
)

func fakeClient(t *testing.T, handler func(r rpcRequest) any) *Client {
	t.Helper()
	return &Client{
		SocketPath: "fake.sock",
		Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
			client, server := net.Pipe()
			go func() {
				defer server.Close()
				var req rpcRequest
				if err := json.NewDecoder(server).Decode(&req); err != nil {
					return
				}
				_ = json.NewEncoder(server).Encode(map[string]any{
					"jsonrpc": "2.0",
					"id":      req.ID,
					"result":  handler(req),
				})
			}()
			return client, nil
		},
	}
}

func TestDefaultSocketPathUsesBroccoliRuntimeDir(t *testing.T) {
	t.Setenv("AGENT_TRACKER_SOCKET", "")
	t.Setenv("BROCCOLI_COMMS_RUNTIME_DIR", "/tmp/broccoli-runtime")
	if got, want := DefaultSocketPath(), filepath.Join("/tmp/broccoli-runtime", "agent-tracker.sock"); got != want {
		t.Fatalf("DefaultSocketPath() = %q, want %q", got, want)
	}
}

func TestDefaultSocketPathPrefersExplicitAgentTrackerSocket(t *testing.T) {
	t.Setenv("AGENT_TRACKER_SOCKET", "/tmp/private/tracker.sock")
	t.Setenv("BROCCOLI_COMMS_RUNTIME_DIR", "/tmp/broccoli-runtime")
	if got := DefaultSocketPath(); got != "/tmp/private/tracker.sock" {
		t.Fatalf("DefaultSocketPath() = %q, want explicit socket", got)
	}
}

func TestListSetsAgentNamesFromMapKeys(t *testing.T) {
	client := fakeClient(t, func(req rpcRequest) any {
		if req.Method != "list" {
			t.Fatalf("method = %s, want list", req.Method)
		}
		return map[string]Agent{"alpha": {AgentID: "id-1", Status: "idle"}}
	})
	agents, err := client.List(context.Background())
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if agents["alpha"].Name != "alpha" || agents["alpha"].AgentID != "id-1" {
		t.Fatalf("agent = %+v", agents["alpha"])
	}
}

func TestWaitEventsUsesLongerSocketDeadlineAndFilters(t *testing.T) {
	client := fakeClient(t, func(req rpcRequest) any {
		if req.Method != "wait_events" {
			t.Fatalf("method = %s, want wait_events", req.Method)
		}
		params := req.Params.(map[string]any)
		if params["target_agent_id"] != "id-1" {
			t.Fatalf("target_agent_id = %v", params["target_agent_id"])
		}
		return WaitEventsResult{LastSeq: 7, Events: []Event{{Seq: 7, Type: "message_delivered"}}}
	})
	result, err := client.WaitEvents(context.Background(), WaitOptions{Since: 6, Timeout: 20 * time.Millisecond, TargetAgentID: "id-1"})
	if err != nil {
		t.Fatalf("WaitEvents: %v", err)
	}
	if result.LastSeq != 7 || len(result.Events) != 1 {
		t.Fatalf("result = %+v", result)
	}
}

func TestReadInbox(t *testing.T) {
	client := fakeClient(t, func(req rpcRequest) any {
		if req.Method != "get_inbox" {
			t.Fatalf("method = %s, want get_inbox", req.Method)
		}
		return ReadInboxResult{Mode: "history", Messages: []Message{{Sender: "agent", Body: "hi"}}}
	})
	inbox, err := client.ReadInbox(context.Background(), "alpha", 5, false)
	if err != nil || len(inbox.Messages) != 1 {
		t.Fatalf("ReadInbox = %+v, %v", inbox, err)
	}
}

func TestSendMessageUsesAgentNameForPlainLocalTarget(t *testing.T) {
	client := fakeClient(t, func(req rpcRequest) any {
		if req.Method != "send_message" {
			t.Fatalf("method = %s, want send_message", req.Method)
		}
		params := req.Params.(map[string]any)
		if params["agent_name"] != "alpha" || params["target_address"] != nil || params["agent_id"] != nil {
			t.Fatalf("params = %+v", params)
		}
		return true
	})
	if err := client.SendMessage(context.Background(), "alpha", "hello", nil); err != nil {
		t.Fatalf("SendMessage: %v", err)
	}
}

func TestSendMessageUsesTargetAddressForHostQualifiedTarget(t *testing.T) {
	client := fakeClient(t, func(req rpcRequest) any {
		params := req.Params.(map[string]any)
		if params["target_address"] != "host/alpha" || params["agent_name"] != nil {
			t.Fatalf("params = %+v", params)
		}
		return true
	})
	if err := client.SendMessage(context.Background(), "host/alpha", "hello", nil); err != nil {
		t.Fatalf("SendMessage: %v", err)
	}
}

func TestSendMessageFromIncludesSenderName(t *testing.T) {
	client := fakeClient(t, func(req rpcRequest) any {
		params := req.Params.(map[string]any)
		if params["sender_name"] != "agent-communicator" || params["agent_name"] != "alpha" {
			t.Fatalf("params = %+v", params)
		}
		return true
	})
	if err := client.SendMessageFrom(context.Background(), "agent-communicator", "alpha", "hello", nil); err != nil {
		t.Fatalf("SendMessageFrom: %v", err)
	}
}

func TestSendMessageUsesLocalTargetAddressForUUIDTarget(t *testing.T) {
	target := "123e4567-e89b-12d3-a456-426614174000"
	client := fakeClient(t, func(req rpcRequest) any {
		params := req.Params.(map[string]any)
		if params["target_address"] != "local/"+target || params["agent_id"] != nil {
			t.Fatalf("params = %+v", params)
		}
		return true
	})
	if err := client.SendMessage(context.Background(), target, "hello", nil); err != nil {
		t.Fatalf("SendMessage: %v", err)
	}
}

func TestCallHonorsContextCancellationAfterDial(t *testing.T) {
	client := &Client{
		SocketPath: "fake.sock",
		Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
			client, _ := net.Pipe()
			return client, nil
		},
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if err := client.SendMessage(ctx, "alpha", "hello", nil); err == nil {
		t.Fatal("SendMessage succeeded, want context cancellation error")
	}
}
