# Implementation Plan: Local Daemon Group Timeline Cache & Tracker Caches

- **Date**: 2026-05-26
- **Author**: `coding-agent` (via local socket)
- **Status**: Proposed Architectural Implementation Plan

---

## Goal
Implement a persistent local group timeline cache inside the tracker daemon filesystem (`~/.cache/`) and expose an RPC query layer, replacing client-side React calculations with persistent, high-performance daemon-level history.

---

## Milestone 1: Local Daemon Group Timeline Cache & RPC (Phases 1 & 2)

### Objective
Implement local persistent storage and RPC query layers for group timelines inside the `agent-tracker` daemon.

### Tasks:
1. **Observed Group Tracking (`state.py`)**:
   - Implement idempotent tracking of group message observations in daemon memory.
   - Group records: `state.group_timelines[group_id] = { name, member_ids, messages: List[Message] }`
2. **Persistent Local Cache**:
   - Persist group timelines to the host filesystem:
     `~/.cache/broccoli-comms/agent-tracker/group_timelines/<group_id_hash>.jsonl`
   - Dynamically read and write JSONL records on message delivery and daemon startups.
3. **Timeline RPC Query (`rpc_handler.py`)**:
   - Implement the new RPC method: `get_group_timeline(group_id, cursor?, limit?)`.
   - Return canonical, deduplicated message lists chronologically.

### Verification:
- Python unit tests verifying timeline retrieval, message deduplication, and disk persistence across daemon restarts.

---

## Milestone 2: Active & Remote Delegated Group Watch Leases (Phases 3 & 4)

### Objective
Establish lease-bound active group watches and registry-delegated watch propagation for hostname groups.

### Tasks:
1. **Active Group Watches**:
   - Extend local watchlist state to support active group watches with automatic TTL lease expirations.
2. **Delegated Watch Routing**:
   - Implement delegated `watch_group_request` registry routing for remote hostname groups.
3. **Remote Event Handler**:
   - Handle fanned-out `group_message_observed` registry events and write them to the local daemon group timeline cache.

### Verification:
- Unit tests validating local captures, remote delegated round-trips, and lease-bound auto-expirations.

---

## Milestone 3: Electron App Integration & UI Upgrades (Phase 5)

### Objective
Connect the new group timeline cache API to the Electron React desktop UI.

### Tasks:
1. **Contracts Upgrade**:
   - Register `listGroupMessages(groupId)` contract in `contracts.ts` and `trackerClient.ts` querying `get_group_timeline`.
2. **App Hooks Refactoring**:
   - Refactor React hooks in `App.tsx` to establish active group watches and fetch timelines directly via the new API.
3. **Backward Compatibility**:
   - Ensure graceful degraded fallbacks for older daemons (falling back to client-side React aggregation if the RPC is missing).

### Verification:
- Zero `npm run typecheck` compilation errors.
- All Vitest unit tests pass cleanly.
- Successful manual validation of persistent history across app restarts.
