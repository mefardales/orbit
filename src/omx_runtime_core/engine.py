"""RuntimeEngine: event-sourced command processor with persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from . import (
    RUNTIME_SCHEMA_VERSION,
    ReadinessSnapshot,
    RuntimeCommand,
    RuntimeEvent,
    RuntimeSnapshot,
)
from .authority import AuthorityError, AuthorityLease
from .dispatch import DispatchError, DispatchLog, DispatchStatus
from .mailbox import MailboxError, MailboxLog
from .replay import ReplayState


class EngineError(Exception):
    """Wraps authority, dispatch, mailbox, IO, and JSON errors."""
    pass


class RuntimeEngine:
    """Event-sourced runtime engine that processes commands and emits events."""

    def __init__(self):
        self._authority = AuthorityLease()
        self._dispatch = DispatchLog()
        self._mailbox = MailboxLog()
        self._replay = ReplayState()
        self._event_log: List[RuntimeEvent] = []
        self._state_dir: Optional[Path] = None

    def with_state_dir(self, path: str | Path) -> RuntimeEngine:
        self._state_dir = Path(path)
        return self

    def process(self, command: RuntimeCommand) -> RuntimeEvent:
        """Process a command and return the resulting event."""
        cmd = command.command

        if cmd == "AcquireAuthority":
            self._authority.acquire(command.owner, command.lease_id, command.leased_until)
            event = RuntimeEvent(event="AuthorityAcquired", owner=command.owner, lease_id=command.lease_id, leased_until=command.leased_until)

        elif cmd == "RenewAuthority":
            self._authority.renew(command.owner, command.lease_id, command.leased_until)
            event = RuntimeEvent(event="AuthorityRenewed", owner=command.owner, lease_id=command.lease_id, leased_until=command.leased_until)

        elif cmd == "QueueDispatch":
            self._dispatch.queue(command.request_id, command.target, command.metadata)
            event = RuntimeEvent(event="DispatchQueued", request_id=command.request_id, target=command.target, metadata=command.metadata)

        elif cmd == "MarkNotified":
            self._dispatch.mark_notified(command.request_id, command.channel)
            event = RuntimeEvent(event="DispatchNotified", request_id=command.request_id, channel=command.channel)

        elif cmd == "MarkDelivered":
            self._dispatch.mark_delivered(command.request_id)
            event = RuntimeEvent(event="DispatchDelivered", request_id=command.request_id)

        elif cmd == "MarkFailed":
            self._dispatch.mark_failed(command.request_id, command.reason)
            event = RuntimeEvent(event="DispatchFailed", request_id=command.request_id, reason=command.reason)

        elif cmd == "RequestReplay":
            self._replay.request_replay(command.cursor)
            event = RuntimeEvent(event="ReplayRequested", cursor=command.cursor)

        elif cmd == "CaptureSnapshot":
            event = RuntimeEvent(event="SnapshotCaptured")

        elif cmd == "CreateMailboxMessage":
            self._mailbox.create(command.message_id, command.from_worker, command.to_worker, command.body)
            event = RuntimeEvent(event="MailboxMessageCreated", message_id=command.message_id, from_worker=command.from_worker, to_worker=command.to_worker)

        elif cmd == "MarkMailboxNotified":
            self._mailbox.mark_notified(command.message_id)
            event = RuntimeEvent(event="MailboxNotified", message_id=command.message_id)

        elif cmd == "MarkMailboxDelivered":
            self._mailbox.mark_delivered(command.message_id)
            event = RuntimeEvent(event="MailboxDelivered", message_id=command.message_id)

        else:
            raise EngineError(f"unknown command: {cmd}")

        self._event_log.append(event)
        return event

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            schema_version=RUNTIME_SCHEMA_VERSION,
            authority=self._authority.to_snapshot(),
            backlog=self._dispatch.to_backlog_snapshot(),
            replay=self._replay.to_snapshot(),
            readiness=derive_readiness(self._authority, self._dispatch, self._replay),
        )

    def event_log(self) -> List[RuntimeEvent]:
        return list(self._event_log)

    def compact(self) -> None:
        """Remove events for dispatches in terminal states."""
        terminal_ids = {
            r.request_id
            for r in self._dispatch.records()
            if r.status in (DispatchStatus.DELIVERED, DispatchStatus.FAILED)
        }
        self._event_log = [
            e for e in self._event_log
            if not (
                e.event in ("DispatchQueued", "DispatchNotified", "DispatchDelivered", "DispatchFailed")
                and e.request_id in terminal_ids
            )
        ]

    def persist(self) -> None:
        if self._state_dir is None:
            raise EngineError("no state_dir configured")
        self._state_dir.mkdir(parents=True, exist_ok=True)

        snapshot = self.snapshot()
        _write_json(self._state_dir / "snapshot.json", _snapshot_to_dict(snapshot))
        _write_json(self._state_dir / "events.json", [_event_to_dict(e) for e in self._event_log])

    def write_compatibility_view(self) -> None:
        if self._state_dir is None:
            raise EngineError("no state_dir configured")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        snapshot = self.snapshot()
        _write_json(self._state_dir / "authority.json", _authority_to_dict(snapshot.authority))
        _write_json(self._state_dir / "backlog.json", _backlog_to_dict(snapshot.backlog))
        _write_json(self._state_dir / "readiness.json", _readiness_to_dict(snapshot.readiness))
        _write_json(self._state_dir / "replay.json", _replay_to_dict(snapshot.replay))

    @classmethod
    def load(cls, state_dir: str | Path) -> RuntimeEngine:
        path = Path(state_dir)
        events_path = path / "events.json"
        with open(events_path) as f:
            events_data = json.load(f)

        engine = cls()
        engine._state_dir = path
        for ed in events_data:
            event = _dict_to_event(ed)
            _replay_event(engine, event)
            engine._event_log.append(event)
        return engine


def derive_readiness(authority: AuthorityLease, dispatch: DispatchLog, replay: ReplayState) -> ReadinessSnapshot:
    reasons = []
    if not authority.is_held():
        reasons.append("authority lease not acquired")
    elif authority.is_stale():
        snap = authority.to_snapshot()
        reasons.append(f"authority lease is stale: {snap.stale_reason or ''}")

    replay_snap = replay.to_snapshot()
    if replay_snap.pending_events > 0:
        reasons.append(f"replay has {replay_snap.pending_events} pending events")

    if not reasons:
        return ReadinessSnapshot.ready_state()
    result = ReadinessSnapshot.blocked(reasons[0])
    for r in reasons[1:]:
        result.add_reason(r)
    return result


def _replay_event(engine: RuntimeEngine, event: RuntimeEvent) -> None:
    e = event.event
    if e == "AuthorityAcquired":
        try:
            engine._authority.acquire(event.owner, event.lease_id, event.leased_until)
        except Exception:
            pass
    elif e == "AuthorityRenewed":
        try:
            engine._authority.renew(event.owner, event.lease_id, event.leased_until)
        except Exception:
            pass
    elif e == "DispatchQueued":
        engine._dispatch.queue(event.request_id, event.target, event.metadata)
    elif e == "DispatchNotified":
        try:
            engine._dispatch.mark_notified(event.request_id, event.channel)
        except Exception:
            pass
    elif e == "DispatchDelivered":
        try:
            engine._dispatch.mark_delivered(event.request_id)
        except Exception:
            pass
    elif e == "DispatchFailed":
        try:
            engine._dispatch.mark_failed(event.request_id, event.reason)
        except Exception:
            pass
    elif e == "ReplayRequested":
        engine._replay.request_replay(event.cursor)
    elif e == "MailboxMessageCreated":
        engine._mailbox.create(event.message_id, event.from_worker, event.to_worker, "")
    elif e == "MailboxNotified":
        try:
            engine._mailbox.mark_notified(event.message_id)
        except Exception:
            pass
    elif e == "MailboxDelivered":
        try:
            engine._mailbox.mark_delivered(event.message_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _snapshot_to_dict(s) -> dict:
    return {
        "schema_version": s.schema_version,
        "authority": _authority_to_dict(s.authority),
        "backlog": _backlog_to_dict(s.backlog),
        "replay": _replay_to_dict(s.replay),
        "readiness": _readiness_to_dict(s.readiness),
    }


def _authority_to_dict(a) -> dict:
    return {"owner": a.owner, "lease_id": a.lease_id, "leased_until": a.leased_until, "stale": a.stale, "stale_reason": a.stale_reason}


def _backlog_to_dict(b) -> dict:
    return {"pending": b.pending, "notified": b.notified, "delivered": b.delivered, "failed": b.failed}


def _replay_to_dict(r) -> dict:
    return {"cursor": r.cursor, "pending_events": r.pending_events, "last_replayed_event_id": r.last_replayed_event_id, "deferred_leader_notification": r.deferred_leader_notification}


def _readiness_to_dict(r) -> dict:
    return {"ready": r.ready, "reasons": r.reasons}


def _event_to_dict(e: RuntimeEvent) -> dict:
    d = {"event": e.event}
    for attr in ("owner", "lease_id", "leased_until", "request_id", "target", "metadata", "channel", "reason", "cursor", "message_id", "from_worker", "to_worker"):
        val = getattr(e, attr, None)
        if val is not None:
            d[attr] = val
    return d


def _dict_to_event(d: dict) -> RuntimeEvent:
    return RuntimeEvent(**{k: v for k, v in d.items() if k in RuntimeEvent.__dataclass_fields__})
