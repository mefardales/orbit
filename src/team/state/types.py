"""Shared state types for team orchestration.

Mirrors the TypeScript state/types.ts with Python dataclasses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union


# ── Safe name patterns ────────────────────────────────────────────────────────

TEAM_NAME_SAFE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
WORKER_NAME_SAFE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TASK_ID_SAFE_PATTERN = re.compile(r"^\d{1,20}$")

DEFAULT_MAX_WORKERS = 20
ABSOLUTE_MAX_WORKERS = 20


# ── Worker status ─────────────────────────────────────────────────────────────

WorkerState = Literal[
    "idle", "working", "blocked", "done", "failed", "draining", "unknown"
]


@dataclass
class WorkerStatus:
    state: WorkerState = "unknown"
    current_task_id: Optional[str] = None
    reason: Optional[str] = None
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = datetime.utcnow().isoformat() + "Z"


@dataclass
class WorkerHeartbeat:
    pid: int = 0
    last_turn_at: str = ""
    turn_count: int = 0
    alive: bool = False


# ── Worker info ───────────────────────────────────────────────────────────────

WorkerCli = Literal["codex", "claude", "gemini"]


@dataclass
class WorkerInfo:
    name: str = ""
    index: int = 0
    role: str = ""
    worker_cli: Optional[WorkerCli] = None
    assigned_tasks: List[str] = field(default_factory=list)
    pid: Optional[int] = None
    pane_id: Optional[str] = None
    working_dir: Optional[str] = None
    worktree_repo_root: Optional[str] = None
    worktree_path: Optional[str] = None
    worktree_branch: Optional[str] = None
    worktree_detached: Optional[bool] = None
    worktree_created: Optional[bool] = None
    team_state_root: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if v is not None:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerInfo":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# ── Task types ────────────────────────────────────────────────────────────────

TeamTaskStatus = Literal["pending", "blocked", "in_progress", "completed", "failed"]

TEAM_TASK_STATUSES: List[TeamTaskStatus] = [
    "pending", "blocked", "in_progress", "completed", "failed"
]
TEAM_TERMINAL_TASK_STATUSES = frozenset({"completed", "failed"})


@dataclass
class TeamTaskClaim:
    owner: str = ""
    token: str = ""
    leased_until: str = ""


@dataclass
class TeamTask:
    id: str = ""
    subject: str = ""
    description: str = ""
    status: TeamTaskStatus = "pending"
    requires_code_change: Optional[bool] = None
    role: Optional[str] = None
    owner: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    blocked_by: Optional[List[str]] = None
    depends_on: Optional[List[str]] = None
    version: int = 1
    claim: Optional[TeamTaskClaim] = None
    created_at: str = ""
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if v is not None:
                if k == "claim" and isinstance(v, TeamTaskClaim):
                    d[k] = v.__dict__
                else:
                    d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeamTask":
        claim_data = data.pop("claim", None)
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        task = cls(**{k: v for k, v in data.items() if k in known})
        if claim_data and isinstance(claim_data, dict):
            task.claim = TeamTaskClaim(**claim_data)
        return task


# ── Team config ───────────────────────────────────────────────────────────────

WorkspaceModeType = Literal["single", "worktree"]
LaunchMode = Literal["interactive", "prompt"]
DisplayMode = Literal["split_pane", "auto"]
DispatchMode = Literal["hook_preferred_with_fallback", "transport_direct"]


@dataclass
class TeamPolicy:
    display_mode: DisplayMode = "auto"
    worker_launch_mode: LaunchMode = "interactive"
    dispatch_mode: DispatchMode = "transport_direct"
    dispatch_ack_timeout_ms: int = 5000


@dataclass
class TeamGovernance:
    delegation_only: bool = True
    plan_approval_required: bool = False
    nested_teams_allowed: bool = False
    one_team_per_leader_session: bool = True
    cleanup_requires_all_workers_inactive: bool = True


@dataclass
class TeamConfig:
    name: str = ""
    task: str = ""
    agent_type: str = "executor"
    worker_launch_mode: LaunchMode = "interactive"
    lifecycle_profile: str = "default"
    worker_count: int = 0
    max_workers: int = DEFAULT_MAX_WORKERS
    workers: List[WorkerInfo] = field(default_factory=list)
    created_at: str = ""
    tmux_session: str = ""
    next_task_id: int = 1
    leader_cwd: Optional[str] = None
    team_state_root: Optional[str] = None
    workspace_mode: Optional[WorkspaceModeType] = None
    leader_pane_id: Optional[str] = None
    hud_pane_id: Optional[str] = None
    resize_hook_name: Optional[str] = None
    resize_hook_target: Optional[str] = None
    next_worker_index: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"


# ── Dispatch types ────────────────────────────────────────────────────────────

DispatchRequestKind = Literal["inbox", "mailbox", "nudge"]
DispatchRequestStatus = Literal["pending", "notified", "delivered", "failed"]
DispatchTransportPreference = Literal[
    "hook_preferred_with_fallback", "transport_direct", "prompt_stdin"
]


@dataclass
class TeamDispatchRequest:
    request_id: str = ""
    kind: DispatchRequestKind = "inbox"
    team_name: str = ""
    to_worker: str = ""
    worker_index: Optional[int] = None
    pane_id: Optional[str] = None
    trigger_message: str = ""
    message_id: Optional[str] = None
    inbox_correlation_key: Optional[str] = None
    transport_preference: DispatchTransportPreference = "hook_preferred_with_fallback"
    fallback_allowed: bool = True
    status: DispatchRequestStatus = "pending"
    attempt_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    notified_at: Optional[str] = None
    delivered_at: Optional[str] = None
    failed_at: Optional[str] = None
    last_reason: Optional[str] = None


# ── Mailbox types ─────────────────────────────────────────────────────────────


@dataclass
class TeamMailboxMessage:
    message_id: str = ""
    from_worker: str = ""
    to_worker: str = ""
    body: str = ""
    created_at: str = ""
    notified_at: Optional[str] = None
    delivered_at: Optional[str] = None


@dataclass
class TeamMailbox:
    worker: str = ""
    messages: List[TeamMailboxMessage] = field(default_factory=list)


# ── Event types ───────────────────────────────────────────────────────────────

TEAM_EVENT_TYPES = [
    "task_completed", "task_failed", "worker_state_changed", "worker_idle",
    "worker_stopped", "message_received", "leader_notification_deferred",
    "all_workers_idle", "shutdown_ack", "shutdown_gate", "shutdown_gate_forced",
    "approval_decision", "team_leader_nudge", "worker_diff_activity",
    "worker_diff_report", "worker_merge_report", "worker_merge_conflict",
    "worker_cherry_pick_detected", "worker_cherry_pick_applied",
    "worker_cherry_pick_conflict", "worker_rebase_applied",
    "worker_rebase_conflict", "worker_cross_rebase_applied",
    "worker_cross_rebase_conflict", "worker_cross_rebase_skipped",
    "worker_stale_diff", "worker_stale_heartbeat", "worker_stale_stdout",
]

TEAM_WAKEABLE_EVENT_TYPES = frozenset({
    "worker_state_changed", "task_completed", "task_failed", "worker_stopped",
    "message_received", "leader_notification_deferred", "all_workers_idle",
    "team_leader_nudge", "worker_merge_conflict", "worker_cherry_pick_conflict",
    "worker_rebase_conflict", "worker_cross_rebase_conflict",
    "worker_stale_diff", "worker_stale_heartbeat", "worker_stale_stdout",
})

TeamEventType = str


@dataclass
class TeamEvent:
    event_id: str = ""
    team: str = ""
    type: TeamEventType = ""
    worker: str = ""
    task_id: Optional[str] = None
    message_id: Optional[str] = None
    reason: Optional[str] = None
    state: Optional[WorkerState] = None
    prev_state: Optional[WorkerState] = None
    worker_count: Optional[int] = None
    to_worker: Optional[str] = None
    source_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"


# ── Monitor snapshot ──────────────────────────────────────────────────────────


@dataclass
class TeamMonitorSnapshotState:
    task_status_by_id: Dict[str, str] = field(default_factory=dict)
    worker_alive_by_name: Dict[str, bool] = field(default_factory=dict)
    worker_state_by_name: Dict[str, str] = field(default_factory=dict)
    worker_turn_count_by_name: Dict[str, int] = field(default_factory=dict)
    worker_task_id_by_name: Dict[str, str] = field(default_factory=dict)
    mailbox_notified_by_message_id: Dict[str, str] = field(default_factory=dict)
    completed_event_task_ids: Dict[str, bool] = field(default_factory=dict)


# ── Phase state ───────────────────────────────────────────────────────────────

TeamPhaseType = Literal[
    "team-plan", "team-prd", "team-exec", "team-verify", "team-fix"
]
TerminalPhaseType = Literal["complete", "failed", "cancelled"]


@dataclass
class TeamPhaseState:
    current_phase: str = "team-plan"
    max_fix_attempts: int = 3
    current_fix_attempt: int = 0
    transitions: List[Dict[str, str]] = field(default_factory=list)
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = datetime.utcnow().isoformat() + "Z"


# ── Shutdown ──────────────────────────────────────────────────────────────────

ShutdownStatus = Literal["accept", "reject"]


@dataclass
class ShutdownAck:
    status: ShutdownStatus = "accept"
    reason: Optional[str] = None
    updated_at: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def validate_team_name(name: str) -> str:
    """Validate and return a safe team name."""
    if not TEAM_NAME_SAFE_PATTERN.match(name):
        raise ValueError(f"Invalid team name: {name!r}")
    return name


def validate_worker_name(name: str) -> str:
    """Validate and return a safe worker name."""
    if not WORKER_NAME_SAFE_PATTERN.match(name):
        raise ValueError(f"Invalid worker name: {name!r}")
    return name


def is_terminal_task_status(status: TeamTaskStatus) -> bool:
    return status in TEAM_TERMINAL_TASK_STATUSES


def is_wakeable_event_type(event_type: str) -> bool:
    return event_type in TEAM_WAKEABLE_EVENT_TYPES
