# Broccoli Comms Migration Plan

## Goal

Create a standalone agent communication app that owns its own tmux runtime and UI, without requiring the user's Home Manager or tmux setup.

## Desired user flow

```sh
broccoli-comms
```

The app should start a private runtime, reconcile configured agents, and open the communicator UI.

## Current initial extraction

Copied into this repo:

- `agent-tracker/`: daemon, JSON-RPC, CLI, inbox/event store, tmux helpers, registry client
- `agent-communicator-tui/`: existing Go TUI
- `agent-registry/`: registry server and managed-agent code
- `wrapper/agent-wrapper.sh`: first standalone wrapper script
- `app/broccoli-comms.py`: first standalone launcher/supervisor

Added:

- `flake.nix` with packages/apps
- `Makefile` for non-Nix builds
- `README.md`

## Target architecture

```text
broccoli-comms
├── app launcher/supervisor
├── private tmux server
├── private agent-tracker daemon
├── managed agent panes/windows
├── agent-wrapper
└── agent-communicator UI
```

## Phase 1: bootstrap standalone runtime

Status: started.

Tasks:

- [x] create `~/projects/nix/broccoli-comms`
- [x] copy `agent-tracker`
- [x] copy `agent-communicator-tui`
- [x] copy `agent-registry`
- [x] add standalone `agent-wrapper.sh`
- [x] add `broccoli-comms.py` launcher
- [x] add flake package outputs
- [x] add non-Nix Makefile
- [ ] validate `nix flake check`
- [ ] validate `make check`
- [ ] validate `broccoli-comms start/status/stop`

## Phase 2: harden app-private runtime

Tasks:

- Use app-private `XDG_CACHE_HOME`/state paths consistently.
- Ensure no code assumes `~/.cache/agent-tracker` when app env is set.
- Ensure all tmux commands use the private socket.
- Add robust stale socket and stale tmux-server cleanup.
- Add log files for tracker, tmux launch, and managed agents.
- Add `broccoli-comms doctor` checks for `tmux`, `python3`, agent commands, writable dirs, and socket reachability.

## Phase 3: managed agents

Tasks:

- Define stable config schema.
- Add commands:
  - `broccoli-comms agent list`
  - `broccoli-comms agent add`
  - `broccoli-comms agent remove`
  - `broccoli-comms agent restart`
- Reconcile desired agents into private tmux windows/panes.
- Avoid duplicate agents after restart.
- Persist managed-agent metadata.

## Phase 4: UI integration

Tasks:

- Make `agent-communicator-tui` app-aware.
- Show runtime health and managed-agent state.
- Add attach/open-pane affordances.
- Add private tmux capture/focus actions.
- Later: add global advanced view over all app-managed inboxes.

## Phase 5: packaging

Tasks:

- Finalize flake package names.
- Add checks for Python syntax, Go tests, launcher smoke tests.
- Add install docs:
  - `nix run`
  - `nix profile install`
  - non-Nix `make install`
- Decide whether `agent-registry` remains bundled or optional.

## Phase 6: split from home-manager-core cleanly

Tasks:

- Decide whether this repo becomes canonical source for tracker/wrapper/TUI.
- If yes, update `home-manager-core` to consume this repo as a flake input.
- If no, keep this as a downstream extraction and periodically sync.

## Open decisions

1. Should `agent-registry` be bundled in the default app or optional?
2. Should the UI attach to tmux, embed captured pane views, or both?
3. Should managed agents be windows, panes, or configurable?
4. Should default config start one `pi` agent automatically or start empty?
5. How should app handle secrets/tokens for registry config?

## Known risks

- The first standalone `agent-wrapper.sh` is intentionally simpler than the Home Manager inline wrapper; it needs parity testing.
- `agent-tracker` currently imports sibling Python modules; packaging works by copying the whole tree, but this should become a proper Python package later.
- The copied TUI still has assumptions from `home-manager-core` and may need UI-level app-mode changes.
- Private tmux control must be audited to ensure every tmux call uses the private socket.
