# Broccoli Comms E2E Routing Testing Plan

## Objective

Discover and document routing, inbox delivery, reply, and TUI visibility bugs. Do **not** fix product code in this pass.

The testing agent (`pi-1`) owns execution of the test matrix. The validating agent (`pi`) reviews the plan, verifies that the cases are complete, inspects evidence, and asks for additional coverage where needed.

## Ground rules

1. Use `broccoli-comms` CLI as the primary test surface.
   - Good: `broccoli-comms start`, `broccoli-comms agent add`, `broccoli-comms agent-tracker send-message`, `broccoli-comms agent-tracker read-inbox`, `broccoli-comms registry ...`.
   - Avoid raw `agent-tracker-ctl` unless there is no Broccoli CLI path and the exception is documented.
2. Use isolated runtime/config/cache paths.
3. Use an isolated registry on this machine with a unique token and state file.
4. Use `~/projects/nix/test-vm` as the remote machine.
5. Create deterministic test agents, not LLM agents, for reproducible inbox/pane evidence.
6. Capture evidence for every journey, including negative evidence from non-target inboxes.
7. Document bugs only; do not implement fixes.
8. For task-update fanout journeys, record the logical `message_id`, each recipient `delivery_id`, and the output of `broccoli-comms registry agents --logical-identity agent-communicator --service-kind shared_service --json`.

## Topology

### Host side

- Hostname override: `e2e-host`
- Runtime: temp dir, e.g. `/tmp/bc-e2e.<id>/host/runtime`
- Config: temp dir, e.g. `/tmp/bc-e2e.<id>/host/config`
- Cache: temp dir, e.g. `/tmp/bc-e2e.<id>/host/cache`
- Tmux mode: `private`
- Registry: hosted on this machine using `broccoli-comms registry start` with auth.

### VM side

- VM repo: `~/projects/nix/test-vm`
- SSH: `dev@127.0.0.1:2222`
- Hostname override: `e2e-vm`
- Runtime/config/cache under `/tmp/bc-e2e.<id>/vm/...`
- Tmux mode: `private`
- Registry URL points to host registry through QEMU host address, usually `http://10.0.2.2:<port>`.

## Test agents

Use `scripts/e2e_test_agent.py`, launched through `broccoli-comms agent add ... --autostart`.

Host agents:

- `local-alpha`
- `local-beta`
- `dupe-agent`
- `agent-communicator` (simulated communicator identity)

VM agents:

- `remote-alpha`
- `remote-beta`
- `dupe-agent`
- `agent-communicator` (simulated communicator identity)

Each agent should log:

- startup identity
- commands it receives
- inbox messages observed
- send results
- auto-reply results where enabled

## Required evidence per journey

For each journey, capture:

1. Journey ID and command(s) executed.
2. `broccoli-comms status --json` for host and/or VM.
3. `broccoli-comms agent list --json` for host and/or VM.
4. `broccoli-comms agent-tracker list` for host and/or VM.
5. Registry `agents` and `trackers` JSON.
6. Sender inbox after send.
7. Target inbox after send.
8. All non-target inboxes after send.
9. Test-agent JSONL logs.
10. Tmux pane captures for sender, target, and any `agent-communicator` involved.
11. Tracker/registry logs around the journey.

## User journey matrix

### A. Local routing

| ID | Journey | Expected |
|---|---|---|
| A1 | `local-alpha` sends to `local-beta` by bare name | Only `local-beta` receives. |
| A2 | `local-beta` sends to `local-alpha` by bare name | Only `local-alpha` receives. |
| A3 | `local-alpha` sends to `local-beta` by local UUID | Only `local-beta` receives. |
| A4 | `local-alpha` sends to `dupe-agent` while a remote `dupe-agent` exists | Bare name remains local-only; only local `dupe-agent` receives. |
| A5 | host CLI sends to `local-alpha` | Sender should be `cli-user` or documented stable CLI sender; only `local-alpha` receives. |

### B. Remote routing

| ID | Journey | Expected |
|---|---|---|
| B1 | `local-alpha` sends to `e2e-vm/remote-alpha` | Only VM `remote-alpha` receives. |
| B2 | `local-alpha` sends to `e2e-vm/remote-beta` | Only VM `remote-beta` receives. |
| B3 | `remote-alpha` sends to `e2e-host/local-alpha` | Only host `local-alpha` receives. |
| B4 | `remote-beta` sends to `e2e-host/local-beta` | Only host `local-beta` receives. |
| B5 | send to remote UUID target | Only the matching remote agent receives. |
| B6 | send to `e2e-vm/dupe-agent` while local `dupe-agent` exists | Only VM `dupe-agent` receives. |

