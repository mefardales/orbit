"""
Session Lifecycle Manager.

Tracks session start/end, detects stale sessions from crashed launches,
and provides structured logging for session events.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional


@dataclass
class SessionState:
    """Persisted session state."""

    session_id: str
    started_at: str
    cwd: str
    pid: int
    platform: Optional[str] = None
    pid_start_ticks: Optional[int] = None
    pid_cmdline: Optional[str] = None


def _omx_state_dir(cwd: str) -> Path:
    return Path(cwd) / ".omx" / "state"


def _omx_logs_dir(cwd: str) -> Path:
    return Path(cwd) / ".omx" / "logs"


def _session_path(cwd: str) -> Path:
    return _omx_state_dir(cwd) / "session.json"


def _history_path(cwd: str) -> Path:
    return _omx_logs_dir(cwd) / "session-history.jsonl"


async def reset_session_metrics(cwd: str) -> None:
    """
    Reset session-scoped HUD/metrics files at launch so stale values
    do not leak into a new session.
    """
    omx_dir = Path(cwd) / ".omx"
    state_dir = _omx_state_dir(cwd)
    omx_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()

    metrics = {
        "total_turns": 0,
        "session_turns": 0,
        "last_activity": now,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "session_total_tokens": 0,
        "five_hour_limit_pct": 0,
        "weekly_limit_pct": 0,
    }
    (omx_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    hud = {
        "last_turn_at": now,
        "turn_count": 0,
        "last_agent_output": "",
    }
    (state_dir / "hud-state.json").write_text(json.dumps(hud, indent=2))


async def read_session_state(cwd: str) -> Optional[SessionState]:
    """Read current session state. Returns None if no session file exists."""
    path = _session_path(cwd)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        return SessionState(
            session_id=data["session_id"],
            started_at=data["started_at"],
            cwd=data["cwd"],
            pid=data["pid"],
            platform=data.get("platform"),
            pid_start_ticks=data.get("pid_start_ticks"),
            pid_cmdline=data.get("pid_cmdline"),
        )
    except (json.JSONDecodeError, KeyError):
        return None


def _default_is_pid_alive(pid: int) -> bool:
    """Check if a PID is alive using os.kill(pid, 0)."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


@dataclass
class LinuxProcessIdentity:
    start_ticks: int
    cmdline: Optional[str] = None


def _parse_linux_proc_start_ticks(stat_content: str) -> Optional[int]:
    command_end = stat_content.rfind(")")
    if command_end == -1:
        return None
    remainder = stat_content[command_end + 1:].strip()
    fields = remainder.split()
    if len(fields) <= 19:
        return None
    try:
        start_ticks = int(fields[19])
        return start_ticks
    except (ValueError, IndexError):
        return None


def _normalize_cmdline(cmdline: Optional[str]) -> Optional[str]:
    if not cmdline:
        return None
    normalized = " ".join(cmdline.split()).strip()
    return normalized if normalized else None


def _read_linux_process_identity(pid: int) -> Optional[LinuxProcessIdentity]:
    try:
        stat_content = Path(f"/proc/{pid}/stat").read_text()
        start_ticks = _parse_linux_proc_start_ticks(stat_content)
        if start_ticks is None:
            return None

        cmdline: Optional[str] = None
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_text()
            cmdline = raw.replace("\x00", " ").strip()
        except OSError:
            pass

        return LinuxProcessIdentity(
            start_ticks=start_ticks,
            cmdline=_normalize_cmdline(cmdline),
        )
    except OSError:
        return None


def is_session_stale(
    state: SessionState,
    plat: Optional[str] = None,
    is_pid_alive: Optional[Callable[[int], bool]] = None,
    read_linux_identity: Optional[Callable[[int], Optional[LinuxProcessIdentity]]] = None,
) -> bool:
    """
    Check if a session is stale.
    - If the owning PID is dead, it is stale.
    - On Linux, require process identity validation (start ticks, optional cmdline).
    """
    if not isinstance(state.pid, int) or state.pid <= 0:
        return True

    check_alive = is_pid_alive or _default_is_pid_alive
    if not check_alive(state.pid):
        return True

    current_platform = plat or sys.platform
    if current_platform != "linux":
        return False

    read_identity = read_linux_identity or _read_linux_process_identity
    live_identity = read_identity(state.pid)
    if not live_identity:
        return True

    if not isinstance(state.pid_start_ticks, int):
        return True
    if state.pid_start_ticks != live_identity.start_ticks:
        return True

    expected_cmdline = _normalize_cmdline(state.pid_cmdline)
    if expected_cmdline:
        live_cmdline = _normalize_cmdline(live_identity.cmdline)
        if not live_cmdline or live_cmdline != expected_cmdline:
            return True

    return False


async def write_session_start(cwd: str, session_id: str) -> None:
    """Write session start state."""
    state_dir = _omx_state_dir(cwd)
    state_dir.mkdir(parents=True, exist_ok=True)

    linux_identity = (
        _read_linux_process_identity(os.getpid())
        if sys.platform == "linux"
        else None
    )

    now = datetime.now(timezone.utc).isoformat()
    state = {
        "session_id": session_id,
        "started_at": now,
        "cwd": cwd,
        "pid": os.getpid(),
        "platform": sys.platform,
    }
    if linux_identity:
        state["pid_start_ticks"] = linux_identity.start_ticks
        if linux_identity.cmdline:
            state["pid_cmdline"] = linux_identity.cmdline

    _session_path(cwd).write_text(json.dumps(state, indent=2))

    await append_to_log(cwd, {
        "event": "session_start",
        "session_id": session_id,
        "pid": os.getpid(),
        "timestamp": now,
    })


async def write_session_end(cwd: str, session_id: str) -> None:
    """Write session end: archive to history, delete session.json."""
    state = await read_session_state(cwd)
    end_time = datetime.now(timezone.utc).isoformat()

    logs_dir = _omx_logs_dir(cwd)
    logs_dir.mkdir(parents=True, exist_ok=True)

    history_entry = {
        "session_id": session_id,
        "started_at": state.started_at if state else "unknown",
        "ended_at": end_time,
        "cwd": cwd,
        "pid": state.pid if state else os.getpid(),
    }

    with open(_history_path(cwd), "a") as f:
        f.write(json.dumps(history_entry) + "\n")

    try:
        _session_path(cwd).unlink()
    except FileNotFoundError:
        pass

    await append_to_log(cwd, {
        "event": "session_end",
        "session_id": session_id,
        "timestamp": end_time,
    })


async def append_to_log(cwd: str, entry: Dict[str, Any]) -> None:
    """Append a structured JSONL entry to the daily log file."""
    logs_dir = _omx_logs_dir(cwd)
    logs_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).isoformat()[:10]
    log_file = logs_dir / f"omx-{date_str}.jsonl"
    line = json.dumps({**entry, "_ts": datetime.now(timezone.utc).isoformat()}) + "\n"

    with open(log_file, "a") as f:
        f.write(line)
