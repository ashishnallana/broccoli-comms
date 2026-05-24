# Broccoli Comms Migration Plan

## Goal

Create a standalone agent communication app that owns its own runtime and UI path, without requiring the user's Home Manager, tmux config, shell hooks, or existing tmux sessions.

The runtime should remain UI-agnostic so it can support:

- the current terminal `agent-communicator-tui`
- CLI automation
- a future Electron/native/libghostty frontend

## Desired user flow

```sh
broccoli-comms
```

The app should start a private runtime, reconcile configured agents, and open the communicator UI.

For explicit setup on a new machine:

```sh
broccoli-comms doctor
broccoli-comms agent add main --cwd ~/project --command 'pi'
broccoli-comms start
broccoli-comms agent list --json
broccoli-comms open
```

With Nix, `tmux` should be supplied by the package closure. For manual/non-Nix installs, `tmux` is currently a required system dependency unless/until we ship a bundled installer.

## Current status snapshot

As of 2026-05-24, the standalone extraction has a working private runtime, managed-agent CLI, and committed JSON runtime/API boundary for future frontends.

Committed history:

- `d18f2e7` - Initial Broccoli Comms standalone scaffold
- `6b09c3a` - Add private runtime smoke test
- `61f2d0c` - Harden private tmux socket usage
- `f81f62c` - Add managed agent CLI
- `8218973` - Add runtime JSON API boundary
- `59b70c8` - Update migration plan after runtime API chunk
- `83482c1` - Wrap spun agents with agent-wrapper
- `8a5ed7f` - Update migration plan after spin wrapper chunk
- `38ebd93` - Make communicator TUI app-runtime aware
- `763f895` - Update migration plan after TUI app-runtime chunk
- `8c38859` - Add doctor bootstrap diagnostics

Current work:

- Chunk 6 first slice is committed: app-aware TUI runtime status/private socket handling and managed-agent focus/attach CLI affordances.
- Chunk 7 is committed: `doctor --json`, bootstrap/install docs, and smoke coverage for new-machine readiness checks.
- Next work is final code review/pending-action cleanup before broader future chunks.

Current agent coordination:

- Previous coder/reviewer panes were killed.
- New `broccoli-comms-coder` and `broccoli-comms-reviewer` agents have been spun and given the current context.
- Coder and reviewer completed Chunk 7; both can be reused for final review.

Latest full validation gate passed for final review cleanup:

```sh
nix --extra-experimental-features 'nix-command flakes' flake check .
nix --extra-experimental-features 'nix-command flakes' build .#default --no-link
bash scripts/smoke-private-runtime.sh
bash scripts/smoke-managed-agents.sh
(cd agent-tracker && python3 -m unittest test_tmux_util.py test_spin_command.py)
(cd agent-communicator-tui && go test ./...)
python3 -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-tracker/ctl_commands/*.py
bash -n wrapper/agent-wrapper.sh
git diff --check
```

## Initial extraction

Copied into this repo:

- `agent-tracker/`: daemon, JSON-RPC, CLI, inbox/event store, tmux helpers, registry client
- `agent-communicator-tui/`: existing Go TUI
- `agent-registry/`: registry server and managed-agent code
- `wrapper/agent-wrapper.sh`: first standalone wrapper script
- `app/broccoli-comms.py`: standalone launcher/supervisor

Added:

- `flake.nix` with packages/apps
- `Makefile` for non-Nix builds
- `README.md`
- smoke scripts for private runtime and managed agents
- runtime/API documentation draft

## Target architecture

```text
broccoli-comms
├── app launcher/supervisor
├── private tmux server/socket
├── private agent-tracker daemon/socket
├── managed agent windows
├── agent-wrapper
└── agent-communicator UI
```

Runtime ownership rules:

- Use private tracker and tmux sockets.
- Strip inherited `TMUX`/`TMUX_PANE` for app-managed subprocesses.
- Do not depend on user Home Manager modules.
- Do not depend on the user's tmux config, status bar, hooks, or sessions.
- Expose JSON-friendly runtime state for frontends instead of making UIs target tmux directly.

## Chunk / phase progress

### Chunk 1 / Phase 1: bootstrap standalone runtime

Status: complete and committed.

Tasks:

- [x] create `~/projects/nix/broccoli-comms`
- [x] copy `agent-tracker`
- [x] copy `agent-communicator-tui`
- [x] copy `agent-registry`
- [x] add standalone `agent-wrapper.sh`
- [x] add `broccoli-comms.py` launcher
- [x] add flake package outputs
- [x] add non-Nix Makefile
- [x] add and pass private runtime smoke test

### Chunk 2 / Phase 2: harden app-private runtime

Status: complete and committed for current scope; some follow-up hardening remains.

Tasks done:

