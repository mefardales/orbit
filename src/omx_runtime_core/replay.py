"""Replay state tracking for event deduplication."""

from __future__ import annotations

from typing import Optional, Set

from . import ReplaySnapshot


class ReplayState:
    """Tracks replay cursor, seen event IDs, and deferred leader notification."""

    def __init__(self):
        self._cursor: Optional[str] = None
        self._seen_event_ids: Set[str] = set()
        self._deferred_leader_notification: bool = False

    def request_replay(self, cursor: Optional[str]) -> None:
        self._cursor = cursor

    def record_event(self, event_id: str) -> bool:
        """Returns True if event is new, False if already seen."""
        if event_id in self._seen_event_ids:
            return False
        self._seen_event_ids.add(event_id)
        return True

    def defer_leader_notification(self) -> None:
        self._deferred_leader_notification = True

    def clear_deferred(self) -> None:
        self._deferred_leader_notification = False

    def cursor(self) -> Optional[str]:
        return self._cursor

    def seen_count(self) -> int:
        return len(self._seen_event_ids)

    def is_deferred(self) -> bool:
        return self._deferred_leader_notification

    def to_snapshot(self) -> ReplaySnapshot:
        return ReplaySnapshot(
            cursor=self._cursor,
            pending_events=0,
            last_replayed_event_id=None,
            deferred_leader_notification=self._deferred_leader_notification,
        )
