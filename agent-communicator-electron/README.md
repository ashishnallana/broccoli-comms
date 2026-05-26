# Broccoli Comms Electron Mock

Dev-only Electron + Vite + React + TypeScript mock app for exploring a desktop Agent Communicator UX before wiring real Broccoli Comms services.

## Mock-only boundary

This app is intentionally self-contained:

- Uses deterministic fixture data from `src/test/fixtures.ts`.
- Does **not** connect to `agent-tracker`, `agent-registry`, tmux, `broccoli-comms start`, sockets, HTTP sidecars, or any running service.
- Does **not** persist state beyond in-memory mock runtime data for the current app session.
- Does **not** package via Nix, sign Electron artifacts, or replace the terminal TUI.
- Direct Text / Direct Keys are mock pane-control affordances only and are disabled for remote fixture agents.

## Install and run

```sh
cd /home/tanmay/projects/nix/broccoli-comms-electron-worktree/agent-communicator-electron
npm install
npm run dev
```

`npm run dev` opens a mock Electron window with runtime health, local/remote fixture agents, conversation history, normal message sending, and mocked direct action modes.

## Validation

```sh
npm run typecheck
npm run build
```

No test runner is configured yet, so there is no `npm test` script.

## npm scripts

- `npm run dev` — launch the Electron mock with Vite dev tooling.
- `npm run typecheck` — run TypeScript validation with `tsc --noEmit`.
- `npm run build` — run typecheck, then build Electron main/preload/renderer bundles.

## Fixture data

Mock runtime data lives in `src/test/fixtures.ts`:

- `mockRuntimeStatus` — simulated runtime/tracker/registry/tmux health chips and notes.
- `mockAgents` — local and remote fixture agents, statuses, cwd/project metadata, unread counts, target addresses, tags, and direct-control eligibility.
- `mockMessages` — deterministic conversation timelines keyed by stable target address.

Stable conversation keys intentionally mirror the TUI rule `conversationKey(row) == rowTarget(row)`: use target address when present, otherwise the agent name.

## Current UX chunks

### E1 scaffold

- Electron + electron-vite + React + TypeScript scaffold.
- Narrow preload IPC surface and shared runtime contracts in `src/shared/`.
- Renderer talks to `CommunicatorRuntimeClient` instead of shelling out or knowing service internals.

### E2 app shell and agent list

- Dev-only sidebar and runtime health chips.
- Grouped local/remote fixture agents.
- Search/filtering, total/unread counts, group empty states.
- Status, cwd, address, scope labels, direct-control lock labels, unread clearing on selection, and offline-state visuals.

### E3 conversation timeline and normal composer

- Inbound/outbound/system message bubbles with author, timestamp, direction styling, and delivery state labels.
- Normal Message mode appends an optimistic outbound `sending` bubble and replaces it with a delayed `delivered` mock result.
- Electron IPC and renderer fallback mock clients both persist sent mock messages for the session.

### E4 direct pane-control mock modes

- Composer mode picker exposes Message, Direct Text, and Direct Keys.
- Direct modes use amber warning styling and explicit pane-control warning banners.
- Remote fixture agents keep direct modes disabled/locked with UI and submit backstops.
- Direct actions call only mock direct-action APIs, show transient status, and do not append normal conversation history.

### E5 polish and documentation

- This README documents the mock-only boundary, commands, fixture data, current UX behavior, and future integration path.
- The in-app details pane includes a compact mock boundary checklist for quick visual confirmation.

## Project structure

```text
agent-communicator-electron/
├── package.json
├── electron.vite.config.ts
├── index.html
├── src/
│   ├── main/                  # Electron lifecycle and mock IPC handlers
│   ├── shared/                # Runtime contracts and IPC channel constants
│   ├── renderer/              # React UI, feature helpers, styles
│   └── test/fixtures.ts       # Deterministic mock runtime/agent/message data
└── README.md
```

## Future integration notes

The renderer consumes `CommunicatorRuntimeClient`; it does not shell out and does not know tmux, tracker socket, or registry details. A future integration can replace the mock runtime/preload handlers with a real main-process adapter that maps the same contract to Broccoli runtime APIs, for example:

- runtime/status commands or local daemon APIs for runtime health
- tracker APIs for agent lists and inbox messages
- guarded local-only pane-control APIs for Direct Text / Direct Keys
- registry-aware remote messaging APIs once remote guardrails exist

Until that integration work is explicitly requested, this directory should remain a dev-only mock app in the isolated worktree.
