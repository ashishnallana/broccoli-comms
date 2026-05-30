# Broccoli Comms demo-agent implementation plan

## Goal

Add a deterministic, non-AI `demo-agent/` that can be launched by Broccoli Comms to demonstrate local inbox messaging, TUI conversations, and simple inter-agent workflows without requiring API keys, model CLIs, network access, or an agent registry.

The same executable must be reusable as a generic Pi-like demo agent, a coding agent, or a review agent. It should behave like a small scripted agent: read its Broccoli Comms inbox, match supported messages, and reply with static/scripted responses.

Primary demo target:

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

No registry is in scope for the first implementation.

## Non-goals

- No AI/model integration.
- No network calls made by `demo-agent`.
- No shell-command execution from inbox text.
- No registry or remote direct pane input.
- No direct pane input as part of the demo-agent behavior.
- No shared global state between separate Broccoli Comms runtimes.
- No file reads/writes requested by inbox messages.
- No dynamic plugins, scenario scripts, templates, or eval-like behavior.

## User-facing behavior requirements

1. `demo-agent` runs as a normal terminal process under `agent-wrapper`.
2. It uses the private Broccoli tracker identified by `AGENT_TRACKER_SOCKET`.
3. It reads its own inbox and responds to every supported incoming message using:

   ```sh
   broccoli-comms agent-tracker send-message <target> <message>
   ```

   Terminal stdout is only for observability/debug logs. A response must not rely only on printing to the pane.

4. All scripted progress updates must also use `send-message` so they appear in the TUI conversation history.
5. Unknown messages receive a TUI-visible fallback via `send-message`.
6. The same program supports role-specific behavior for generic, coder, reviewer, and optional planner roles.
7. It should be safe to run multiple demo agents in one Broccoli Comms runtime and safe to run many separate runtimes for SSH demo users.

## Proposed files

```text
demo-agent/
  demo-agent              # executable Python entrypoint or small shell wrapper
  demo_agent.py           # implementation if entrypoint is a wrapper
  README.md               # demo setup and supported messages
  scenarios.json          # optional; only static trusted data, no user-provided code
```

Preferred first implementation: a single executable Python script at `demo-agent/demo-agent` using only the Python standard library.

Optional packaging follow-up:

- expose `demo-agent` in the Nix package closure used by demo containers.
- add README examples using both `broccoli-comms agent add ...` and `broccoli-comms track ...`.

## CLI design

```sh
./demo-agent [--role ROLE] [--name NAME] [--peer-coder NAME] [--peer-reviewer NAME] [--poll-interval SECONDS] [--state-dir DIR]
```

Arguments:

- `--role {generic,coder,reviewer,planner}`: explicit role. Optional.
- `--name NAME`: optional display/logging name. Defaults to `AGENT_NAME`, `SUGGESTED_AGENT_NAME`, or inferred role name.
- `--peer-coder NAME`: default `demo-coder`.
- `--peer-reviewer NAME`: default `demo-reviewer`.
- `--poll-interval SECONDS`: default `1.0`, minimum clamp recommended at `0.2`.
- `--state-dir DIR`: optional state directory. Default under `$BROCCOLI_COMMS_CACHE_DIR/demo-agent/<agent-id-or-name>`.

Role inference if `--role` is omitted:

| Agent name contains | Role |
| --- | --- |
| `coder`, `implementer`, `dev` | `coder` |
| `reviewer`, `review` | `reviewer` |
| `planner`, `lead` | `planner` |
| otherwise | `generic` |

## Runtime implementation design

### Tracker/inbox access

Use structured tracker JSON-RPC over `AGENT_TRACKER_SOCKET` for inbox reads, because `read-inbox` CLI output is human-oriented.

Recommended polling flow:

1. Connect to Unix socket from `AGENT_TRACKER_SOCKET`.
2. Call `get_inbox` for the current agent:

   ```json
   {
     "jsonrpc": "2.0",
     "method": "get_inbox",
     "params": {
       "agent_id": "$AGENT_ID",
       "mark_read": true
     },
     "id": 1
   }
   ```

   Fallback to `agent_name` only if `AGENT_ID` is absent.

3. For each returned message, compute a dedupe key:
   - prefer `message_id`
   - else hash of `timestamp + sender + message`
4. Skip already-processed keys stored in the local state file.
5. Handle the message.
6. Record the processed key atomically.

### Sending replies

All outbound demo responses must use the CLI passthrough:

