package registry

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestListAgentsParsesRegistryResponseAndSendsAuth(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/agents" {
			t.Fatalf("path = %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer secret" {
			t.Fatalf("Authorization = %q", r.Header.Get("Authorization"))
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"agents": []Agent{{
			AgentID:  "id-1",
			Name:     "alpha",
			Hostname: "host-a",
			Status:   "idle",
			CWD:      "/repo",
		}}})
	}))
	defer server.Close()

	client := New(server.URL+"/", "secret")
	agents, err := client.ListAgents(context.Background())
	if err != nil {
		t.Fatalf("ListAgents: %v", err)
	}
	if len(agents) != 1 || agents[0].Name != "alpha" || agents[0].CWD != "/repo" {
		t.Fatalf("agents = %+v", agents)
	}
}

func TestListAgentsEmptyBaseURLReturnsEmpty(t *testing.T) {
	agents, err := New("", "").ListAgents(context.Background())
	if err != nil {
		t.Fatalf("ListAgents: %v", err)
	}
	if len(agents) != 0 {
		t.Fatalf("agents = %+v, want empty", agents)
	}
}

func TestListAgentsReportsNonOKStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "nope", http.StatusUnauthorized)
	}))
	defer server.Close()
	if _, err := New(server.URL, "bad").ListAgents(context.Background()); err == nil {
		t.Fatal("ListAgents succeeded, want error")
	}
}
