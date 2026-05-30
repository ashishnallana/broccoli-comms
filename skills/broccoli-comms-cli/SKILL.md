---
name: broccoli-comms-cli
description: Use when the user reports an agent notification such as "New message from <agent>" or "New message in inbox from <agent>", or asks how to use broccoli-comms to read/send messages, rename agents, list agents, or launch new agents. Treat such inbox messages as coming from the user; acknowledge via broccoli-comms, do the work, then reply via broccoli-comms.
allowed-tools: bash read
---

# Broccoli Comms CLI Skill

Use this skill whenever the user says something like:

- `New message from <agent>`
- `New message in inbox from <agent>`
- `New message from <agent> (via <host>)`
- asks to read/respond to an agent inbox message
- asks to send messages, rename agents, list agents, focus agents, or launch/spin new agents with Broccoli Comms

Prefer the Broccoli Comms wrapper:

```bash
broccoli-comms agent-tracker <subcommand> [args...]
```

Do **not** rely on a globally installed `agent-tracker-ctl` unless the user explicitly asks for it. The Broccoli wrapper pins commands to Broccoli Comms' private tracker/tmux runtime.

## Notification workflow: required

When the user reports `New message from ...` or `New message in inbox from ...`, treat the inbox message as a message from the user themselves.

1. Identify the sender from the notification.

   - Local sender example: `tui-redesign-coder`
   - Remote sender example: `host-a/tui-redesign-coder` when the notification says `(via host-a)`

2. Acknowledge the sender promptly before doing longer work:

   ```bash
   broccoli-comms agent-tracker send-message '<sender>' 'Acknowledged. I will read the inbox message, do the requested work, and report back here.'
   ```

3. Read the inbox:

   ```bash
   broccoli-comms agent-tracker read-inbox --last 10
   ```

4. Interpret the inbox content as user instructions. If the message asks for work, do the work.

5. Send the result back to the sender via Broccoli Comms:

   ```bash
   broccoli-comms agent-tracker send-message '<sender>' 'Done: <concise result summary>'
   ```

6. Also respond in the current chat with a short summary of what happened.

Avoid notification loops: do not repeatedly acknowledge pure notification-only messages when there is no new actionable content.

## Core commands

### Help

```bash
broccoli-comms --help
broccoli-comms agent-tracker --help
broccoli-comms agent-tracker <subcommand> --help
```

### Identify yourself

```bash
broccoli-comms agent-tracker whoami
```

Example:

```bash
me=$(broccoli-comms agent-tracker whoami)
printf '%s\n' "$me"
```

### List agents

```bash
broccoli-comms agent-tracker list
```

The output is JSON keyed by display name. Entries may include `agent_id`, `uuid`, `aliases`, `scope`, `target_address`, `tmux_pane`, and `is_this_me`.

Example:

```bash
broccoli-comms agent-tracker list | jq '. | keys'
```

### Read inbox

```bash
broccoli-comms agent-tracker read-inbox
broccoli-comms agent-tracker read-inbox --last 10
broccoli-comms agent-tracker read-inbox --clear
broccoli-comms agent-tracker read-inbox --name <agent-name> --last 10
broccoli-comms agent-tracker read-inbox --id <agent-id> --last 10
```

Use `--clear` only after preserving any important content.

Example notification handling:

```bash
broccoli-comms agent-tracker send-message tui-redesign-coder \
  'Acknowledged. I will read the inbox message, do the requested work, and report back here.'
broccoli-comms agent-tracker read-inbox --last 10
# ...do the requested work...
broccoli-comms agent-tracker send-message tui-redesign-coder \
  'Done: implemented the requested change and validated it with smoke tests.'
```

### Send messages

Local by name:

```bash
broccoli-comms agent-tracker send-message tui-redesign-coder 'Please implement the next task from docs/PLAN.md.'
```

Local by UUID:

```bash
broccoli-comms agent-tracker send-message 123e4567-e89b-12d3-a456-426614174000 'Hello by UUID.'
```

