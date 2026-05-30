# Broccoli Comms demo-agent

`demo-agent` is a deterministic, non-AI Broccoli Comms agent for demos. It polls its local tracker inbox and replies with scripted messages using:

```sh
broccoli-comms agent-tracker send-message <target> <message>
```

It does not call models, use the network, execute inbox text, use registries, or send direct pane input.

## Quick start

From the repository root:

```sh
broccoli-comms agent add demo-coder \
  --cwd ./demo-agent \
  --command './demo-agent --role coder --peer-reviewer demo-reviewer'

broccoli-comms agent add demo-reviewer \
  --cwd ./demo-agent \
  --command './demo-agent --role reviewer --peer-coder demo-coder'

broccoli-comms agent add demo-pi \
  --cwd ./demo-agent \
  --command './demo-agent --role generic'

broccoli-comms start
broccoli-comms ui
```

If `broccoli-comms track` is available in your build, the same executable can also be tracked directly, for example:

```sh
cd demo-agent
broccoli-comms track --name demo-pi -- ./demo-agent --role generic
```

## Roles

One executable supports these roles:

- `generic`: Pi-like scripted inbox responder.
- `coder`: scripted implementation progress and review handoff.
- `reviewer`: scripted approval/blocking responses.
- `planner`: currently uses the generic command set with planner labelling.

If `--role` is omitted, the role is inferred from `--name`, `AGENT_NAME`, or `SUGGESTED_AGENT_NAME`:

| Name contains | Role |
| --- | --- |
| `coder`, `implementer`, `dev` | `coder` |
| `reviewer`, `review` | `reviewer` |
| `planner`, `lead` | `planner` |
| anything else | `generic` |

## Supported messages

Send these from the TUI or CLI with `broccoli-comms agent-tracker send-message <agent> '<message>'`:

| Message | Behavior |
| --- | --- |
| `help` | Shows command menu. |
| `hello` | Sends a scripted greeting. |
| `who are you?` | Explains this is a no-AI scripted demo agent. |
| `status` | Reports local inbox/tracker status and role peers. |
| `ping` | Replies with `pong` (role-specific for coder/reviewer). |
| `ack demo` | Explains inbox + `send-message` flow. |
| `start task` | Sends a short 3-step scripted progress sequence. |
| `progress` | Reports local scripted state. |
| `implement feature` | Coder sends implementation progress and asks reviewer. Other roles explain the role mismatch. |
| `review good` | Reviewer approves. Coder requests an approving review. |
| `review bad` | Reviewer blocks. Coder requests a blocking review. |
| `ask reviewer` | Sends a local scripted message/review request to the configured reviewer. |
| `ask coder` | Sends a local scripted implementation request to the configured coder. |
| `summarize` | Reports local demo summary. |
| `reset` | Clears only this agent's local demo state. |
| anything else | Sends a safe fallback and `help` hint. |

Coder/reviewer handoff uses local-only peer names. Example:

1. Send `implement feature` to `demo-coder`.
2. The coder sends progress messages to you.
3. The coder sends `Please review scripted feature from demo-coder. task_id=...` to `demo-reviewer`.
4. The reviewer sends `review-result approved ...` back to `demo-coder`.
5. The coder reports the result to the original sender.

## CLI

```sh
./demo-agent [--role generic|coder|reviewer|planner] \
  [--name NAME] \
  [--peer-coder demo-coder] \
  [--peer-reviewer demo-reviewer] \
  [--poll-interval 1.0] \
  [--state-dir DIR]
```

`--state-dir` is intended for tests/debugging and must resolve under `BROCCOLI_COMMS_CACHE_DIR` or `BROCCOLI_COMMS_RUNTIME_DIR`.

## Safety notes

- No AI/model/API dependency.
- No network access; the only socket use is the local Unix-domain tracker socket from `AGENT_TRACKER_SOCKET`.
- No `shell=True`; outbound replies use subprocess argument arrays.
- Inbox text is never executed and is not interpreted as code, shell, JSON, template, plugin, path, or URL.
- Outbound targets must be local names matching `^[A-Za-z0-9_.-]+$`; host-qualified or remote-looking targets are refused.
- Self-messages are ignored to avoid loops.
- Scripted multi-message responses are capped and state is bounded.
- State is written only under the Broccoli runtime/cache tree.
