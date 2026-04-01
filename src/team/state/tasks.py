"""Task lifecycle management: claiming, transitions, readiness checks.

Implements claim-based optimistic concurrency for multi-worker task ownership.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from .types import (
    TeamTask,
    TeamTaskClaim,
    TeamTaskStatus,
    TEAM_TERMINAL_TASK_STATUSES,
    is_terminal_task_status,
)


# ── Task status transition rules ──────────────────────────────────────────────

TASK_STATUS_TRANSITIONS: Dict[TeamTaskStatus, List[TeamTaskStatus]] = {
    "pending": [],
    "blocked": [],
    "in_progress": ["completed", "failed"],
    "completed": [],
    "failed": [],
}


def can_transition_task_status(from_status: TeamTaskStatus, to_status: TeamTaskStatus) -> bool:
    """Check if a task status transition is valid."""
    allowed = TASK_STATUS_TRANSITIONS.get(from_status, [])
    return to_status in allowed


# ── File helpers ──────────────────────────────────────────────────────────────


def _team_dir(team_name: str, cwd: str) -> Path:
    return Path(cwd) / ".omx" / "state" / "team" / team_name


def _task_file(team_name: str, task_id: str, cwd: str) -> Path:
    return _team_dir(team_name, cwd) / "tasks" / f"task-{task_id}.json"


def _read_task(team_name: str, task_id: str, cwd: str) -> Optional[TeamTask]:
    path = _task_file(team_name, task_id, cwd)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return TeamTask.from_dict(data)
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def _write_task(team_name: str, task_id: str, cwd: str, task: TeamTask) -> None:
    path = _task_file(team_name, task_id, cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task.to_dict(), indent=2), encoding="utf-8")


def _is_claim_expired(claim: Optional[TeamTaskClaim]) -> bool:
    if not claim or not claim.leased_until:
        return False
    try:
        return datetime.fromisoformat(claim.leased_until.replace("Z", "+00:00")) <= datetime.now(
            tz=datetime.now().astimezone().tzinfo
        )
    except (ValueError, TypeError):
        return False


# ── Readiness ─────────────────────────────────────────────────────────────────


class TaskReadiness:
    """Result of computing whether a task is ready to start."""

    def __init__(self, ready: bool, reason: Optional[str] = None,
                 dependencies: Optional[List[str]] = None):
        self.ready = ready
        self.reason = reason
        self.dependencies = dependencies or []


def compute_task_readiness(
    team_name: str,
    task_id: str,
    cwd: str,
) -> TaskReadiness:
    """Check if a task's dependencies are all completed."""
    task = _read_task(team_name, task_id, cwd)
    if not task:
        return TaskReadiness(False, "blocked_dependency", [])

    dep_ids = task.depends_on or task.blocked_by or []
    if not dep_ids:
        return TaskReadiness(True)

    incomplete: List[str] = []
    for dep_id in dep_ids:
        dep = _read_task(team_name, dep_id, cwd)
        if not dep or dep.status != "completed":
            incomplete.append(dep_id)

    if incomplete:
        return TaskReadiness(False, "blocked_dependency", incomplete)
    return TaskReadiness(True)


# ── Claim result types ────────────────────────────────────────────────────────

ClaimError = Literal[
    "claim_conflict", "blocked_dependency", "task_not_found",
    "already_terminal", "worker_not_found"
]

TransitionError = Literal[
    "claim_conflict", "invalid_transition", "task_not_found",
    "already_terminal", "lease_expired"
]

ReleaseError = Literal[
    "claim_conflict", "task_not_found", "already_terminal", "lease_expired"
]

ReclaimError = Literal[
    "claim_conflict", "task_not_found", "already_terminal", "lease_active"
]


# ── Claim task ────────────────────────────────────────────────────────────────