```sh
broccoli-comms agent-tracker send-message "$target" "$message"
```

Use `subprocess.run([...], check=True, env=os.environ.copy())`; do not use `shell=True`.

Rationale:

- matches the public Broccoli Comms workflow being demonstrated;
- guarantees TUI-visible inbox/conversation history;
- avoids direct pane input;
- avoids needing registry features.

If `broccoli-comms` is not on `PATH`, the implementation may also try a `BROCCOLI_COMMS_BIN` env override, but the packaged/demo runtime should ensure `broccoli-comms` is available.

Target safety rules:

- `send-message` targets must be local-only names validated with `^[A-Za-z0-9_.-]+$`.
- Do not send to targets containing `/`, `:`, whitespace, shell metacharacters, or URL-like text.
- The inbound sender may be used as a reply target only after this validation.
- Configured peers (`--peer-coder`, `--peer-reviewer`) must pass the same validation at startup.
- If the sender target is invalid or remote-looking, log a safe warning to stdout and do not send a reply.
- Do not use `send-text`, `send-key`, `send-pane`, registry endpoints, or remote host-qualified targets.

### Terminal observability

The pane should print concise logs for demo observers, for example:

```text
[demo-agent] role=coder name=demo-coder tracker=/run/user/.../agent-tracker.sock
[demo-agent] received from agent-communicator: implement feature
[demo-agent] send-message -> agent-communicator: Acknowledged...
```

Logs must not include secrets. Messages are user-visible demo text and may be logged.

## Supported message table

All responses and side effects below must be delivered with `broccoli-comms agent-tracker send-message`.

| Incoming message | Generic role behavior | Coder role behavior | Reviewer role behavior |
| --- | --- | --- | --- |
| `help` | Sends shared command menu | Sends coder command menu | Sends reviewer command menu |
| `hello` | Sends scripted greeting | Sends greeting as demo coder | Sends greeting as demo reviewer |
| `who are you?` | Explains it is a no-AI scripted demo agent | Explains scripted coding role | Explains scripted review role |
| `status` | Reports online, local inbox/tracker only, no registry | Reports coding state and peer reviewer | Reports review state and peer coder |
| `ping` | Sends `pong` | Sends `pong from demo-coder` | Sends `pong from demo-reviewer` |
| `ack demo` | Explains inbox + `send-message` flow | Same, with coder framing | Same, with reviewer framing |
| `start task` | Runs generic 3-step progress sequence | Runs scripted implementation sequence | Runs scripted review sequence |
| `progress` | Reports current state | Reports implementation state | Reports review state |
| `implement feature` | Says this is best shown with coder role | Sends implementation progress and optionally asks reviewer | Says implementation is not reviewer role; offer to review when ready |
| `review good` | Says this is best shown with reviewer role | Sends review request to reviewer | Sends `APPROVED...` to sender |
| `review bad` | Says this is best shown with reviewer role | Sends review request asking for blocked review | Sends `BLOCKED...` to sender |
| `ask reviewer` | Sends a demo message to configured reviewer and confirms to sender | Sends review request to reviewer and confirms to sender | Replies that it is already the reviewer |
| `ask coder` | Sends a demo message to configured coder and confirms to sender | Replies that it is already the coder | Sends implementation request to coder and confirms to sender |
| `please review scripted feature from demo-coder` | If generic, gives neutral review acknowledgement | If coder receives this, redirects to reviewer | Reviews and sends approval back to `demo-coder` |
| `review-result approved <task_id>` | Records generic result | Coder maps task to original sender and reports approval | Reviewer should not normally receive this |
| `review-result blocked <task_id>` | Records generic result | Coder maps task to original sender and reports blocker | Reviewer should not normally receive this |
| `summarize` | Sends local demo summary | Summarizes implementation/review handoff state | Summarizes review state |
| `reset` | Clears local demo state | Clears coder task/review state | Clears reviewer state |
| anything else | Sends fallback + `help` hint | Sends coder fallback + `help` hint | Sends reviewer fallback + `help` hint |

## Scripted response examples

### `help`

Generic response:

```text
Demo commands: hello, status, ping, ack demo, start task, progress, implement feature, ask reviewer, ask coder, review good, review bad, summarize, reset.
Every response is sent through broccoli-comms agent-tracker send-message so it appears in the TUI.
```

### `hello`

```text
Hello! I am demo-agent, a scripted no-AI Broccoli Comms demo agent. I receive inbox messages and reply through send-message.
```

### `status`

