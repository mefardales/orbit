---
name: team
description: N coordinated agents on shared task list using tmux-based orchestration
---

<Purpose>
Team is the tmux-based parallel execution mode for OMX. It launches N coordinated agents (Codex and/or Claude CLI sessions) in split tmux panes, coordinated through `.omx/state/team/...` state files and CLI interop. Use Team for durable, stateful coordination suitable for long-running parallel work.
</Purpose>

<Use_When>
- Multiple workers needed for parallel task execution
- Work must survive beyond a single reasoning cycle
- Explicit lifecycle control required (start, monitor, shutdown)
- Shared task state needed across agents
- User says "team", "swarm", or wants coordinated parallel execution
</Use_When>

<Do_Not_Use_When>
- Bounded in-session parallelism suffices -- use native subagents instead
- Single sequential task -- delegate directly to executor
- No tmux available -- fall back to ultrawork
</Do_Not_Use_When>

<Execution_Policy>
- Never use ad-hoc `tmux send-keys` as primary control; use `pyclaude team api` CLI mutations
- Workers must commit changes before reporting completion
- Follow the exact lifecycle: start -> monitor -> wait for terminal state -> shutdown -> verify cleanup
- Do not run shutdown while workers actively write updates unless abort is explicitly requested
- Default to concise, evidence-dense progress and completion reporting
</Execution_Policy>

## Launch

```bash
pyclaude team [N:agent-type] "<task description>"
```

Example: `pyclaude team 3:executor "analyze feature X and report flaws"`

For Claude CLI workers:
```bash
OMX_TEAM_WORKER_CLI=claude pyclaude team 2:executor "update docs and report"
```

## Required Preconditions

- tmux installed
- Leader session runs inside tmux (check `$TMUX`)
- `omx` command resolves correctly
- No duplicate HUD panes exist

## Pre-Launch Intake Gate

Create or reuse a grounded context snapshot in `.omx/context/{slug}-*.md` before team launch with: task statement, desired outcome, known facts, constraints, and codebase touchpoints.

## Lifecycle Contract

1. **Start team** and verify startup evidence (panes, ACK mailbox)
2. **Monitor progress** via `pyclaude team status <team-name>` and mailbox files
3. **Wait** for terminal task state (no pending/in-progress/failed tasks)
4. **Shutdown**: `pyclaude team shutdown <team-name>`
5. **Verify cleanup**

## Worker Commit Protocol

Workers must commit changes before reporting completion:
```bash
git add -A && git commit -m "task: <subject>"
```

## Operational Commands

- `pyclaude team status <team-name>` -- reads task counts and worker health
- `pyclaude team resume <team-name>` -- reconnects to active team
- `pyclaude team shutdown <team-name>` -- graceful shutdown and cleanup

## Message Dispatch Policy

1. Use `pyclaude team ...` runtime lifecycle commands
2. Use `pyclaude team api ... --json` for mutations
3. Verify delivery via state evidence
4. Direct tmux is fallback-only after confirming state evidence failure

## State Files

Team state lives in `.omx/state/team/<team>/`:
- `config.json` -- team configuration
- `manifest.v2.json` -- team manifest
- Task files -- individual task state
- Worker identity/inbox/heartbeat/status files
- Mailbox files -- leader-to-worker and worker-to-leader communication

## MCP Tools

Four tools for agent-driven team orchestration:
- `omx_run_team_start` -- start a team
- `omx_run_team_status` -- check team status
- `omx_run_team_wait` -- wait for completion
- `omx_run_team_cleanup` -- cleanup after shutdown

## Worker Configuration

Workers resolve model and reasoning-effort from:
- Explicit `OMX_TEAM_WORKER_LAUNCH_ARGS`
- Inherited leader `--model` flag
- Per-worker role defaults

## Failure Diagnosis

| Issue | Solution |
|-------|----------|
| Stale panes from prior runs | Clean up with `pyclaude team shutdown` |
| Trigger submit failures | Check worker state first via `pyclaude team status` |
| ENOENT errors | Ensure shutdown waits for workers to finish |
