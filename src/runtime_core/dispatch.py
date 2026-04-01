"""Dispatch log with state-machine transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from . import BacklogSnapshot


class DispatchStatus(Enum):
    PENDING = "pending"
    NOTIFIED = "notified"
    DELIVERED = "delivered"
    FAILED = "failed"


class DispatchError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind

    @classmethod
    def not_found(cls, request_id: str) -> DispatchError:
        return cls("not_found", f"dispatch record not found: {request_id}")

    @classmethod
    def invalid_transition(cls, request_id: str, from_status: DispatchStatus, to_status: DispatchStatus) -> DispatchError:
        return cls("invalid_transition", f"invalid transition for {request_id}: {from_status.value} -> {to_status.value}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class DispatchRecord:
    request_id: str
    target: str
    status: DispatchStatus
    created_at: str
    notified_at: Optional[str] = None
    delivered_at: Optional[str] = None
    failed_at: Optional[str] = None
    reason: Optional[str] = None
    metadata: Optional[Any] = None


class DispatchLog:
    """Ordered log of dispatch records with state-machine transitions."""

    def __init__(self):
        self._records: List[DispatchRecord] = []

    def queue(self, request_id: str, target: str, metadata: Optional[Any] = None) -> None:
        self._records.append(DispatchRecord(
            request_id=request_id,
            target=target,
            status=DispatchStatus.PENDING,
            created_at=_now_iso(),
            metadata=metadata,
        ))

    def mark_notified(self, request_id: str, channel: str) -> None:
        record = self._find(request_id)
        if record.status != DispatchStatus.PENDING:
            raise DispatchError.invalid_transition(request_id, record.status, DispatchStatus.NOTIFIED)
        record.status = DispatchStatus.NOTIFIED
        record.notified_at = _now_iso()
        record.reason = channel

    def mark_delivered(self, request_id: str) -> None:
        record = self._find(request_id)
        if record.status != DispatchStatus.NOTIFIED:
            raise DispatchError.invalid_transition(request_id, record.status, DispatchStatus.DELIVERED)
        record.status = DispatchStatus.DELIVERED
        record.delivered_at = _now_iso()

    def mark_failed(self, request_id: str, reason: str) -> None:
        record = self._find(request_id)
        if record.status not in (DispatchStatus.PENDING, DispatchStatus.NOTIFIED):
            raise DispatchError.invalid_transition(request_id, record.status, DispatchStatus.FAILED)
        record.status = DispatchStatus.FAILED
        record.failed_at = _now_iso()
        record.reason = reason

    def records(self) -> List[DispatchRecord]:
        return list(self._records)

    def to_backlog_snapshot(self) -> BacklogSnapshot:
        snapshot = BacklogSnapshot()
        for r in self._records:
            if r.status == DispatchStatus.PENDING:
                snapshot.pending += 1
            elif r.status == DispatchStatus.NOTIFIED:
                snapshot.notified += 1
            elif r.status == DispatchStatus.DELIVERED:
                snapshot.delivered += 1
            elif r.status == DispatchStatus.FAILED:
                snapshot.failed += 1
        return snapshot

    def _find(self, request_id: str) -> DispatchRecord:
        for r in self._records:
            if r.request_id == request_id:
                return r
        raise DispatchError.not_found(request_id)