```text
Status: online. I am using the local private Broccoli tracker inbox. Registry and remote direct pane input are not required for this demo.
```

### `ack demo`

```text
Message received through my Broccoli Comms inbox. This reply was sent with broccoli-comms agent-tracker send-message, so it appears in the TUI conversation.
```

### `start task`

Send multiple TUI-visible messages to the original sender:

```text
Acknowledged. Starting scripted task.
Progress: 1/3 reading requirements.
Progress: 2/3 preparing pretend changes.
Progress: 3/3 task complete. Ready for review.
```

Use short sleeps between progress updates, e.g. `0.7s`, so the TUI visibly updates without making demos slow.

### `implement feature` as coder

To original sender:

```text
Acknowledged. I am implementing the scripted feature.
Progress: 1/3 inspecting requirements.
Progress: 2/3 editing pretend files.
Progress: 3/3 implementation complete.
Sending review request to demo-reviewer.
```

Then to reviewer:

```text
Please review scripted feature from demo-coder. task_id=<task_id>
```

Store `task_id -> original sender` locally so the coder can report the review result back to the user.

### Reviewer handles coder request

Incoming:

```text
Please review scripted feature from demo-coder. task_id=<task_id>
```

Reviewer sends to `demo-coder`:

```text
review-result approved <task_id>: APPROVED. Scripted review passed: requirements satisfied, tests simulated, no blockers.
```

Coder receives the review result and sends to original sender:

```text
demo-reviewer approved task <task_id>. Scripted workflow complete.
```

### `review bad` as reviewer

```text
BLOCKED. Required change: add missing validation before approval. This is a scripted reviewer response.
```

## State management

State should be small JSON stored under the runtime/cache tree:

```json
{
  "processed_message_keys": ["..."],
  "tasks": {
    "task-001": {
      "origin_sender": "agent-communicator",
      "status": "awaiting_review"
    }
  }
}
```

Requirements:

- Write atomically with temp file + rename.
- Keep processed-message key history bounded, e.g. last 500 keys.
- Bound task history too, e.g. last 100 task records.
- Never store secrets.
- State directory must default inside `$BROCCOLI_COMMS_CACHE_DIR` or `$BROCCOLI_COMMS_RUNTIME_DIR`, not the repository checkout.
- `--state-dir` is for tests/debugging only and must resolve under `$BROCCOLI_COMMS_CACHE_DIR` or `$BROCCOLI_COMMS_RUNTIME_DIR`; otherwise exit with a clear error.
- Never choose a state path from inbox message text.
- Use `Path.resolve()`/equivalent before checking state-dir containment.

## Security requirements

1. No `shell=True` anywhere.
2. Never execute inbox message text as code or commands.
3. Never parse inbox message text as a command line, Python expression, template, JSON instruction, plugin name, file path, URL, or shell fragment.
4. Only allow configured peer names after validating with the same conservative name regex shape: letters, digits, underscore, dot, dash.
5. Outbound targets are either the validated inbound local `sender` or explicit configured local peer names (`demo-coder`, `demo-reviewer`).
6. Reject/ignore outbound targets containing `/`, `:`, whitespace, URL schemes, or other remote-looking syntax. This prevents accidental registry routing.
7. Ignore or safely handle messages from self to avoid loops.
8. Rate-limit scripted multi-message responses:
   - cap one incoming message to a small fixed number of outbound messages, recommended max 5;
   - use fixed short sleeps only;
   - avoid unbounded loops between coder and reviewer.
9. Coder/reviewer protocol messages must require known task IDs before forwarding results. Unknown `review-result ...` messages should receive at most one local fallback/ignored log, not trigger new peer messages.
10. No network access in the agent implementation. Do not import or use `urllib`, `requests`, `http.client`, `socket` for network connections, or registry client code. Unix socket access to the local tracker is allowed.
11. No registry usage in the demo-agent plan.
12. Do not enable or depend on remote direct pane input.
13. Do not read arbitrary files based on user messages.
14. Do not write outside the configured state dir.
15. Use subprocess argument arrays for `broccoli-comms agent-tracker send-message`.
16. Enforce maximum outbound message length, e.g. 2000 chars, though scripted messages should be far shorter.
17. Enforce a maximum inbound message length to inspect/echo, e.g. 4000 chars. Long inputs should be treated as unknown/truncated for logs and must not be echoed in full.
18. Treat all incoming message text as untrusted even in demo mode.
19. Do not print environment variables wholesale; logs must not include tokens, registry credentials, or full process environments.
20. On send failure, log a concise error and continue polling; do not retry indefinitely.

