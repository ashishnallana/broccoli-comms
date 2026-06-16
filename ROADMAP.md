# Broccoli Comms Roadmap

## Product direction

Broccoli Comms is a standalone agent communication app. It should not depend on a user's Home Manager setup, tmux config, shell hooks, or existing tmux sessions.

The app owns:

- private tmux server/socket
- private agent-tracker daemon/socket
- managed agent windows/panes
- terminal TUI today
- possible native/desktop UI later

Design implication: keep the runtime/API layer UI-agnostic. The TUI and any future native UI should talk to the same local runtime/control API.

## Phase chunks

### Chunk 1: private runtime smoke test and lifecycle hardening

Goal: prove `broccoli-comms start/status/stop` works end-to-end with no user tmux dependency.

Tasks:

- Add a smoke test script for private runtime lifecycle.
- Use isolated temp runtime/cache/config directories.
- Start private tracker and private tmux.
- Verify private tmux session exists via explicit socket.
- Verify tracker socket responds.
- Stop runtime and verify cleanup.
- Document known limitations.

### Chunk 2: private tmux/socket consistency audit

Goal: ensure copied tracker/wrapper code never accidentally controls the user's default tmux server in app mode.

Tasks:

- Audit `agent-tracker/tmux_util.py`, `tmux_reliability.py`, `rpc_handler.py`, wrapper, and launcher.
- Add app env var / config plumbing where needed.
- Prefer explicit socket args in all tmux calls.
- Add tests around socket usage where feasible.

### Chunk 3: managed agents API/CLI

Goal: make configured agents first-class.

Tasks:

- Define config schema.
- Add agent subcommands: list/add/remove/restart.
- Reconcile configured agents into private tmux windows.
- Avoid duplicates after restart.

### Chunk 4: UI/runtime boundary

Goal: prepare for both terminal TUI and a possible future native UI.

Tasks:

- Define a stable local runtime API contract.
- Keep UI-specific behavior outside tracker core.
- Add health/status JSON suitable for TUI and future desktop UI.

## Current assignment

- Coder: Chunk 1 implementation.
- Reviewer: Review Chunk 1 after coder reports completion.
- Lead: coordinate phases, run validation, commit approved chunks.
