# Bug log

## BUG-001: agent-registry managed-agent default tmux socket can derive invalid `/run/user/tmux-<uid>/default`

Status: fixed and landed in `61a46b4 Fix managed-agent runtime dir handling`; VM validation passed.

Found while testing registry managed agents in `~/projects/nix/test-vm`.

### Reproduction

A test NixOS config imported `agent-registry.nixosModules.default` and enabled:

```nix
services.agent-registry = {
  enable = true;
  auth = false;
  port = 8080;
  managedAgents.smoke = {
    user = "dev";
    session = "registry-smoke";
    cwd = "/home/dev";
    command = "sleep 300";
    wrapperPath = "env";
    reconcileIntervalSeconds = 30;
  };
};
```

After activating the config in the VM, `agent-registry-managed-smoke.service` failed:

```text
PermissionError: [Errno 13] Permission denied: '/run/user/tmux-1000'
```

The managed-agent helper attempted to create a tmux socket parent under `/run/user/tmux-1000`, which is missing the UID path component (`/run/user/1000/...`).

### Suspected cause

`agent-registry/managed_agent.py` trusts an inherited `XDG_RUNTIME_DIR` via `default_tmux_socket()`. In this VM/systemd service context, `XDG_RUNTIME_DIR` appears to be `/run/user`, so the derived socket path becomes `/run/user/tmux-1000/default` instead of `/run/user/1000/tmux-1000/default`.

The NixOS module only sets `XDG_RUNTIME_DIR` when the target user has an explicit `uid` in the NixOS config, so services for users without an explicit `uid` can inherit/derive an invalid runtime dir.

### Fix

Implemented and landed:

- added `effective_runtime_dir()` in `agent-registry/managed_agent.py`
- treat missing, empty, bare `/run/user`, and mismatched `/run/user/<other-uid>` `XDG_RUNTIME_DIR` as invalid for managed-agent tmux socket derivation
- fallback to `/run/user/<os.getuid()>`
- make `ensure_env()` replace invalid inherited `XDG_RUNTIME_DIR` instead of preserving it with `setdefault`
- added unit coverage for bare `/run/user`, mismatched UID, and `ensure_env()` socket derivation

### VM validation

Passed in `~/projects/nix/test-vm` after rebuilding the temporary registry test flake against the fixed checkout and activating:

```text
/nix/store/r608k24bc16wyzx9kraxic6p1rg5hqab-nixos-system-devvm-26.05.20260523.2991645
```

Observed results:

- `curl -fsS http://127.0.0.1:8080/healthz` returned `{"ok": true}`
- `agent-registry.service` was active
- `agent-registry-managed-smoke.service` exited with `status=0/SUCCESS`
- managed tmux server used `/run/user/1000/tmux-1000/default`
- `tmux -S /run/user/1000/tmux-1000/default list-panes` showed `registry-smoke smoke %0 smoke sleep`
- `AGENT_REGISTRY_TMUX_SOCKET=/run/user/1000/tmux-1000/default` was present in tmux global environment