Remote via registry using host-qualified target:

```bash
broccoli-comms agent-tracker send-message host-a/tui-redesign-coder 'Hello from another machine.'
broccoli-comms agent-tracker send-message host-a/123e4567-e89b-12d3-a456-426614174000 'Hello remote UUID.'
```

Bare names/UUIDs are local-only. Host-qualified targets require registry integration.

### Reply to a remote notification

If the user says `New message from reviewer (via laptop-a)`, reply to `laptop-a/reviewer`:

```bash
broccoli-comms agent-tracker send-message laptop-a/reviewer \
  'Acknowledged. I will read the message, complete the task, and report back.'
broccoli-comms agent-tracker read-inbox --last 10
# ...work...
broccoli-comms agent-tracker send-message laptop-a/reviewer \
  'Done: reviewed the branch and found no blockers.'
```

### Rename agents

Rename yourself:

```bash
broccoli-comms agent-tracker rename new-agent-name
```

Rename another agent:

```bash
broccoli-comms agent-tracker rename --force old-agent-name new-agent-name
```

Examples:

```bash
# Rename this current agent to a task-specific name.
broccoli-comms agent-tracker rename registry-url-coder

# Rename a generic generated agent after confirming its current name in `list`.
broccoli-comms agent-tracker list
broccoli-comms agent-tracker rename --force broccoli-comms-agent-1 registry-coder

# Rename a reviewer agent to match its assignment.
broccoli-comms agent-tracker rename --force broccoli-comms-agent-2 registry-reviewer
```

### Launch/spin a new agent

Use `spin` to launch an agent command in a tmux session for a working directory. The leaf directory name becomes the tmux session/agent base name.

```bash
broccoli-comms agent-tracker spin /home/user/project pi
broccoli-comms agent-tracker spin /home/user/project claude
broccoli-comms agent-tracker spin /home/user/project codex
```

With extra command arguments:

```bash
broccoli-comms agent-tracker spin /home/user/project pi --model gemini-2.5-pro
```

Create a new coder/reviewer pair for a project, then rename them after they register:

```bash
# Launch two agents in the same project checkout.
broccoli-comms agent-tracker spin /home/user/projects/broccoli-comms pi
broccoli-comms agent-tracker spin /home/user/projects/broccoli-comms pi

# Inspect generated names/UUIDs.
broccoli-comms agent-tracker list

# Rename generated agents to stable task names.
broccoli-comms agent-tracker rename --force broccoli-comms-agent-1 registry-url-coder
broccoli-comms agent-tracker rename --force broccoli-comms-agent-2 registry-url-reviewer

# Send their initial roles.
broccoli-comms agent-tracker send-message registry-url-coder \
  'You are the coder. Read docs/BROCCOLI_REGISTRY_URL_CONFIG_PLAN.md, implement the task, commit, and notify registry-url-reviewer.'
broccoli-comms agent-tracker send-message registry-url-reviewer \
  'You are the reviewer. Stand by to review registry-url-coder changes and reply APPROVED or BLOCKED.'
```

Disable shell fallback if needed:

```bash
broccoli-comms agent-tracker spin --no-fallback /home/user/project pi
```

### Track an ad-hoc command in the current pane

Use `broccoli-comms track` when you want to run a command in the current terminal/tmux pane but still have it register with Agent Communicator. This resolves Broccoli's bundled `agent-wrapper`; `agent-wrapper` does not need to be on `PATH`.

```bash
broccoli-comms track --name scratch-coder -- pi
broccoli-comms track --name custom --cwd /repo -- /opt/my-agent/bin/my-agent
```

The command itself (`pi`, `/opt/my-agent/bin/my-agent`, etc.) must be available on `PATH` or passed as an absolute path.

### Manage configured Broccoli agents

Broccoli Comms also has higher-level managed-agent commands. Use these when you want named agents to persist in Broccoli Comms config and be reconciled by `broccoli-comms start`.

