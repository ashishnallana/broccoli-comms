# Workspace Tracking (AGENTS.md)

## Overview
- **Workspace ID**: `7473ae6d-06a8-444d-8a9f-c50788f3f465`
- **Last Updated**: `2026-06-02T10:45:00Z`
- **Goal**: Implement independent message rendering and ensure key local agents like zv2 are never hidden.
- **Links**: [README.md](file:///usr/local/google/home/tanmayvijay/broccoli-comms/README.md)

## Active Agents
| Agent ID | Agent Name | Role / Purpose | Process Info | Status | Last Active |
|---|---|---|---|---|---|
| b58eb4c9-7601-4038-b3af-eb73f99ae069 | home-manager-core-agent-1 | Systems & Events Developer | Pane %1 | Idle | 2026-05-26T18:46:00Z |
| ef242aad-c44f-4498-9d6d-47ba7986e93d | coding-agent | Expert Software Coding Engineer | Pane %4 | Idle | 2026-05-27T00:18:00Z |
| a47b9496-cf73-4a2b-b0d8-6950f8fd83f1 | otel-difftest-agent-1 | TUI & Systems Interface Developer | Pane %0 | Working | 2026-06-02T10:45:00Z |

## Task Allocation & Progress
| Task ID | Description | Assigned Agent ID | Status | Priority | Dependencies | Notes / Artifacts |
|---|---|---|---|---|---|---|
| task-01 | Refine and finalize v2 Design and Phased Implementation Plan | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Completed | P0 | | [Plan](file:///usr/local/google/home/tanmayvijay/.gemini/jetski/brain/7473ae6d-06a8-444d-8a9f-c50788f3f465/implementation_plan_push_events.md) |
| task-02 | Dispatch Phase A, B, C Coding instructions | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Completed | P0 | task-01 | send-message delivered |
| task-03 | Implement Phase A, B, C Push-Only wait_events, remote leases, & auth gates | ef242aad-c44f-4498-9d6d-47ba7986e93d | Completed | P0 | task-02 | Upgraded rpc_handler.py & server.py |
| task-04 | Dispatch Group Cache deconstructed Milestone Plan | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Completed | P0 | task-03 | send-message delivered |
| task-05 | Implement Milestone 1, 2, 3 Group Caches & dynamic visual channels | ef242aad-c44f-4498-9d6d-47ba7986e93d | Completed | P0 | task-04 | Upgraded state.py, App.tsx, & ipc.ts |
| task-06 | Dispatch Message Ungrouping coding task | b58eb4c9-7601-4038-b3af-eb73f99ae069 | Completed | P0 | task-05 | send-message delivered |
| task-07 | Implement independent message rendering (disable grouping) in React | ef242aad-c44f-4498-9d6d-47ba7986e93d | Completed | P0 | task-06 | Completely disabled grouping logic in ConversationView.tsx and verified initials rendering in MessageBubble.tsx |
| task-08 | Implement Tokyo Night truecolor theme in agent-communicator-tui | ef242aad-c44f-4498-9d6d-47ba7986e93d | Completed | P0 | | [theme.go](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-tui/theme.go) |
| task-09 | Ensure zv2-agent is unhidden & show hidden visual indicator | a47b9496-cf73-4a2b-b0d8-6950f8fd83f1 | Completed | P0 | | Overrode `isHiddenAgent`, added `◌` indicator, synced locks |

## Active Blockers & Dependencies
| Blocked Agent ID | Blocked Task ID | Blocking Task ID | Blocking Agent ID | Reason |
|---|---|---|---|---|
| None | | | | |

## Decisions & Design Notes Log
- **2026-05-26T17:12:00Z** [tanmayvijay]: DECISION: Approved auto-creating Hostname-based Group Channels to dynamically group agents registered on the same machine.
- **2026-05-26T18:10:00Z** [tanmayvijay]: DECISION: Approved deconstructed 3-Milestone plan for persistent daemon group timeline caches.
- **2026-05-26T18:46:00Z** [tanmayvijay]: DECISION: Approved disabling consecutive message grouping to render each message independently with its own full avatar and time headers.
- **2026-06-02T04:14:00Z** [ef242aad-c44f-4498-9d6d-47ba7986e93d]: DECISION: Patched NameError in agent-tracker/rpc_handler.py by replacing deprecated _identify_sender with safe _identify_agent call. - REASON: Essential fix to restore Nix flake build sanity and allow verification of TUI communicator tests.
- **2026-06-02T04:15:00Z** [ef242aad-c44f-4498-9d6d-47ba7986e93d]: DECISION: Customize TUI colors with standard Tokyo Night Storm hex values, isolating hex literals in theme.go to comply with TestNoRawHexColorsOutsideThemeFile. - REASON: Adheres to TUI styling rules while bringing a truecolor modern terminal theme.
- **2026-06-02T04:16:00Z** [ef242aad-c44f-4498-9d6d-47ba7986e93d]: DECISION: Reorder AgentColors array and adjust TextSubtle/Muted contrast in theme.go. - REASON: Corrects border color collisions under TestOutgoingAndIncomingUseDifferentBorderColors and matches WCAG AA guidelines for optimal terminal contrast and readability.
- **2026-06-02T10:45:00Z** [a47b9496-cf73-4a2b-b0d8-6950f8fd83f1]: DECISION: Overrode isHiddenAgent in agent-communicator-tui/hidden_agents.go to fundamentally return false for any agent starting with "zv2", preventing them from ever being hidden. Synced Nix locks across all home-manager dependencies.

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

## Local Development & Testing Workarounds (Bypassing Nix Store)

To iterate rapidly on local modifications without having to run a global `home-manager switch` or overwrite system packages, you can point the runtime variables directly to your local workspace:

### 1. Running local edits of the Tracker Daemon
The standard `broccoli-comms start` script launches the pre-compiled, read-only tracker daemon from the Nix store. To bypass this and execute your local workspace Python edits:
```bash
# Stop any currently running background daemon
python3 app/broccoli-comms.py stop

# Start the daemon pointing explicitly to your local workspace tracker script
BROCCOLI_COMMS_AGENT_TRACKER=/usr/local/google/home/tanmayvijay/broccoli-comms/agent-tracker/agent-tracker.py \
python3 app/broccoli-comms.py start
```

### 2. Running local edits of the Go TUI (agent-communicator)
To test local Go TUI styling/rendering edits immediately without global recompilation:
```bash
# 1. Compile the Go TUI locally inside the sandboxed Nix environment
nix build .#agentCommunicator

# 2. Run the communicator UI pointing explicitly to your new locally compiled binary
BROCCOLI_COMMS_AGENT_COMMUNICATOR_TUI=/usr/local/google/home/tanmayvijay/broccoli-comms/result/bin/agent-communicator \
broccoli-comms ui
```

---

## Key Artifacts & Links
- Repository: [broccoli-comms/](file:///usr/local/google/home/tanmayvijay/broccoli-comms/)
- Redesign Specification: [redesign.html](file:///usr/local/google/home/tanmayvijay/broccoli-comms/redesign.html)
- Shortcuts Panel: [ShortcutsPanel.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/ShortcutsPanel.tsx)
- Command Palette: [CommandPalette.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/CommandPalette.tsx)
- Main Redesigned Stylesheet: [styles.css](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/styles.css)
- Markdown Renderer Component: [MessageBubble.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/MessageBubble.tsx)
- Launch Agent Dialog: [LaunchAgentModal.tsx](file:///usr/local/google/home/tanmayvijay/broccoli-comms/agent-communicator-electron/src/renderer/components/LaunchAgentModal.tsx)
- Refined v2 Push Updates Design: [push_updates_design_proposal_v2.md](file:///usr/local/google/home/tanmayvijay/.gemini/jetski/brain/7473ae6d-06a8-444d-8a9f-c50788f3f465/push_updates_design_proposal_v2.md)
- Detailed Phased Implementation Plan: [implementation_plan_push_events.md](file:///usr/local/google/home/tanmayvijay/.gemini/jetski/brain/7473ae6d-06a8-444d-8a9f-c50788f3f465/implementation_plan_push_events.md)
- Zero-Knowledge VPS Managed Registry Design: [managed_registry_security_design.md](file:///usr/local/google/home/tanmayvijay/.gemini/jetski/brain/7473ae6d-06a8-444d-8a9f-c50788f3f465/managed_registry_security_design.md)
- Deconstructed Group Cache Plan: [group_cache_implementation_plan.md](file:///usr/local/google/home/tanmayvijay/broccoli-comms/group_cache_implementation_plan.md)
