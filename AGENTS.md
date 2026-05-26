# Workspace Tracking (AGENTS.md)

## Overview
- **Workspace ID**: `7473ae6d-06a8-444d-8a9f-c50788f3f465`
- **Last Updated**: `2026-05-26T15:27:00Z`
- **Goal**: Change the default tmux pane capture scrollback history lines limit from 25 to 20 inside both the Electron client and the background tracker python daemon.
- **Links**: [README.md](file:///usr/local/google/home/tanmayvijay/broccoli-comms/README.md)

## Active Agents
| Agent ID | Agent Name | Role / Purpose | Process Info | Status | Last Active |
|---|---|---|---|---|---|
| b58eb4c9-7601-4038-b3af-eb73f99ae069 | home-manager-core-agent-1 | Systems & UI Developer | Pane %1 | Working | 2026-05-26T15:27:00Z |

## Task Allocation & Progress
| Task ID | Description | Assigned Agent ID | Status | Priority | Dependencies | Notes / Artifacts |
|---|---|---|---|---|---|---|
| task-01 | Change default capture lines to 20 in trackerClient.ts | b58eb4c9-7601-4038-b3af-eb73f99ae069 | In Progress | P0 | | Code updates |
| task-02 | Update trackerClient.test.ts unit tests mock assertions to expect 20 lines | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Pending | P0 | task-01 | Test updates |
| task-03 | Change DEFAULT_CAPTURE_PANE_LINES to 20 in agent-tracker/ctl_commands/common.py | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Pending | P0 | task-02 | Daemon updates |
| task-04 | Verify tsc compilers and Vitest tests pass successfully | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Pending | P0 | task-03 | Compiler check |
| task-05 | Commit all modifications to main branch | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Pending | P0 | task-04 | Committed to main branch |

## Active Blockers & Dependencies
| Blocked Agent ID | Blocked Task ID | Blocking Task ID | Blocking Agent ID | Reason |
|---|---|---|---|---|
| None | | | | |

## Decisions & Design Notes Log
- **2026-05-26T15:27:00Z** [tanmayvijay]: DECISION: Approved changing default scrollback capture lines limit from 25 to 20 inside Electron and Daemon to optimize payload sizes.

## Running the Electron App

The React-based Electron desktop UI resolves its tracker socket using the `AGENT_TRACKER_SOCKET` environment variable. This allows you to connect the exact same desktop interface to different backend tracking services.

### 1. Running with Broccoli Comms Private Services
To run the Electron app against `broccoli-comms`' own isolated background services, start the private services first, then run Electron with the private socket location:
```bash
# 1. Start private tmux server and tracker daemon
broccoli-comms start

# 2. Launch Electron app in development mode
cd agent-communicator-electron
AGENT_TRACKER_SOCKET=$XDG_RUNTIME_DIR/broccoli-comms/agent-tracker.sock npm run dev
```

### 2. Running with Existing Home-Manager-Core Services
To use the desktop interface to control your active global `home-manager-core` agent sessions, simply point the socket variable to the default cache socket:
```bash
cd agent-communicator-electron
AGENT_TRACKER_SOCKET=~/.cache/agent-tracker/agent-tracker.sock npm run dev
```

### 3. Running in Mock / Developer Mode
If you want to explore or develop the UI without running any active backend services or socket daemons, run:
```bash
cd agent-communicator-electron
npm run dev
```

### 4. Advanced Remote Registry Setup (Mac-to-Linux Routing)
To run the Electron app on your Mac and route remote pane captures or direct input deliveries back to your desktop mailbox without colliding with pre-existing global `home-manager-core` services, use the following working setup:

#### A. Sync Latest Code to Mac Host
Execute `rsync` from your Mac terminal to pull the latest mailbox publishability fixes:
```bash
rsync -avz --exclude '.git' --exclude 'node_modules' --exclude 'out' \
  tanmayvijay@tanmayvijay.c.googlers.com:/usr/local/google/home/tanmayvijay/broccoli-comms/ \
  /Users/tanmayvijay/broccoli-comms/
```

#### B. Launch Daemon with Dedicated Hostname
Launch your private Broccoli Comms tracker using a custom `AGENT_TRACKER_HOSTNAME` to isolate its registry endpoints:
```bash
cd /Users/tanmayvijay/broccoli-comms
XDG_RUNTIME_DIR=/tmp nix run .#broccoli-comms -- stop || true

AGENT_TRACKER_HOSTNAME='tanmayvijay-mac-broccoli' \
AGENT_REGISTRIES_JSON='[{"name":"local","url":"http://127.0.0.1:18000"},{"name":"mundus","url":"https://agents.mundus.in"}]' \
XDG_RUNTIME_DIR=/tmp nix run .#broccoli-comms -- start
```

#### C. Launch Electron connected to Custom Hostname
Spin up the desktop interface targeting the private socket and isolated hostname:
```bash
cd /Users/tanmayvijay/broccoli-comms/agent-communicator-electron
AGENT_TRACKER_SOCKET=/tmp/broccoli-comms/agent-tracker.sock \
AGENT_TRACKER_HOSTNAME='tanmayvijay-mac-broccoli' \
npm run dev
```

#### D. Optional: Spin a Local Capture Agent
To create a local mock agent target for validating pane-capture scrollbacks:
```bash
cd /Users/tanmayvijay/broccoli-comms
XDG_RUNTIME_DIR=/tmp nix run .#broccoli-comms -- agent add local-capture --cwd /Users/tanmayvijay/broccoli-comms --command 'pi'

AGENT_TRACKER_HOSTNAME='tanmayvijay-mac-broccoli' \
AGENT_REGISTRIES_JSON='[{"name":"local","url":"http://127.0.0.1:18000"},{"name":"mundus","url":"https://agents.mundus.in"}]' \
XDG_RUNTIME_DIR=/tmp nix run .#broccoli-comms -- start
```

#### E. Registry Validation Checks
Verify that the mailbox is globally addressable and connected:
* Running `agent-tracker-ctl registry-status` should show `local + mundus` connected (`●`).
* Querying the local endpoint `curl http://127.0.0.1:18000/agents | jq` should show the hostname `tanmayvijay-mac-broccoli` and the mailbox agent `agent-communicator`.
* Querying the remote endpoint `curl https://agents.mundus.in/agents | jq` should show `tanmayvijay-mac-broccoli/agent-communicator` successfully published!

---

## Key Artifacts & Links
- Repository: [broccoli-comms/](file:///usr/local/google/home/tanmayvijay/broccoli-comms/)
- Redesign Specification: [redesign.html](file:///usr/local/google/home/tanmayvijay/broccoli-comms/redesign.html)
- Shortcuts Panel: [ShortcutsPanel.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/ShortcutsPanel.tsx)
- Command Palette: [CommandPalette.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/CommandPalette.tsx)
- Main Redesigned Stylesheet: [styles.css](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/styles.css)
- Markdown Renderer Component: [MessageBubble.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/MessageBubble.tsx)
- Launch Agent Dialog: [LaunchAgentModal.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/LaunchAgentModal.tsx)