def claim_task(
    team_name: str,
    task_id: str,
    worker_name: str,
    cwd: str,
    expected_version: Optional[int] = None,
) -> Tuple[bool, Union[TeamTask, ClaimError], Optional[str]]:
    """Claim a task for a worker. Returns (ok, task_or_error, claim_token)."""
    task = _read_task(team_name, task_id, cwd)
    if not task:
        return False, "task_not_found", None

    readiness = compute_task_readiness(team_name, task_id, cwd)
    if not readiness.ready:
        return False, "blocked_dependency", None

    if expected_version is not None and task.version != expected_version:
        return False, "claim_conflict", None

    if is_terminal_task_status(task.status):
        return False, "already_terminal", None

    if task.status == "in_progress":
        if not _is_claim_expired(task.claim):
            return False, "claim_conflict", None
        task.owner = None
        task.claim = None
        task.status = "pending"

    if task.status in ("pending", "blocked"):
        if task.claim and not _is_claim_expired(task.claim):
            return False, "claim_conflict", None
        if task.owner and task.owner != worker_name:
            return False, "claim_conflict", None

    claim_token = str(uuid.uuid4())
    lease_until = (datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z"

    task.status = "in_progress"
    task.owner = worker_name
    task.claim = TeamTaskClaim(
        owner=worker_name,
        token=claim_token,
        leased_until=lease_until,
    )
    task.version += 1

    _write_task(team_name, task_id, cwd, task)
    return True, task, claim_token


# ── Transition task status ────────────────────────────────────────────────────


def transition_task_status(
    team_name: str,
    task_id: str,
    from_status: TeamTaskStatus,
    to_status: TeamTaskStatus,
    claim_token: str,
    cwd: str,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> Tuple[bool, Union[TeamTask, TransitionError]]:
    """Transition a task from one status to another with claim validation."""
    if not can_transition_task_status(from_status, to_status):
        return False, "invalid_transition"

    task = _read_task(team_name, task_id, cwd)
    if not task:
        return False, "task_not_found"

    if is_terminal_task_status(task.status):
        return False, "already_terminal"

    if not can_transition_task_status(task.status, to_status):
        return False, "invalid_transition"

    if task.status != from_status:
        return False, "invalid_transition"

    if not task.owner or not task.claim or task.claim.token != claim_token:
        return False, "claim_conflict"

    if _is_claim_expired(task.claim):
        return False, "lease_expired"

    task.status = to_status
    task.completed_at = datetime.utcnow().isoformat() + "Z"
    task.claim = None
    task.version += 1

    if to_status == "completed":
        task.result = result
        task.error = None
    elif to_status == "failed":
        task.error = error
        task.result = None

    _write_task(team_name, task_id, cwd, task)
    return True, task


# ── Release task claim ────────────────────────────────────────────────────────


def release_task_claim(
    team_name: str,
    task_id: str,
    claim_token: str,
    cwd: str,
) -> Tuple[bool, Union[TeamTask, ReleaseError]]:
    """Release a task claim, returning it to pending."""
    task = _read_task(team_name, task_id, cwd)
    if not task:
        return False, "task_not_found"

    if task.status == "pending" and not task.claim and not task.owner:
        return True, task

    if is_terminal_task_status(task.status):
        return False, "already_terminal"

    if not task.owner or not task.claim or task.claim.token != claim_token:
        return False, "claim_conflict"

    if _is_claim_expired(task.claim):
        return False, "lease_expired"

    task.status = "pending"
    task.owner = None
    task.claim = None
    task.version += 1

    _write_task(team_name, task_id, cwd, task)
    return True, task


# ── Reclaim expired ──────────────────────────────────────────────────────────


def reclaim_expired_task_claim(
    team_name: str,
    task_id: str,
    cwd: str,
) -> Tuple[bool, Union[TeamTask, ReclaimError], bool]:
    """Reclaim a task with an expired lease. Returns (ok, task_or_error, reclaimed)."""
    task = _read_task(team_name, task_id, cwd)
    if not task:
        return False, "task_not_found", False

    if is_terminal_task_status(task.status):
        return False, "already_terminal", False

    if task.status != "in_progress" or not task.claim:
        return True, task, False

    if not _is_claim_expired(task.claim):
        return False, "lease_active", False

    task.status = "pending"
    task.owner = None
    task.claim = None
    task.version += 1

    _write_task(team_name, task_id, cwd, task)
    return True, task, True


# ── List tasks ────────────────────────────────────────────────────────────────


def list_tasks(team_name: str, cwd: str) -> List[TeamTask]:
    """List all tasks for a team, sorted by numeric ID."""
    tasks_dir = _team_dir(team_name, cwd) / "tasks"
    if not tasks_dir.exists():
        return []

    tasks: List[TeamTask] = []
    import re

    for entry in tasks_dir.iterdir():
        if not entry.is_file():
            continue
        match = re.match(r"^task-(\d+)\.json$", entry.name)
        if not match:
            continue

        task_id = match.group(1)
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            task = TeamTask.from_dict(data)
            if task.id == task_id:
                tasks.append(task)
        except (json.JSONDecodeError, OSError, TypeError):
            continue

    tasks.sort(key=lambda t: int(t.id) if t.id.isdigit() else 0)
    return tasks
