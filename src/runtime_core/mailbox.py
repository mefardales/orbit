"""Inter-worker mailbox log."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


class MailboxError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind

    @classmethod
    def not_found(cls, message_id: str) -> MailboxError:
        return cls("not_found", f"mailbox record not found: {message_id}")

    @classmethod
    def already_delivered(cls, message_id: str) -> MailboxError:
        return cls("already_delivered", f"mailbox message already delivered: {message_id}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class MailboxRecord:
    message_id: str
    from_worker: str
    to_worker: str
    body: str
    created_at: str
    notified_at: Optional[str] = None
    delivered_at: Optional[str] = None


class MailboxLog:
    """Ordered log of inter-worker messages."""

    def __init__(self):
        self._records: List[MailboxRecord] = []

    def create(self, message_id: str, from_worker: str, to_worker: str, body: str) -> None:
        self._records.append(MailboxRecord(
            message_id=message_id,
            from_worker=from_worker,
            to_worker=to_worker,
            body=body,
            created_at=_now_iso(),
        ))

    def mark_notified(self, message_id: str) -> None:
        record = self._find(message_id)
        if record.delivered_at is not None:
            raise MailboxError.already_delivered(message_id)
        record.notified_at = _now_iso()

    def mark_delivered(self, message_id: str) -> None:
        record = self._find(message_id)
        if record.delivered_at is not None:
            raise MailboxError.already_delivered(message_id)
        record.delivered_at = _now_iso()

    def records(self) -> List[MailboxRecord]:
        return list(self._records)

    def _find(self, message_id: str) -> MailboxRecord:
        for r in self._records:
            if r.message_id == message_id:
                return r
        raise MailboxError.not_found(message_id)
