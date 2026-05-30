# About Broccoli Comms

Broccoli Comms is a private command center for terminal-based AI coding agents.

It helps you run, message, monitor, and coordinate agents from one isolated workspace. Instead of mixing agent panes into your normal tmux setup or relying on a global tracker service, Broccoli Comms owns its own runtime: a private tmux socket, a private `agent-tracker`, managed agent windows, a terminal UI, and optional registry-based multi-device messaging.

## Why customers use it

As people start using multiple coding agents at once, the hard part is no longer only prompting one agent. The hard part becomes coordination:

- Which agents are running?
- Which terminal pane belongs to which agent?
- Did the coder finish?
- Did the reviewer approve?
- Which machine is an agent running on?
- How do I send an instruction without losing it in scrollback?
- How do I keep agent experiments separate from my normal terminal sessions?

Broccoli Comms exists to make those workflows explicit and repeatable.

## Personas and problems

### 1. The solo developer running several local agents

**Problem**

You want to run a coder, a reviewer, maybe a planning agent, and maybe a scratch agent. Without a coordination layer, every agent is just another terminal pane. You need to remember names, panes, scrollback, and state yourself.

**How Broccoli Comms helps**

Broccoli Comms gives each registered agent an addressable identity and inbox through the private tracker. You can list agents, send messages, read inboxes, capture panes, focus agent windows, and open a terminal UI for conversations and status.

Example workflow:

```sh
broccoli-comms start
broccoli-comms agent add coder --cwd ~/project --command 'pi'
broccoli-comms agent add reviewer --cwd ~/project --command 'pi'
broccoli-comms start
broccoli-comms ui
```

From there you can message the agents:

```sh
broccoli-comms agent-tracker send-message coder 'Please implement the parser change and tell reviewer when ready.'
broccoli-comms agent-tracker send-message reviewer 'Please review coder changes when they report ready.'
```

### 2. The engineer coordinating coder/reviewer workflows

**Problem**

You want one agent to implement and another agent to review. You need a reliable handoff: coder reports completion, reviewer checks the work, and you only merge after approval. Plain terminal panes make that workflow easy to lose track of.

**How Broccoli Comms helps**

Broccoli Comms exposes inbox-style messaging and a CLI wrapper pinned to the private runtime:

```sh
broccoli-comms agent-tracker read-inbox --last 10
broccoli-comms agent-tracker send-message reviewer 'Coder says branch feat/example is ready. Please review.'
```

The terminal UI (`broccoli-comms ui`) gives a single place to view conversations, switch targets, and use explicit input modes for inbox messages or direct pane input.

The repository also includes a `skills/` directory with guidance for agents using the Broccoli Comms CLI. That skill tells agents how to acknowledge messages, do the requested work, and respond through `broccoli-comms agent-tracker`.

### 3. The user who wants clean isolation from their normal terminal setup

**Problem**

You may already have tmux sessions, shell hooks, or a Home Manager setup. You do not want an agent experiment to interfere with that environment.

**How Broccoli Comms helps**

Broccoli Comms owns a private runtime by default:

- private tracker socket: `$XDG_RUNTIME_DIR/broccoli-comms/agent-tracker.sock`
- private tmux socket: `$XDG_RUNTIME_DIR/broccoli-comms/tmux.sock`
- config under `$XDG_CONFIG_HOME/broccoli-comms`
- logs/cache under `$XDG_CACHE_HOME/broccoli-comms`

You can start and stop the Broccoli workspace independently:

```sh
broccoli-comms start
broccoli-comms status --json
broccoli-comms stop
```

This keeps the agent workspace separate from your normal tmux server and from any global/default tracker you may already run.

### 4. The multi-device user

**Problem**

You may run agents on a laptop, a workstation, or a remote Linux box. Local tmux panes do not solve cross-machine discovery or messaging.

**How Broccoli Comms helps**

Broccoli Comms can use a central `agent-registry` for multi-device communication. Each machine runs its own local Broccoli Comms tracker. The trackers publish to and poll the same registry for discovery and queued messages.

A central registry is needed for multi-device communication. Without a registry, Broccoli Comms works as a local-only agent workspace on one machine.

Using an existing registry:

```sh
broccoli-comms registry add \
  --name home \
  --url https://registry.example.com \
  --auth \
  --token-file ~/.config/broccoli-comms/registry-token

broccoli-comms start
broccoli-comms agent-tracker registry-status
```

Running a local/standalone registry with Broccoli Comms:

```sh
broccoli-comms registry start --host 0.0.0.0 --port 8080 --name home --auth --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms registry status
```

Then each participating machine can add that registry URL and start its local tracker.

### 5. The platform-minded user who wants a scriptable agent runtime

**Problem**

You want a CLI-first workflow that can be scripted, tested, and installed. You may want a TUI for humans, but you also need commands for automation.

**How Broccoli Comms helps**

The `broccoli-comms` CLI provides runtime, agent, tracker, and registry commands:

```sh
broccoli-comms doctor
broccoli-comms start
broccoli-comms ui
broccoli-comms status --json
broccoli-comms agent list --json
broccoli-comms agent add coder --cwd ~/project --command 'pi'
broccoli-comms agent-tracker list
broccoli-comms registry list --json
broccoli-comms stop
```

The same runtime can be used interactively through the TUI or programmatically through CLI commands.

## What Broccoli Comms includes

### Private runtime

Broccoli Comms starts and manages its own tracker and tmux socket. This isolates the agent workspace from your normal tmux sessions and from other tracker services.

### Managed agents

You can configure named agents with a working directory and command. `broccoli-comms start` reconciles those agents into the private runtime.

```sh
broccoli-comms agent add coder --cwd ~/project --command 'pi'
broccoli-comms agent add reviewer --cwd ~/project --command 'pi'
broccoli-comms start
```

### Agent messaging and inboxes

Agents can receive messages through the tracker inbox system.

```sh
broccoli-comms agent-tracker send-message coder 'Please inspect the failing test.'
broccoli-comms agent-tracker read-inbox --last 10
```

### Terminal UI

`broccoli-comms ui` opens the `agent-communicator` terminal UI inside the private runtime. It provides conversation/status views and explicit modes for inbox messages and pane input.

### Tracker passthrough

`broccoli-comms agent-tracker <subcommand>` runs the in-repository tracker control tool against the Broccoli private runtime. This avoids relying on a globally installed `agent-tracker-ctl`.

```sh
broccoli-comms agent-tracker list
broccoli-comms agent-tracker registry-status
broccoli-comms agent-tracker capture-pane coder --last 80
```

### Registry management

Broccoli Comms can both run a local `agent-registry` service and configure registry URLs for the private tracker.

Run a registry:

```sh
broccoli-comms registry start --host 127.0.0.1 --port 8080 --name local --noauth
broccoli-comms registry health
broccoli-comms registry agents --json
broccoli-comms registry stop
```

Configure an existing registry URL:

```sh
broccoli-comms registry add --name home --url https://registry.example.com --auth --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms registry list
broccoli-comms registry env
```

Saved registry URLs live in `$BROCCOLI_COMMS_CONFIG_DIR/registries.json`, usually `~/.config/broccoli-comms/registries.json`.

## Security and control model

Broccoli Comms is local-first by default:

- Local messaging works without a registry.
- Multi-device communication requires explicitly configuring a central registry.
- Registry token files are preferred over storing token values in commands or config.
- Remote direct pane input is disabled by default and remains behind separate explicit gates.
- Starting or adding a registry does not automatically enable remote direct pane control.

This makes the common local workflow simple while keeping more powerful cross-machine and direct-input workflows explicit.

## Installation options

Broccoli Comms supports Nix and source-checkout workflows.

Nix:

```sh
nix run github:tanmayv/broccoli-comms#broccoli-comms -- doctor
nix run github:tanmayv/broccoli-comms#broccoli-comms -- ui
```

Persistent Nix install:

```sh
nix profile install github:tanmayv/broccoli-comms#broccoli-comms
broccoli-comms doctor
broccoli-comms ui
```

Source checkout:

```sh
git clone https://github.com/tanmayv/broccoli-comms.git
cd broccoli-comms
make build
./bin/broccoli-comms doctor
./bin/broccoli-comms ui
```

See `README.md` for the detailed dependency list and setup commands.

## In one sentence

Broccoli Comms helps you turn a pile of terminal-based AI agents into a coordinated, private, scriptable workspace that can run locally or connect across machines through a central registry.