### C. Reply routing

| ID | Journey | Expected |
|---|---|---|
| C1 | `local-alpha -> remote-alpha`; `remote-alpha` auto-replies | Reply lands only in `local-alpha` inbox. |
| C2 | `local-beta -> remote-alpha`; `remote-alpha` auto-replies | Reply lands only in `local-beta` inbox. |
| C3 | Two local senders send to same remote agent, remote replies to both | Replies do not cross between local inboxes. |
| C4 | Two remote senders send to same local agent, local replies | Replies return to correct remote sender. |

### D. `agent-communicator` routing regressions

| ID | Journey | Expected |
|---|---|---|
| D1 | Host `agent-communicator` sends to `local-alpha` | Message must not land in host `agent-communicator` unless explicitly targeted. |
| D2 | Host `agent-communicator` sends to `e2e-vm/remote-alpha` | Only VM `remote-alpha` receives. |
| D3 | VM `remote-alpha` replies to host `agent-communicator` | Reply lands only in host `agent-communicator`. |
| D4 | VM `agent-communicator` sends to `e2e-host/local-alpha` | Only host `local-alpha` receives; VM communicator does not self-receive. |
| D5 | Host and VM both have `agent-communicator`; send to fully-qualified communicator target | Only the qualified communicator receives. |
| D6 | Host task update is moved to a visible status while host and VM both run `agent-communicator` shared services | Both host and VM communicator inboxes receive exactly one typed task-update message with the same logical `message_id` and distinct per-recipient `delivery_id` values. |
| D7 | Run `broccoli-comms registry agents --logical-identity agent-communicator --service-kind shared_service --json` with host and VM registered | Registry returns one active shared-service row per communicator with `logical_identity`, `service_kind`, and `capabilities`; stale/gone communicator rows are absent from fanout targets. |
| D8 | Bare CLI send to `agent-communicator` while both communicators are registered | Bare send remains local-only; remote communicator receives nothing. |

### E. TUI visibility and identity

| ID | Journey | Expected |
|---|---|---|
| E1 | Start/open host TUI with remote VM communicator registered | Remote `agent-communicator` should ideally not show as a normal selectable agent. |
| E2 | Start/open VM TUI with host communicator registered | Remote `agent-communicator` should ideally not show as a normal selectable agent. |
| E3 | Multiple communicator identities exist across devices | TUI should not collapse them into one normal chat row or route messages to itself. |
| E4 | Sending from TUI to a non-communicator agent | TUI sender identity is local communicator; target receives; TUI does not self-deliver. |

### F. Ambiguity and collision coverage

| ID | Journey | Expected |
|---|---|---|
| F1 | Local and remote agents share display name | Bare target is local-only; host-qualified target is remote. |
| F2 | Remote targets share display name across two registry-visible hostnames, if available | Host-qualified names must disambiguate. |
| F3 | Use registry-qualified target if supported, e.g. `e2e:e2e-vm/remote-alpha` | Must route through named registry only. |
| F4 | Send to stale/gone remote target | Error is explicit; no fallback to wrong local/remote agent. |

## Bug report format

Use this structure in the final report:

```md
## BUG-NNN: Short title

### Journey
Which journey ID and exact command sequence.

### Expected
What should have happened.

### Actual
What happened.

### Evidence
- Command output
- Inbox snapshots
- Registry snapshots
- Pane captures
- Relevant log snippets

### Impact
Why this matters to users.

### Reproducibility
Always / intermittent / observed once.

### Suspected area
Target resolution / registry routing / sender attribution / communicator identity / TUI filtering.
```

## Initial implementation artifacts

- `scripts/e2e_test_agent.py` has been added as the deterministic managed-agent command.
- The execution harness should be added separately and should write all artifacts under a timestamped temp/results directory.

## Validation role for `pi`

`pi` should review `pi-1`'s resulting test report and verify:

1. Every journey in the matrix was executed or explicitly marked blocked.
2. At least one local, one remote, one reply, one communicator, and one collision case was verified by pane capture and inbox snapshots.
3. Negative checks were performed against non-target inboxes.
4. The report distinguishes product bugs from test harness/environment failures.
5. No product code fixes were made during the bug discovery run.
