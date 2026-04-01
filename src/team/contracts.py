"""Team contracts: task status rules, event types, approval statuses.

Defines the core vocabulary and validation rules for the team protocol.
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Literal, Optional

# ── Safe name patterns ────────────────────────────────────────────────────────

TEAM_NAME_SAFE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
WORKER_NAME_SAFE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TASK_ID_SAFE_PATTERN = re.compile(r"^\d{1,20}$")


# ── Task statuses ─────────────────────────────────────────────────────────────

TeamTaskStatus = Literal["pending", "blocked", "in_progress", "completed", "failed"]

TEAM_TASK_STATUSES: List[str] = [
    "pending", "blocked", "in_progress", "completed", "failed"
]

TEAM_TERMINAL_TASK_STATUSES: FrozenSet[str] = frozenset({"completed", "failed"})

TEAM_TASK_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "pending": [],
    "blocked": [],
    "in_progress": ["completed", "failed"],
    "completed": [],
    "failed": [],
}


def is_terminal_task_status(status: str) -> bool:
    """Check if a task status is terminal (completed or failed)."""
    return status in TEAM_TERMINAL_TASK_STATUSES


def can_transition_task_status(from_status: str, to_status: str) -> bool:
    """Validate whether a task status transition is permitted."""
    allowed = TEAM_TASK_STATUS_TRANSITIONS.get(from_status)
    if allowed is None:
        return False
    return to_status in allowed


# ── Event types ───────────────────────────────────────────────────────────────

TEAM_EVENT_TYPES: List[str] = [
    "task_completed",
    "task_failed",
    "worker_state_changed",
    "worker_idle",
    "worker_stopped",
    "message_received",
    "leader_notification_deferred",
    "all_workers_idle",
    "shutdown_ack",
    "shutdown_gate",
    "shutdown_gate_forced",
    "ralph_cleanup_policy",
    "ralph_cleanup_summary",
    "approval_decision",
    "team_leader_nudge",
    "worker_diff_activity",
    "worker_diff_report",
    "worker_merge_report",
    "worker_merge_conflict",
    "worker_cherry_pick_detected",
    "worker_cherry_pick_applied",
    "worker_cherry_pick_conflict",
    "worker_rebase_applied",
    "worker_rebase_conflict",
    "worker_cross_rebase_applied",
    "worker_cross_rebase_conflict",
    "worker_cross_rebase_skipped",
    "worker_stale_diff",
    "worker_stale_heartbeat",
    "worker_stale_stdout",
]

TEAM_WAKEABLE_EVENT_TYPES: FrozenSet[str] = frozenset({
    "worker_state_changed",
    "task_completed",
    "task_failed",
    "worker_stopped",
    "message_received",
    "leader_notification_deferred",
    "all_workers_idle",
    "team_leader_nudge",
    "worker_merge_conflict",
    "worker_cherry_pick_conflict",
    "worker_rebase_conflict",
    "worker_cross_rebase_conflict",
    "worker_stale_diff",
    "worker_stale_heartbeat",
    "worker_stale_stdout",
})


def is_wakeable_event_type(event_type: str) -> bool:
    """Check if an event type should wake the leader."""
    return event_type in TEAM_WAKEABLE_EVENT_TYPES


# ── Approval statuses ─────────────────────────────────────────────────────────

TeamTaskApprovalStatus = Literal["pending", "approved", "rejected"]

TEAM_TASK_APPROVAL_STATUSES: List[str] = ["pending", "approved", "rejected"]