## Demo container considerations, non-blocking for first implementation

The demo-agent should be compatible with an SSH demo host where each SSH connection gets isolated env:

```sh
export HOME=/tmp/broccoli-demo/$sid/home
export BROCCOLI_COMMS_RUNTIME_DIR=/tmp/broccoli-demo/$sid/runtime
export BROCCOLI_COMMS_CACHE_DIR=/tmp/broccoli-demo/$sid/cache
export BROCCOLI_COMMS_CONFIG_DIR=/tmp/broccoli-demo/$sid/config
export BROCCOLI_COMMS_TMUX_MODE=private
export BROCCOLI_COMMS_DISABLE_CONFIG_REGISTRIES=1
unset AGENT_REGISTRIES_JSON AGENT_REGISTRY_TOKEN
```

The demo-agent must not assume a shared home directory or stable state across sessions.

## Documentation updates

Add `demo-agent/README.md` covering:

- what the demo agent is and is not;
- quick start with `broccoli-comms agent add`;
- quick start with `broccoli-comms track` if the track command is available;
- supported message table;
- role inference;
- security notes: no AI, no network, no command execution from messages, replies always use `send-message`.

Update top-level `README.md` with a short pointer to `demo-agent/README.md` if appropriate.

## Validation plan

### Static checks

```sh
python -m py_compile demo-agent/demo-agent app/broccoli-comms.py
```

If implemented as `demo_agent.py`:

```sh
python -m py_compile demo-agent/demo_agent.py
```

### Basic runtime smoke

```sh
rt=$(mktemp -d)
export BROCCOLI_COMMS_RUNTIME_DIR="$rt/runtime"
export BROCCOLI_COMMS_CACHE_DIR="$rt/cache"
export BROCCOLI_COMMS_CONFIG_DIR="$rt/config"
export BROCCOLI_COMMS_TMUX_MODE=private

python app/broccoli-comms.py agent add demo-pi --cwd "$PWD/demo-agent" --command './demo-agent --role generic'
python app/broccoli-comms.py start
python app/broccoli-comms.py agent-tracker list
python app/broccoli-comms.py agent-tracker send-message demo-pi 'hello'
sleep 2
python app/broccoli-comms.py agent-tracker read-inbox --name agent-communicator --last 10
python app/broccoli-comms.py stop
```

Expected: `agent-communicator` receives the scripted `hello` reply.

### Coder/reviewer smoke

```sh
python app/broccoli-comms.py agent add demo-coder --cwd "$PWD/demo-agent" --command './demo-agent --role coder --peer-reviewer demo-reviewer'
python app/broccoli-comms.py agent add demo-reviewer --cwd "$PWD/demo-agent" --command './demo-agent --role reviewer --peer-coder demo-coder'
python app/broccoli-comms.py start
python app/broccoli-comms.py agent-tracker send-message demo-coder 'implement feature'
sleep 5
python app/broccoli-comms.py agent-tracker read-inbox --name agent-communicator --last 20
```

Expected:

- coder sends progress messages to the user;
- coder sends review request to reviewer;
- reviewer sends approval to coder;
- coder reports approval back to original sender.

### Safety smokes

- Unknown message returns fallback via `send-message`.
- Message text like `$(rm -rf /)` is treated as plain text and not executed.
- Message text like `review-result approved fake-task` does not trigger peer forwarding unless the task is known.
- Remote-looking sender/target values containing `/` or `:` are rejected or ignored by target validation.
- Very long message is bounded/truncated in response handling if echoed.
- Self-sent messages do not cause infinite loops.
- `reset` clears only demo-agent state dir.
- `--state-dir /tmp/outside-cache` is rejected unless it resolves under the configured Broccoli runtime/cache directory.
- The implementation contains no `shell=True` and no network client imports/usage beyond local Unix socket tracker RPC.

## Acceptance criteria

- `demo-agent/demo-agent` exists and is executable.
- Same executable can serve generic, coder, and reviewer roles.
- Every supported incoming command produces TUI-visible responses using `broccoli-comms agent-tracker send-message`.
- Coder/reviewer inter-agent handoff works locally with no registry.
- No AI/network/API dependency is introduced.
- No user-provided message text is executed.
- State is isolated under Broccoli runtime/cache paths and is cleaned with the runtime/session.
- Docs include supported command table and demo setup.
