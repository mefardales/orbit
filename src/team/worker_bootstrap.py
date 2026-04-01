"""Worker bootstrap: inbox generation, trigger messages, overlay management.

Generates the per-worker instruction files, inbox content, and trigger
messages used to initialize and communicate with team workers.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from .state.types import TeamTask


# ── Constants ─────────────────────────────────────────────────────────────────

TEAM_OVERLAY_START = "<!-- ORBIT:TEAM:WORKER:START -->"
TEAM_OVERLAY_END = "<!-- ORBIT:TEAM:WORKER:END -->"


# ── Worker overlay ────────────────────────────────────────────────────────────


def generate_worker_overlay(team_name: str) -> str:
    """Generate the generic AGENTS.md overlay for team workers.

    This is the SAME for all workers -- no per-worker identity.
    Per-worker context goes in the inbox file.
    """
    return f"""{TEAM_OVERLAY_START}
<team_worker_protocol>
You are a team worker in team "{team_name}". Your identity and assigned tasks are in your inbox file.

## Protocol
1. Read your inbox file at the path provided in your first instruction
2. Send an ACK to the lead using CLI interop (to_worker="leader-fixed") once initialized
3. Read your task from <team_state_root>/team/{team_name}/tasks/task-<id>.json
4. Request a claim via CLI interop; do not directly set lifecycle fields in the task file
5. Do the work using your tools
6. After completing work, commit your changes before reporting completion
7. On completion/failure, use lifecycle transition APIs
8. Update your status to idle and wait for new instructions
9. Check your mailbox for messages at <team_state_root>/team/{team_name}/mailbox/{{your-name}}.json

## Message Protocol
When sending messages, ALWAYS include:
- from_worker: "<your-worker-name>"
- to_worker: "leader-fixed" (to message the leader) or "worker-N" (for peers)

## Rules
- Do NOT edit files outside the paths listed in your task description
- If blocked on a shared file, report to the lead by writing to your status file
- Do NOT write lifecycle fields directly in task files; use claim-safe lifecycle APIs
</team_worker_protocol>
{TEAM_OVERLAY_END}"""


# ── Overlay application ──────────────────────────────────────────────────────


def strip_overlay_from_content(content: str) -> str:
    """Strip worker overlay from content. Idempotent."""
    start_idx = content.find(TEAM_OVERLAY_START)
    end_idx = content.find(TEAM_OVERLAY_END)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return content
    before = content[:start_idx].rstrip()
    after = content[end_idx + len(TEAM_OVERLAY_END):].lstrip()
    return before + ("\n\n" + after if after else "") + "\n"


def apply_worker_overlay(agents_md_path: str, overlay: str) -> None:
    """Apply worker overlay to AGENTS.md. Idempotent."""
    path = Path(agents_md_path)
    content = ""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        pass

    content = strip_overlay_from_content(content)
    content = content.rstrip() + "\n\n" + overlay + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def strip_worker_overlay(agents_md_path: str) -> None:
    """Strip worker overlay from AGENTS.md. Idempotent."""
    path = Path(agents_md_path)
    try:
        content = path.read_text(encoding="utf-8")
        stripped = strip_overlay_from_content(content)
        if stripped != content:
            path.write_text(stripped, encoding="utf-8")
    except OSError:
        pass


# ── Initial inbox generation ─────────────────────────────────────────────────


def generate_initial_inbox(
    worker_name: str,
    team_name: str,
    agent_type: str,
    tasks: List[TeamTask],
    *,
    team_state_root: Optional[str] = None,
    leader_cwd: Optional[str] = None,
    worker_role: Optional[str] = None,
    role_prompt_content: Optional[str] = None,
) -> str:
    """Generate initial inbox file content for worker bootstrap."""
    task_list_parts: List[str] = []
    for t in tasks:
        entry = f"- **Task {t.id}**: {t.subject}\n  Description: {t.description}\n  Status: {t.status}"
        if t.blocked_by:
            entry += f"\n  Blocked by: {', '.join(t.blocked_by)}"
        if t.role:
            entry += f"\n  Role: {t.role}"
        task_list_parts.append(entry)

    task_list = "\n".join(task_list_parts)
    state_root = team_state_root or "<team_state_root>"
    lcwd = leader_cwd or "<leader_cwd>"
    display_role = worker_role or agent_type

    specialization = ""
    if role_prompt_content:
        specialization = f"""
## Your Specialization

You are operating as a **{display_role}** agent. Follow these behavioral guidelines:

{role_prompt_content}
"""

    return f"""# Worker Assignment: {worker_name}

**Team:** {team_name}
**Role:** {display_role}
**Worker Name:** {worker_name}

## Your Assigned Tasks

{task_list}

## Instructions

1. Send startup ACK to the lead mailbox BEFORE any task work
2. Start with the first non-blocked task
3. Read the task file at `{state_root}/team/{team_name}/tasks/task-<id>.json`
4. Task id format: State/MCP APIs use `task_id: "<id>"` (not `"task-<id>"`)
5. Request a claim via CLI interop to claim it
6. Complete the work described in the task
7. After completing work, commit your changes before reporting completion
8. Complete/fail it via lifecycle transition API
9. Write idle status to `{state_root}/team/{team_name}/workers/{worker_name}/status.json`
10. Wait for the next instruction from the lead

## Message Protocol
When sending messages, ALWAYS include from_worker with YOUR worker name:
- from_worker: "{worker_name}"
- to_worker: "leader-fixed" (for leader) or "worker-N" (for peers)

