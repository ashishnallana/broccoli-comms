# agent-registry slice

This slice ships a standalone package/app plus reusable NixOS and Home Manager modules.

The NixOS module can also reconcile local managed agents into tmux sessions on the registry host. The Home Manager module provides a Linux/non-NixOS user-service deployment path for the registry and managed agents.
By default managed agents now use the user's normal tmux socket under `XDG_RUNTIME_DIR` (for example `/run/user/<uid>/tmux-<uid>/default`). Set `tmuxSocketPath` explicitly if you want a dedicated tmux server instead.
See `AGENT_REGISTRY_DEPLOYMENT.md` for the `managedAgents` example and restart-warning behavior.

Managed-agent end-to-end check:

- `nix build .#checks.x86_64-linux.managed-agent --no-link -L`

Stateful dev VM workflow:

- `nix run .#devvm`
- see `VM_WORKFLOWS.md`

Current registry delivery model: durable on-disk queue + tracker long-poll / ack for cross-tracker messages. This avoids registry→tracker callback reachability requirements while preserving messages across registry restarts.

Deferred to follow-up: DELETE /trackers.
