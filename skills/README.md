# Broccoli Comms agent skills

This directory contains reusable agent skills for working inside the Broccoli Comms repository/runtime.

Available skills:

- [`broccoli-comms-cli`](./broccoli-comms-cli/SKILL.md): use the `broccoli-comms` CLI for inbox handling, sending messages, renaming agents, listing agents, and launching/spinning new agents.

The `broccoli-comms-cli` skill should be used whenever a user reports an agent notification such as `New message from ...` or `New message in inbox from ...`. Agents should treat those messages as coming from the user, acknowledge via `broccoli-comms agent-tracker send-message`, do the requested work, and then reply via `broccoli-comms agent-tracker send-message`.