## Scope Rules
- Only edit files described in your task descriptions
- Do NOT edit files that belong to other workers
- If blocked on a shared file, write blocked status and wait
{specialization}"""


# ── Task assignment inbox ─────────────────────────────────────────────────────


def generate_task_assignment_inbox(
    worker_name: str,
    team_name: str,
    task_id: str,
    task_description: str,
) -> str:
    """Generate inbox content for a follow-up task assignment."""
    return f"""# New Task Assignment

**Worker:** {worker_name}
**Task ID:** {task_id}

## Task Description

{task_description}

## Instructions

1. Read the task file at `<team_state_root>/team/{team_name}/tasks/task-{task_id}.json`
2. Task id format: State/MCP APIs use `task_id: "{task_id}"`
3. Request a claim via CLI interop
4. Complete the work
5. After completing work, commit your changes before reporting completion
6. Complete/fail via lifecycle transition API
7. Write idle status to your status file
"""


# ── Shutdown inbox ────────────────────────────────────────────────────────────


def generate_shutdown_inbox(team_name: str, worker_name: str) -> str:
    """Generate inbox content for shutdown."""
    return f"""# Shutdown Request

All tasks are complete. Please wrap up any remaining work and respond with a shutdown acknowledgement.

## Shutdown Ack Protocol
1. Write your decision to:
   `<team_state_root>/team/{team_name}/workers/{worker_name}/shutdown-ack.json`
2. Format:
   - Accept: `{{"status":"accept","reason":"ok","updated_at":"<iso>"}}`
   - Reject: `{{"status":"reject","reason":"still working","updated_at":"<iso>"}}`
3. After writing the ack, exit your session.
"""


# ── Trigger messages ──────────────────────────────────────────────────────────


def generate_trigger_message(
    worker_name: str,
    team_name: str,
    team_state_root: str = ".omx/state",
) -> str:
    """Generate the SHORT send-keys trigger message (< 200 chars, ASCII-safe)."""
    inbox_path = f"{team_state_root}/team/{team_name}/workers/{worker_name}/inbox.md"
    return f"Read {inbox_path}, start work now, report concrete progress, then continue assigned work or next feasible task."


def generate_mailbox_trigger_message(
    worker_name: str,
    team_name: str,
    count: int,
    team_state_root: str = ".omx/state",
) -> str:
    """Generate a SHORT trigger for mailbox notifications (< 200 chars)."""
    n = max(1, int(count)) if isinstance(count, (int, float)) else 1
    mailbox_path = f"{team_state_root}/team/{team_name}/mailbox/{worker_name}.json"
    return f"You have {n} new message(s). Read {mailbox_path}, act now, reply with concrete progress, then continue assigned work or next feasible task."


def generate_leader_mailbox_trigger(
    team_name: str,
    from_worker: str,
    team_state_root: str = ".omx/state",
) -> str:
    """Generate trigger for leader mailbox notification."""
    mailbox_path = f"{team_state_root}/team/{team_name}/mailbox/leader-fixed.json"
    return f"Read {mailbox_path}; {from_worker} sent a new message. Review it and decide the next concrete step."


# ── Worker instructions file ─────────────────────────────────────────────────


def write_team_worker_instructions_file(
    team_name: str,
    cwd: str,
    overlay: str,
) -> str:
    """Write a team-scoped model instructions file.

    Composes user-level AGENTS.md, the project AGENTS.md (if any),
    and the worker overlay. Returns the absolute path.
    """
    base_parts: List[str] = []
    home_agents = Path.home() / ".claude" / "AGENTS.md"
    project_agents = Path(cwd) / "AGENTS.md"

    for source in [home_agents, project_agents]:
        try:
            content = source.read_text(encoding="utf-8")
            content = strip_overlay_from_content(content).strip()
            if content:
                base_parts.append(content)
        except OSError:
            continue

    base = "\n\n".join(base_parts)
    composed = f"{base}\n\n{overlay}\n" if base.strip() else f"{overlay}\n"

    out_path = Path(cwd) / ".omx" / "state" / "team" / team_name / "worker-agents.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(composed, encoding="utf-8")
    return str(out_path)


def write_worker_role_instructions_file(
    team_name: str,
    worker_name: str,
    cwd: str,
    base_instructions_path: str,
    worker_role: str,
    role_prompt_content: str,
) -> str:
    """Compose a per-worker startup instructions file with role prompt."""
    base = ""
    try:
        base = Path(base_instructions_path).read_text(encoding="utf-8")
    except OSError:
        pass

    role_overlay = f"""
<!-- ORBIT:TEAM:ROLE:START -->
<team_worker_role>
You are operating as the **{worker_role}** role for this team run. Apply the following role-local guidance.

{role_prompt_content.strip()}
</team_worker_role>
<!-- ORBIT:TEAM:ROLE:END -->
"""
    composed = f"{base.rstrip()}\n\n{role_overlay}" if base.strip() else role_overlay.lstrip()

    out_path = (
        Path(cwd) / ".omx" / "state" / "team" / team_name
        / "workers" / worker_name / "AGENTS.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(composed, encoding="utf-8")
    return str(out_path)


def remove_team_worker_instructions_file(team_name: str, cwd: str) -> None:
    """Remove the team-scoped model instructions file."""
    path = Path(cwd) / ".omx" / "state" / "team" / team_name / "worker-agents.md"
    path.unlink(missing_ok=True)
