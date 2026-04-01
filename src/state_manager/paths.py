"""State path resolution for orbit.

Provides functions for resolving state directories and file paths,
with session-scoped and base-scoped variants.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
STATE_MODE_SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def validate_session_id(session_id: str) -> bool:
    """Return True if session_id matches the allowed pattern."""
    return bool(SESSION_ID_PATTERN.match(session_id))


def validate_state_mode_segment(mode: str) -> bool:
    """Return True if mode matches the allowed state-mode segment pattern."""
    return bool(STATE_MODE_SEGMENT_PATTERN.match(mode))


def get_base_state_dir(project_root: Optional[str] = None) -> str:
    """Return the base .orbit/state directory for the given project root."""
    root = project_root or os.getcwd()
    return str(Path(root) / ".orbit" / "state")


def get_state_dir(project_root: Optional[str] = None, session_id: Optional[str] = None) -> str:
    """Return the state directory, optionally scoped by session id."""
    base = get_base_state_dir(project_root)
    if session_id:
        return str(Path(base) / session_id)
    return base


def get_state_path(
    mode: str,
    project_root: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Return the full path to a mode's state JSON file."""
    directory = get_state_dir(project_root, session_id)
    return str(Path(directory) / f"{mode}-state.json")


@dataclass
class ResolvedStateScope:
    state_dir: str
    session_id: Optional[str]
    source: str  # e.g. "env", "file", "default"


def _read_current_session_id(project_root: Optional[str] = None) -> Optional[str]:
    """Try to read the current session id from env or a marker file."""
    env_val = os.environ.get("ORBIT_SESSION_ID", "").strip()
    if env_val and validate_session_id(env_val):
        return env_val

    root = project_root or os.getcwd()
    marker = Path(root) / ".orbit" / "state" / "current-session.json"
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            sid = data.get("session_id", "")
            if isinstance(sid, str) and validate_session_id(sid):
                return sid
        except Exception:
            pass
    return None


def resolve_state_scope(project_root: Optional[str] = None) -> ResolvedStateScope:
    """Resolve the current state scope (session-scoped or base)."""
    session_id = _read_current_session_id(project_root)
    if session_id:
        return ResolvedStateScope(
            state_dir=get_state_dir(project_root, session_id),
            session_id=session_id,
            source="env" if os.environ.get("ORBIT_SESSION_ID") else "file",
        )
    return ResolvedStateScope(
        state_dir=get_base_state_dir(project_root),
        session_id=None,
        source="default",
    )


def get_read_scoped_state_dirs(project_root: Optional[str] = None) -> list[str]:
    """Return list of state directories to search (session-scoped first, then base)."""
    scope = resolve_state_scope(project_root)
    base = get_base_state_dir(project_root)
    dirs = [scope.state_dir]
    if scope.state_dir != base:
        dirs.append(base)
    return dirs


def get_read_scoped_state_paths(mode: str, project_root: Optional[str] = None) -> list[str]:
    """Return list of possible state file paths for a mode (session-scoped first, then base)."""
    dirs = get_read_scoped_state_dirs(project_root)
    return [str(Path(d) / f"{mode}-state.json") for d in dirs]