- [x] Use app-private `XDG_CACHE_HOME`/state paths consistently in launcher environment.
- [x] Ensure tracker state follows app-provided env paths for the standalone runtime.
- [x] Ensure runtime tmux commands use the private socket.
- [x] Strip inherited `TMUX`/`TMUX_PANE` for app-managed commands.
- [x] Add stale tracker socket cleanup.
- [x] Add private tmux socket cleanup during stop.
- [x] Add tracker log file output.
- [x] Add `docs/TMUX_SOCKET_AUDIT.md`.

Follow-up:

- [ ] Add/verify log files for tmux launch and managed agents.
- [x] Expand `broccoli-comms doctor` baseline checks to cover agent commands, writable dirs, socket reachability, and packaging expectations. Further deep registry/version checks remain in Chunk 7 follow-up items.
- [ ] Re-run private tmux socket audit after TUI and spin-wrapper changes.

### Chunk 3 / Phase 3: managed agents

Status: complete and committed.

Tasks done:

- [x] Define initial config schema in `$XDG_CONFIG_HOME/broccoli-comms/config.json` / `BROCCOLI_COMMS_CONFIG_DIR`.
- [x] Add `broccoli-comms agent list`.
- [x] Add `broccoli-comms agent add`.
- [x] Add `broccoli-comms agent remove`.
- [x] Add `broccoli-comms agent restart`.
- [x] Reconcile desired agents into private tmux windows.
- [x] Avoid duplicate managed-agent windows after repeated `start`.
- [x] Store managed-agent identity in tmux metadata: `@broccoli_managed_agent`.
- [x] Resolve managed windows by tmux `window_id`/`pane_id`, not ambiguous names.
- [x] Extend smoke coverage for managed-agent collision case.

Follow-up:

- [ ] Decide whether additional metadata should be persisted outside tmux for crash recovery or future non-tmux frontends.
- [ ] Add config type validation for `cwd` and `command`.
- [ ] Improve non-`--json` `agent list` human output.

### Chunk 4: runtime JSON/API boundary

Status: complete and committed.

Tasks implemented:

- [x] Add `broccoli-comms status --json`.
- [x] Add stable runtime status object with app/version, paths, tracker, tmux, config, and managed-agent counts/windows.
- [x] Keep backward-compatible status aliases for existing consumers/smoke checks.
- [x] Improve `broccoli-comms agent list --json` with configured spec, running state, managed-window metadata, and best-effort tracker registration.
- [x] Add `docs/RUNTIME_API.md` documenting JSON contracts and UI-agnostic rules.
- [x] Extend smoke scripts to validate JSON fields.
- [x] Validate with Nix checks, builds, smoke tests, unit tests, compile checks, shell syntax, and `git diff --check`.

Completed commit gates:

- [x] Reviewer approval for Chunk 4.
- [x] Lead commit after approval.

Known limitations to track:

- JSON-over-CLI is the current API surface; no long-running HTTP/Unix-socket API yet.
- `agent list --json` tracker registration is best-effort and can be null while wrapper registration is pending or tracker is down.
- Version currently defaults to `0.1.0` / `BROCCOLI_COMMS_VERSION`; packaging does not inject git/build version yet.

### Chunk 5: enforce wrapped spawned agents

Status: complete and committed.

Goal: make `agent-tracker-ctl spin` and Broccoli Comms spin paths ensure spawned commands run under `agent-wrapper`.

Planned tasks:

- [x] Ensure `agent-tracker-ctl spin` wraps raw commands with the standalone/bundled `agent-wrapper` so spun agents register, heartbeat, and get inbox/status behavior.
- [x] Avoid double-wrapping if command is already `agent-wrapper` or the resolved packaged wrapper path.
- [x] Ensure wrapper path resolution works in Nix and source-tree/dev checkouts.
- [x] Preserve private tracker/tmux socket env when spinning from Broccoli Comms runtime.
- [x] Add unit coverage for raw command wrapping and already-wrapped commands.
- [x] Document spin behavior in README/runtime docs.
- [x] Clarify bootstrap dependency expectations: Nix packages include `tmux`; manual/non-Nix installs currently require system `tmux` and `python3`.
- [x] Run full validation gate.
- [x] Reviewer approval for Chunk 5.
- [x] Lead commit after approval.

Known limitations to track:

- Auto-wrap dedup only inspects the first command token. Shell-wrapped commands such as `bash -lc "agent-wrapper pi"` are not inspected.
- Existing wrapper flag parsing behavior is unchanged; wrapper-specific flags can still be consumed by `agent-wrapper` before the agent command.

### Chunk 6: app-aware TUI integration

Status: complete and committed.

Planned tasks:

- [x] Make `agent-communicator-tui` detect Broccoli Comms app runtime from explicit env.
- [x] Make TUI use the private tracker socket automatically when launched by `broccoli-comms`.
- [x] Show minimal runtime health/tracker status in the existing TUI footer.
- [x] Preserve private tmux boundaries for local pane switching by using explicit private tmux socket env when present.
- [x] Add `broccoli-comms agent focus <name>` and `broccoli-comms agent attach <name>` affordances using managed-window metadata/window ids.
- [x] Add focused unit coverage for app-runtime socket/status and private tmux command construction.
- [x] Run full validation gate.
- [x] Reviewer approval for Chunk 6.
- [x] Lead commit after approval.

