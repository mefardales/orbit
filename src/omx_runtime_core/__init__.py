"""omx-runtime-core: Event-sourced runtime engine for dispatch orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

RUNTIME_SCHEMA_VERSION = 1

RUNTIME_COMMAND_NAMES = [
    "acquire-authority",
    "renew-authority",
    "queue-dispatch",
    "mark-notified",
    "mark-delivered",
    "mark-failed",
    "request-replay",
    "capture-snapshot",
    "create-mailbox-message",
    "mark-mailbox-notified",
    "mark-mailbox-delivered",
]

RUNTIME_EVENT_NAMES = [
    "authority-acquired",
    "authority-renewed",
    "dispatch-queued",
    "dispatch-notified",
    "dispatch-delivered",
    "dispatch-failed",
    "replay-requested",
    "snapshot-captured",
    "mailbox-message-created",
    "mailbox-notified",
    "mailbox-delivered",
]


# ---------------------------------------------------------------------------
# WorkerCli
# ---------------------------------------------------------------------------

class WorkerCli(Enum):
    CODEX = "codex"
    CLAUDE = "claude"

    @classmethod
    def from_label(cls, label: str) -> WorkerCli | str:
        normalized = label.strip().lower()
        if normalized == "claude":
            return cls.CLAUDE
        if normalized == "codex":
            return cls.CODEX
        return normalized  # Other(string)


def submit_presses_for_worker_cli(worker_cli) -> int:
    if worker_cli == WorkerCli.CLAUDE:
        return 1
    return 2


# ---------------------------------------------------------------------------
# DispatchTransportKind
# ---------------------------------------------------------------------------

class DispatchTransportKind(Enum):
    TMUX = "tmux"

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# DispatchOutcomeReason
# ---------------------------------------------------------------------------

class DispatchOutcomeReason(Enum):
    DELIVERED_CONFIRMED = "tmux_send_keys_confirmed"
    DELIVERED_CONFIRMED_ACTIVE_TASK = "tmux_send_keys_confirmed_active_task"
    DELIVERED_UNCONFIRMED = "tmux_send_keys_unconfirmed"
    DEFERRED_LEADER_PANE_MISSING = "leader_pane_missing_deferred"
    DEFERRED_SHELL_NOT_INJECTABLE = "deferred_shell"
    FAILED_MISSING_TARGET = "missing_tmux_target"

    def __str__(self) -> str:
        return self.value


@dataclass
class DispatchOutcomeReasonParameterized:
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.detail}"


def failed_target_resolution(reason: str):
    return DispatchOutcomeReasonParameterized("target_resolution_failed", reason)


def failed_preflight(reason: str):
    return DispatchOutcomeReasonParameterized("preflight_failed", reason)


def failed_send(reason: str):
    return DispatchOutcomeReasonParameterized("send_failed", reason)


# ---------------------------------------------------------------------------
# QueueTransition
# ---------------------------------------------------------------------------

@dataclass
class QueueTransition:
    status: str  # "pending" | "notified" | "failed"
    reason: Any

    @classmethod
    def keep_pending(cls, reason) -> QueueTransition:
        return cls(status="pending", reason=reason)

    @classmethod
    def mark_notified(cls, reason) -> QueueTransition:
        return cls(status="notified", reason=reason)

    @classmethod
    def mark_failed(cls, reason) -> QueueTransition:
        return cls(status="failed", reason=reason)


def classify_dispatch_outcome(
    target_present: bool,
    target_resolved: bool,
    preflight_ok: bool,
    send_ok: bool,
    confirmed: bool,
    active_task: bool,
    retry_remaining: bool,
) -> QueueTransition:
    if not target_present:
        return QueueTransition.mark_failed(DispatchOutcomeReason.FAILED_MISSING_TARGET)
    if not target_resolved:
        return QueueTransition.mark_failed(failed_target_resolution("unresolved_target"))
    if not preflight_ok:
        return QueueTransition.mark_failed(failed_preflight("pane_not_ready"))
    if not send_ok:
        return QueueTransition.mark_failed(failed_send("send_failed"))
    if confirmed:
        reason = (
            DispatchOutcomeReason.DELIVERED_CONFIRMED_ACTIVE_TASK
            if active_task
            else DispatchOutcomeReason.DELIVERED_CONFIRMED
        )
        return QueueTransition.mark_notified(reason)
    if retry_remaining:
        return QueueTransition.keep_pending(DispatchOutcomeReason.DELIVERED_UNCONFIRMED)
    return QueueTransition.mark_failed(DispatchOutcomeReason.DELIVERED_UNCONFIRMED)


# ---------------------------------------------------------------------------
# RuntimeCommand
# ---------------------------------------------------------------------------

@dataclass
class RuntimeCommand:
    command: str
    owner: Optional[str] = None
    lease_id: Optional[str] = None
    leased_until: Optional[str] = None
    request_id: Optional[str] = None
    target: Optional[str] = None
    metadata: Optional[Any] = None
    channel: Optional[str] = None
    reason: Optional[str] = None
    cursor: Optional[str] = None
    message_id: Optional[str] = None
    from_worker: Optional[str] = None
    to_worker: Optional[str] = None
    body: Optional[str] = None

    @classmethod
    def acquire_authority(cls, owner: str, lease_id: str, leased_until: str):
        return cls(command="AcquireAuthority", owner=owner, lease_id=lease_id, leased_until=leased_until)

    @classmethod
    def renew_authority(cls, owner: str, lease_id: str, leased_until: str):
        return cls(command="RenewAuthority", owner=owner, lease_id=lease_id, leased_until=leased_until)

    @classmethod
    def queue_dispatch(cls, request_id: str, target: str, metadata=None):
        return cls(command="QueueDispatch", request_id=request_id, target=target, metadata=metadata)

    @classmethod
    def mark_notified(cls, request_id: str, channel: str):
        return cls(command="MarkNotified", request_id=request_id, channel=channel)

    @classmethod
    def mark_delivered(cls, request_id: str):
        return cls(command="MarkDelivered", request_id=request_id)

    @classmethod
    def mark_failed(cls, request_id: str, reason: str):
        return cls(command="MarkFailed", request_id=request_id, reason=reason)

    @classmethod
    def request_replay(cls, cursor: Optional[str] = None):
        return cls(command="RequestReplay", cursor=cursor)

    @classmethod
    def capture_snapshot(cls):
        return cls(command="CaptureSnapshot")

    @classmethod
    def create_mailbox_message(cls, message_id: str, from_worker: str, to_worker: str, body: str):
        return cls(command="CreateMailboxMessage", message_id=message_id, from_worker=from_worker, to_worker=to_worker, body=body)

    @classmethod
    def mark_mailbox_notified(cls, message_id: str):
        return cls(command="MarkMailboxNotified", message_id=message_id)

    @classmethod
    def mark_mailbox_delivered(cls, message_id: str):
        return cls(command="MarkMailboxDelivered", message_id=message_id)


# ---------------------------------------------------------------------------
# RuntimeEvent
# ---------------------------------------------------------------------------

@dataclass
class RuntimeEvent:
    event: str
    owner: Optional[str] = None
    lease_id: Optional[str] = None
    leased_until: Optional[str] = None
    request_id: Optional[str] = None
    target: Optional[str] = None
    metadata: Optional[Any] = None
    channel: Optional[str] = None
    reason: Optional[str] = None
    cursor: Optional[str] = None
    message_id: Optional[str] = None
    from_worker: Optional[str] = None
    to_worker: Optional[str] = None


# ---------------------------------------------------------------------------
# Snapshot types
# ---------------------------------------------------------------------------

@dataclass
class AuthoritySnapshot:
    owner: Optional[str] = None
    lease_id: Optional[str] = None
    leased_until: Optional[str] = None
    stale: bool = False
    stale_reason: Optional[str] = None

    @classmethod
    def acquire(cls, owner: str, lease_id: str, leased_until: str):
        return cls(owner=owner, lease_id=lease_id, leased_until=leased_until)

    def mark_stale(self, reason: str):
        self.stale = True
        self.stale_reason = reason

    def clear_stale(self):
        self.stale = False
        self.stale_reason = None

    def __str__(self) -> str:
        return (
            f"owner={self.owner or 'none'} lease_id={self.lease_id or 'none'} "
            f"leased_until={self.leased_until or 'none'} stale={self.stale} "
            f"stale_reason={self.stale_reason or 'none'}"
        )


@dataclass
class BacklogSnapshot:
    pending: int = 0
    notified: int = 0
    delivered: int = 0
    failed: int = 0

    def queue_dispatch(self):
        self.pending += 1

    def mark_notified(self) -> bool:
        if self.pending == 0:
            return False
        self.pending -= 1
        self.notified += 1
        return True

    def mark_delivered(self) -> bool:
        if self.notified == 0:
            return False
        self.notified -= 1
        self.delivered += 1
        return True

    def mark_failed(self) -> bool:
        if self.notified == 0:
            return False
        self.notified -= 1
        self.failed += 1
        return True

    def __str__(self) -> str:
        return f"pending={self.pending} notified={self.notified} delivered={self.delivered} failed={self.failed}"


@dataclass
class ReplaySnapshot:
    cursor: Optional[str] = None
    pending_events: int = 0
    last_replayed_event_id: Optional[str] = None
    deferred_leader_notification: bool = False

    def __str__(self) -> str:
        return (
            f"cursor={self.cursor or 'none'} pending_events={self.pending_events} "
            f"last_replayed_event_id={self.last_replayed_event_id or 'none'} "
            f"deferred_leader_notification={self.deferred_leader_notification}"
        )


@dataclass
class ReadinessSnapshot:
    ready: bool = False
    reasons: List[str] = field(default_factory=lambda: ["authority lease not acquired"])

    @classmethod
    def ready_state(cls) -> ReadinessSnapshot:
        return cls(ready=True, reasons=[])

    @classmethod
    def blocked(cls, reason: str) -> ReadinessSnapshot:
        return cls(ready=False, reasons=[reason])

    def add_reason(self, reason: str):
        self.ready = False
        self.reasons.append(reason)

    def __str__(self) -> str:
        if self.ready:
            return "ready"
        return f"blocked({'; '.join(self.reasons)})"


@dataclass
class RuntimeSnapshot:
    schema_version: int = RUNTIME_SCHEMA_VERSION
    authority: AuthoritySnapshot = field(default_factory=AuthoritySnapshot)
    backlog: BacklogSnapshot = field(default_factory=BacklogSnapshot)
    replay: ReplaySnapshot = field(default_factory=ReplaySnapshot)
    readiness: ReadinessSnapshot = field(default_factory=ReadinessSnapshot)

    def ready(self) -> bool:
        return self.readiness.ready

    def __str__(self) -> str:
        return (
            f"schema={self.schema_version} authority={self.authority} "
            f"backlog={self.backlog} replay={self.replay} readiness={self.readiness}"
        )


def runtime_contract_summary() -> str:
    transition = classify_dispatch_outcome(True, True, True, True, True, False, False)
    return (
        f"runtime-schema={RUNTIME_SCHEMA_VERSION}\n"
        f"commands={', '.join(RUNTIME_COMMAND_NAMES)}\n"
        f"events={', '.join(RUNTIME_EVENT_NAMES)}\n"
        f"transport={DispatchTransportKind.TMUX}\n"
        f"queue-transition={transition.status}\n"
        f"snapshot=authority, backlog, replay, readiness"
    )


# Re-export submodules
from .authority import AuthorityLease, AuthorityError
from .dispatch import DispatchLog, DispatchRecord, DispatchStatus, DispatchError
from .engine import RuntimeEngine, EngineError, derive_readiness
from .mailbox import MailboxLog, MailboxRecord, MailboxError
from .replay import ReplayState

__all__ = [
    "RUNTIME_SCHEMA_VERSION",
    "RUNTIME_COMMAND_NAMES",
    "RUNTIME_EVENT_NAMES",
    "WorkerCli",
    "submit_presses_for_worker_cli",
    "DispatchTransportKind",
    "DispatchOutcomeReason",
    "QueueTransition",
    "classify_dispatch_outcome",
    "RuntimeCommand",
    "RuntimeEvent",
    "AuthoritySnapshot",
    "BacklogSnapshot",
    "ReplaySnapshot",
    "ReadinessSnapshot",
    "RuntimeSnapshot",
    "runtime_contract_summary",
    "AuthorityLease",
    "AuthorityError",
    "DispatchLog",
    "DispatchRecord",
    "DispatchStatus",
    "DispatchError",
    "RuntimeEngine",
    "EngineError",
    "derive_readiness",
    "MailboxLog",
    "MailboxRecord",
    "MailboxError",
    "ReplayState",
]
