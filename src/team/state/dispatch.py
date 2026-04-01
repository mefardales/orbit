"""Task dispatch request management.

Handles enqueuing, deduplication, and status transitions for dispatch requests
that coordinate message delivery to workers via tmux or hook-based transports.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from .types import (
    DispatchRequestKind,
    DispatchRequestStatus,
    DispatchTransportPreference,
    TeamDispatchRequest,
    validate_worker_name,
)


# ── Validation helpers ────────────────────────────────────────────────────────

_VALID_KINDS = frozenset({"inbox", "mailbox", "nudge"})
_VALID_STATUSES = frozenset({"pending", "notified", "delivered", "failed"})

# Allowed status transitions
_STATUS_TRANSITIONS: Dict[str, frozenset] = {
    "pending": frozenset({"notified", "failed"}),
    "notified": frozenset({"delivered", "failed"}),
    "failed": frozenset({"notified"}),
    "delivered": frozenset(),
}


def _is_dispatch_kind(value: Any) -> bool:
    return value in _VALID_KINDS


def _is_dispatch_status(value: Any) -> bool:
    return value in _VALID_STATUSES


def _can_transition(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True
    return to_status in _STATUS_TRANSITIONS.get(from_status, frozenset())


# ── Normalization ─────────────────────────────────────────────────────────────


def normalize_dispatch_request(
    team_name: str,
    raw: Dict[str, Any],
    now_iso: Optional[str] = None,
) -> Optional[TeamDispatchRequest]:
    """Normalize a raw dict into a validated TeamDispatchRequest.

    Returns None if required fields are missing or invalid.
    """
    if now_iso is None:
        now_iso = datetime.utcnow().isoformat() + "Z"

    kind = raw.get("kind")
    if not _is_dispatch_kind(kind):
        return None

    to_worker = raw.get("to_worker", "")
    if not isinstance(to_worker, str) or not to_worker.strip():
        return None

    trigger = raw.get("trigger_message", "")
    if not isinstance(trigger, str) or not trigger.strip():
        return None

    status = raw.get("status", "pending")
    if not _is_dispatch_status(status):
        status = "pending"

    request_id = raw.get("request_id", "")
    if not isinstance(request_id, str) or not request_id.strip():
        request_id = str(uuid.uuid4())

    attempt_count = raw.get("attempt_count", 0)
    if not isinstance(attempt_count, (int, float)) or attempt_count < 0:
        attempt_count = 0
    attempt_count = max(0, int(attempt_count))

    transport = raw.get("transport_preference", "hook_preferred_with_fallback")
    if transport not in ("transport_direct", "prompt_stdin", "hook_preferred_with_fallback"):
        transport = "hook_preferred_with_fallback"

    def _opt_str(key: str) -> Optional[str]:
        v = raw.get(key)
        return v if isinstance(v, str) and v.strip() else None

    return TeamDispatchRequest(
        request_id=request_id,
        kind=kind,
        team_name=team_name,
        to_worker=to_worker,
        worker_index=raw.get("worker_index") if isinstance(raw.get("worker_index"), int) else None,
        pane_id=_opt_str("pane_id"),
        trigger_message=trigger,
        message_id=_opt_str("message_id"),
        inbox_correlation_key=_opt_str("inbox_correlation_key"),
        transport_preference=transport,
        fallback_allowed=raw.get("fallback_allowed", True) is not False,
        status=status,
        attempt_count=attempt_count,
        created_at=_opt_str("created_at") or now_iso,
        updated_at=_opt_str("updated_at") or now_iso,
        notified_at=_opt_str("notified_at"),
        delivered_at=_opt_str("delivered_at"),
        failed_at=_opt_str("failed_at"),
        last_reason=_opt_str("last_reason"),
    )


# ── Dedup logic ───────────────────────────────────────────────────────────────


def _equivalent_pending(existing: TeamDispatchRequest, kind: str, to_worker: str,
                        message_id: Optional[str], inbox_key: Optional[str],
                        trigger: str) -> bool:
    if existing.status != "pending":
        return False
    if existing.kind != kind or existing.to_worker != to_worker:
        return False
    if kind == "mailbox":
        return bool(message_id) and existing.message_id == message_id
    if kind == "inbox" and inbox_key:
        return existing.inbox_correlation_key == inbox_key
    return existing.trigger_message == trigger


# ── File I/O helpers ──────────────────────────────────────────────────────────


def _dispatch_file(team_name: str, cwd: str) -> Path:
    return Path(cwd) / ".omx" / "state" / "team" / team_name / "dispatch-requests.json"


def _read_requests(team_name: str, cwd: str) -> List[Dict[str, Any]]:
    path = _dispatch_file(team_name, cwd)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_requests(team_name: str, requests: List[Dict[str, Any]], cwd: str) -> None:
    path = _dispatch_file(team_name, cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(requests, indent=2), encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────────


def enqueue_dispatch_request(
    team_name: str,
    cwd: str,
    *,
    kind: DispatchRequestKind,
    to_worker: str,
    trigger_message: str,
    worker_index: Optional[int] = None,
    pane_id: Optional[str] = None,
    message_id: Optional[str] = None,
    inbox_correlation_key: Optional[str] = None,
    transport_preference: DispatchTransportPreference = "hook_preferred_with_fallback",
    fallback_allowed: bool = True,
) -> TeamDispatchRequest:
    """Enqueue a new dispatch request, deduplicating against pending ones."""
    if not _is_dispatch_kind(kind):
        raise ValueError(f"Invalid dispatch kind: {kind}")
    if kind == "mailbox" and (not message_id or not message_id.strip()):
        raise ValueError("Mailbox dispatch requests require message_id")
    validate_worker_name(to_worker)

    raw_requests = _read_requests(team_name, cwd)

    # Check for dedup
    for raw in raw_requests:
        req = normalize_dispatch_request(team_name, raw)
        if req and _equivalent_pending(req, kind, to_worker, message_id,
                                       inbox_correlation_key, trigger_message):
            return req

    now_iso = datetime.utcnow().isoformat() + "Z"
    new_raw: Dict[str, Any] = {
        "request_id": str(uuid.uuid4()),
        "kind": kind,
        "team_name": team_name,
        "to_worker": to_worker,
        "trigger_message": trigger_message,
        "status": "pending",
        "attempt_count": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
        "transport_preference": transport_preference,
        "fallback_allowed": fallback_allowed,
    }
    if worker_index is not None:
        new_raw["worker_index"] = worker_index
    if pane_id:
        new_raw["pane_id"] = pane_id
    if message_id:
        new_raw["message_id"] = message_id
    if inbox_correlation_key:
        new_raw["inbox_correlation_key"] = inbox_correlation_key

    request = normalize_dispatch_request(team_name, new_raw, now_iso)
    if request is None:
        raise RuntimeError("Failed to normalize dispatch request")

    raw_requests.append(new_raw)
    _write_requests(team_name, raw_requests, cwd)
    return request


def list_dispatch_requests(
    team_name: str,
    cwd: str,
    *,
    status: Optional[DispatchRequestStatus] = None,
    kind: Optional[DispatchRequestKind] = None,
    to_worker: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[TeamDispatchRequest]:
    """List dispatch requests with optional filtering."""
    raw_requests = _read_requests(team_name, cwd)
    results: List[TeamDispatchRequest] = []

    for raw in raw_requests:
        req = normalize_dispatch_request(team_name, raw)
        if req is None:
            continue
        if status and req.status != status:
            continue
        if kind and req.kind != kind:
            continue
        if to_worker and req.to_worker != to_worker:
            continue
        results.append(req)
        if limit and len(results) >= limit:
            break

    return results


def read_dispatch_request(
    team_name: str,
    request_id: str,
    cwd: str,
) -> Optional[TeamDispatchRequest]:
    """Read a single dispatch request by ID."""
    raw_requests = _read_requests(team_name, cwd)
    for raw in raw_requests:
        if raw.get("request_id") == request_id:
            return normalize_dispatch_request(team_name, raw)
    return None


def transition_dispatch_request(
    team_name: str,
    request_id: str,
    from_status: DispatchRequestStatus,
    to_status: DispatchRequestStatus,
    cwd: str,
    patch: Optional[Dict[str, Any]] = None,
) -> Optional[TeamDispatchRequest]:
    """Transition a dispatch request status with optimistic concurrency."""
    if not _can_transition(from_status, to_status):
        return None

    raw_requests = _read_requests(team_name, cwd)
    now_iso = datetime.utcnow().isoformat() + "Z"

    for i, raw in enumerate(raw_requests):
        if raw.get("request_id") != request_id:
            continue

        current_status = raw.get("status", "pending")
        if current_status != from_status and current_status != to_status:
            return None
        if not _can_transition(current_status, to_status):
            return None

        raw["status"] = to_status
        raw["updated_at"] = now_iso
        if current_status != to_status:
            raw["attempt_count"] = raw.get("attempt_count", 0) + 1

        if to_status == "notified":
            raw["notified_at"] = now_iso
        elif to_status == "delivered":
            raw["delivered_at"] = now_iso
        elif to_status == "failed":
            raw["failed_at"] = now_iso

        if patch:
            for k, v in patch.items():
                if k not in ("request_id", "kind", "team_name", "to_worker"):
                    raw[k] = v

        raw_requests[i] = raw
        _write_requests(team_name, raw_requests, cwd)
        return normalize_dispatch_request(team_name, raw)

    return None


def mark_dispatch_request_notified(
    team_name: str,
    request_id: str,
    cwd: str,
    patch: Optional[Dict[str, Any]] = None,
) -> Optional[TeamDispatchRequest]:
    """Mark a dispatch request as notified."""
    current = read_dispatch_request(team_name, request_id, cwd)
    if not current:
        return None
    if current.status in ("notified", "delivered"):
        return current
    return transition_dispatch_request(
        team_name, request_id, current.status, "notified", cwd, patch
    )


def mark_dispatch_request_delivered(
    team_name: str,
    request_id: str,
    cwd: str,
    patch: Optional[Dict[str, Any]] = None,
) -> Optional[TeamDispatchRequest]:
    """Mark a dispatch request as delivered."""
    current = read_dispatch_request(team_name, request_id, cwd)
    if not current:
        return None
    if current.status == "delivered":
        return current
    return transition_dispatch_request(
        team_name, request_id, current.status, "delivered", cwd, patch
    )


def mark_dispatch_request_failed(
    team_name: str,
    request_id: str,
    reason: str,
    cwd: str,
) -> None:
    """Mark a dispatch request as failed."""
    transition_dispatch_request(
        team_name, request_id, "pending", "failed", cwd, {"last_reason": reason}
    )
