"""Worker state tracking: status, heartbeat, identity, inbox management.

Provides file-based persistence for per-worker state within a team.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .types import (
    WorkerHeartbeat,
    WorkerInfo,
    WorkerStatus,
)


# ── Path helpers ──────────────────────────────────────────────────────────────


def _worker_dir(team_name: str, worker_name: str, cwd: str) -> Path:
    return Path(cwd) / ".omx" / "state" / "team" / team_name / "workers" / worker_name


def _status_path(team_name: str, worker_name: str, cwd: str) -> Path:
    return _worker_dir(team_name, worker_name, cwd) / "status.json"


def _heartbeat_path(team_name: str, worker_name: str, cwd: str) -> Path:
    return _worker_dir(team_name, worker_name, cwd) / "heartbeat.json"


def _identity_path(team_name: str, worker_name: str, cwd: str) -> Path:
    return _worker_dir(team_name, worker_name, cwd) / "identity.json"


def _inbox_path(team_name: str, worker_name: str, cwd: str) -> Path:
    return _worker_dir(team_name, worker_name, cwd) / "inbox.md"


# ── Worker status ─────────────────────────────────────────────────────────────


def read_worker_status(
    team_name: str,
    worker_name: str,
    cwd: str,
) -> WorkerStatus:
    """Read a worker's current status. Returns unknown state if file missing."""
    path = _status_path(team_name, worker_name, cwd)
    if not path.exists():
        return WorkerStatus(state="unknown")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkerStatus(
            state=data.get("state", "unknown"),
            current_task_id=data.get("current_task_id"),
            reason=data.get("reason"),
            updated_at=data.get("updated_at", ""),
        )
    except (json.JSONDecodeError, OSError):
        return WorkerStatus(state="unknown")


def write_worker_status(
    team_name: str,
    worker_name: str,
    status: WorkerStatus,
    cwd: str,
) -> None:
    """Write a worker's status to disk."""
    path = _status_path(team_name, worker_name, cwd)
    path.parent.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any] = {
        "state": status.state,
        "updated_at": status.updated_at or datetime.utcnow().isoformat() + "Z",
    }
    if status.current_task_id:
        data["current_task_id"] = status.current_task_id
    if status.reason:
        data["reason"] = status.reason

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Worker heartbeat ──────────────────────────────────────────────────────────


def read_worker_heartbeat(
    team_name: str,
    worker_name: str,
    cwd: str,
) -> Optional[WorkerHeartbeat]:
    """Read a worker's heartbeat data. Returns None if not found."""
    path = _heartbeat_path(team_name, worker_name, cwd)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkerHeartbeat(
            pid=data.get("pid", 0),
            last_turn_at=data.get("last_turn_at", ""),
            turn_count=data.get("turn_count", 0),
            alive=data.get("alive", False),
        )
    except (json.JSONDecodeError, OSError):
        return None


def update_worker_heartbeat(
    team_name: str,
    worker_name: str,
    cwd: str,
    pid: int,
    turn_count: int,
    alive: bool = True,
) -> WorkerHeartbeat:
    """Update a worker's heartbeat with the current timestamp."""
    now_iso = datetime.utcnow().isoformat() + "Z"
    heartbeat = WorkerHeartbeat(
        pid=pid,
        last_turn_at=now_iso,
        turn_count=turn_count,
        alive=alive,
    )

    path = _heartbeat_path(team_name, worker_name, cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": heartbeat.pid,
                "last_turn_at": heartbeat.last_turn_at,
                "turn_count": heartbeat.turn_count,
                "alive": heartbeat.alive,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return heartbeat


# ── Worker identity ───────────────────────────────────────────────────────────


def write_worker_identity(
    team_name: str,
    worker_name: str,
    info: WorkerInfo,
    cwd: str,
) -> None:
    """Persist a worker's identity metadata to disk."""
    path = _identity_path(team_name, worker_name, cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info.to_dict(), indent=2), encoding="utf-8")


def read_worker_identity(
    team_name: str,
    worker_name: str,
    cwd: str,
) -> Optional[WorkerInfo]:
    """Read a worker's persisted identity. Returns None if not found."""
    path = _identity_path(team_name, worker_name, cwd)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkerInfo.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


# ── Worker inbox ──────────────────────────────────────────────────────────────


def write_worker_inbox(
    team_name: str,
    worker_name: str,
    content: str,
    cwd: str,
) -> str:
    """Write content to a worker's inbox file. Returns the inbox path."""
    path = _inbox_path(team_name, worker_name, cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def read_worker_inbox(
    team_name: str,
    worker_name: str,
    cwd: str,
) -> Optional[str]:
    """Read a worker's inbox content. Returns None if not found."""
    path = _inbox_path(team_name, worker_name, cwd)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
