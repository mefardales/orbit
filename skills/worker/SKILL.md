---
name: worker
description: Team worker protocol (ACK, mailbox, task lifecycle) for tmux-based OMX teams
---

# Worker Skill: OMX Team Protocol

Protocol for Claude agents operating as workers within tmux-based OMX Teams.

## Core Identity

Workers must operate with `OMX_TEAM_WORKER` environment variable set in format `<team-name>/worker-<n>`.

## Startup Protocol

1. Parse worker identity from `OMX_TEAM_WORKER` environment variable
2. Send acknowledgment message to leader mailbox: `ACK: <workerName> initialized`
3. Target mailbox: `leader-fixed`
4. Begin monitoring inbox for task assignments

## Task Lifecycle

Workers follow a claim-safe workflow:

1. **Locate inbox** at canonical team state root
2. **Claim task** via CLI interop command (never direct file manipulation)
3. **Execute work** on claimed task
4. **Transition status** from `in_progress` to `completed` or `failed` via `orbit team api` commands

### Important Rules

- Only use CLI interop commands for state transitions -- never modify state files directly
- Task identifiers use numeric format ("1") not legacy "task-1" notation
- Commit changes before reporting completion: `git add -A && git commit -m "task: <subject>"`

## State Management

Worker sessions treat team state + CLI interop as the source of truth, not manual tmux interactions.

### Canonical Paths

- Team state root: resolved through environment variables and configuration hierarchy
- Inbox: `{team-state-root}/workers/{worker-name}/inbox.json`
- Tasks: `{team-state-root}/tasks/`
- Mailbox: `{team-state-root}/mailbox/`

## Communication Channels

1. **Inbox files** -- task assignments from leader
2. **Mailbox** -- messages to/from leader
3. **CLI interop** -- all state transitions via `orbit team api` commands

## Shutdown Protocol

1. Check inbox for shutdown instructions
2. Complete or save current work
3. Send completion acknowledgment to leader mailbox
4. Terminate session gracefully

## Key Principle

Worker sessions should treat team state + CLI interop as the source of truth rather than relying on manual tmux triggers. This ensures reliable state consistency across distributed team sessions.