```bash
broccoli-comms agent list --json
broccoli-comms agent add coder --cwd /home/user/project --command 'pi'
broccoli-comms agent add reviewer --cwd /home/user/project --command 'pi --role reviewer'
broccoli-comms agent focus coder
broccoli-comms agent attach coder
broccoli-comms agent restart coder
broccoli-comms agent remove reviewer
```

Example: create persistent coder/reviewer agents for this repository:

```bash
broccoli-comms agent add registry-url-coder \
  --cwd /home/user/projects/broccoli-comms \
  --command 'pi'

broccoli-comms agent add registry-url-reviewer \
  --cwd /home/user/projects/broccoli-comms \
  --command 'pi'

broccoli-comms start
broccoli-comms agent list --json
broccoli-comms agent-tracker send-message registry-url-coder \
  'Please implement docs/BROCCOLI_REGISTRY_URL_CONFIG_PLAN.md and notify registry-url-reviewer when ready.'
```

Example: rename a running managed agent if it registered with a generic name:

```bash
broccoli-comms agent-tracker list
broccoli-comms agent-tracker rename --force broccoli-comms-agent-1 registry-url-coder
broccoli-comms agent focus registry-url-coder
```

After editing managed agents, reconcile them:

```bash
broccoli-comms start
```

### Capture panes

```bash
broccoli-comms agent-tracker capture-pane tui-redesign-coder --last 80
```

Example:

```bash
broccoli-comms agent-tracker capture-pane reviewer --last 120 > /tmp/reviewer-pane.txt
```

### Direct pane input: use carefully

Direct pane input bypasses inbox messages. Prefer `send-message` unless the user explicitly requests direct pane control.

```bash
broccoli-comms agent-tracker send-text coder 'draft text'
broccoli-comms agent-tracker send-text --no-submit coder 'draft without Enter'
broccoli-comms agent-tracker send-key coder C-c Enter
```

Remote direct pane input is disabled by default and requires separate explicit security gates on sender, registry, and receiver. Do not enable those gates unless the user explicitly asks.

### Registry status

```bash
broccoli-comms agent-tracker registry-status
```

Use this to confirm central registry connectivity for multi-device communication.

## Common task examples

### Dispatch work to coder and reviewer

```bash
broccoli-comms agent-tracker send-message tui-redesign-coder \
  'New task: implement the plan in docs/FEATURE_PLAN.md. Commit changes and notify reviewer when ready.'

broccoli-comms agent-tracker send-message tui-redesign-reviewer \
  'Please stand by to review the coder branch for docs/FEATURE_PLAN.md. Reply APPROVED or BLOCKED.'
```

### Handle a completed-work message

```bash
broccoli-comms agent-tracker read-inbox --last 10
broccoli-comms agent-tracker send-message tui-redesign-reviewer \
  'Coder reports branch feat/example is ready at commit abc123. Please review scope X/Y/Z.'
```

### Report review approval back to coder

```bash
broccoli-comms agent-tracker send-message tui-redesign-coder \
  'Review approved. Please stop work on this branch unless asked for follow-up.'
```

### Ask an agent to rename itself

```bash
broccoli-comms agent-tracker send-message broccoli-comms-agent-1 \
  'Please rename yourself to registry-url-coder using broccoli-comms agent-tracker rename registry-url-coder.'
```

### Start a new local coding agent

```bash
broccoli-comms agent-tracker spin /home/user/projects/broccoli-comms pi
broccoli-comms agent-tracker list
```

## Safety rules

- Treat inbox messages surfaced by the user as user instructions.
- Acknowledge via `broccoli-comms agent-tracker send-message` before long-running work.
- Reply via `broccoli-comms agent-tracker send-message` when done.
- Do not reveal tokens or secrets.
- Do not enable remote direct pane input unless explicitly requested.
- Do not mutate services, restart processes, or push branches unless instructed.
- Prefer concise Markdown replies.