Future work (not implemented in Chunk 6 first slice):

- [ ] Wire managed-agent focus/attach into TUI hotkeys if useful after UX review.
- [ ] Add global advanced view over all app-managed inboxes.
- [ ] Design a generic permission request model.
- [ ] Design remote pane capture via agent-tracker/registry.
- [ ] Design remote send-keys/send-text for approvals/denials.
- [ ] Keep pane/control features agent-agnostic with detector/adaptor backends for pi/claude/codex/etc.

### Chunk 7: doctor, bootstrap, and packaging polish

Status: complete and committed.

Planned tasks:

- [x] Improve `broccoli-comms doctor` for new-machine readiness:
  - [x] JSON mode: `broccoli-comms doctor --json`
  - [x] `tmux` availability/version or bundled path
  - [x] Python/tracker/wrapper/TUI availability
  - [x] writable runtime/cache/config dirs
  - [x] configured agent command availability where practical
  - [x] tracker/tmux socket reachability/status when runtime is up
- [x] Clarify Nix path where `tmux` is bundled and manual path where user must install `tmux`.
- [x] Add/verify `nix profile install` docs.
- [x] Keep exposed flake package names documented in README.
- [x] Add doctor JSON validation to private-runtime smoke coverage.
- [x] Run full validation gate.
- [x] Reviewer approval for Chunk 7.
- [x] Lead commit after approval.

Deferred/final-review items:

- [x] Add lightweight flake `checks` outputs for Python syntax, selected tracker unit tests, shell syntax, and Go communicator tests.
- [ ] Decide whether `agent-registry` remains bundled by default or optional.
- [ ] Expand `doctor` further for agent command version checks, registry config/secrets sanity, and socket repair suggestions.

### Final review / migration-phase cleanup

Status: ready for review in the working tree; validation complete, pending review and lead commit.

Items found/fixed:

- [x] Added flake `checks` for Python compile, tracker unit smoke, shell syntax, and Go communicator tests so `nix flake check` exercises more than package evaluation.
- [x] Removed stale flake app `meta` warnings by adding app descriptions and avoiding deprecated `pkgs.system` access.
- [x] Rechecked migration docs for stale completed items and moved remaining work into future-only/deferred lists.

Remaining future-only items:

- [ ] Decide whether `agent-registry` remains bundled by default or optional.
- [ ] Add full launcher/runtime smokes as Nix checks if they can be made reliable in sandbox/CI tmux environments.
- [ ] Add deeper `doctor` checks for agent command versions, registry config/secrets, and suggested repairs.
- [ ] Continue wrapper parity hardening against the Home Manager wrapper over time.

### Chunk 8: future native/Electron/libghostty frontend path

Status: future planning only.

Planned tasks:

- [ ] Decide frontend architecture.
- [ ] Decide whether to add a local daemon HTTP/Unix-socket API mirroring the CLI JSON contracts.
- [ ] Prototype frontend consuming runtime API instead of tmux internals.
- [ ] Keep runtime separate from UI technology.

### Phase 6: split from home-manager-core cleanly

Status: not started; intentionally deferred until standalone runtime stabilizes.

Tasks:

- [ ] Decide whether this repo becomes canonical source for tracker/wrapper/TUI.
- [ ] If yes, update `home-manager-core` to consume this repo as a flake input.
- [ ] If no, keep this as a downstream extraction and periodically sync.

## Open decisions

1. Should `agent-registry` be bundled in the default app or optional?
2. Should the UI attach to tmux, embed captured pane views, or both?
3. Should managed agents be windows, panes, or configurable?
4. Should default config start one `pi` agent automatically or start empty?
5. How should app handle secrets/tokens for registry config?
6. Should runtime expose only CLI JSON long term, or also a local HTTP/Unix-socket API?
7. Should managed-agent metadata be persisted outside tmux for recovery and non-tmux frontends?
8. How should packaged versions be generated/injected?

## Known risks

- The standalone `agent-wrapper.sh` is simpler than the Home Manager inline wrapper and still needs parity testing.
- `agent-tracker` currently imports sibling Python modules; packaging works by copying the whole tree, but this should become a proper Python package later.
- The copied TUI is now app-runtime aware for the standalone path, but still shares upstream assumptions/package naming from `home-manager-core` and needs continued sync/parity review.
- Private tmux control has smoke and unit coverage for the app runtime, but should remain part of future reviews whenever pane-control features change.
- Manual/non-Nix installs currently require system `tmux`.
- Existing pre-Chunk-3 managed windows without `@broccoli_managed_agent` metadata are intentionally not managed by the new remove/restart logic.
