"""
State file path resolution for the MCP state system.

Handles working directory validation, session scoping, and state file
path computation. Supports per-session state isolation with root fallback.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional

from .validation import (
    SESSION_ID_PATTERN,
    get_state_filename,
    is_mode_state_filename,
    validate_session_id,
    validate_state_mode_segment,
)

# ── Types ────────────────────────────────────────────────────────────────────

StateFileScope = Literal["root", "session"]
StateScopeSource = Literal["explicit", "session", "root"]

WORKDIR_ALLOWLIST_ENV = "OMX_MCP_WORKDIR_ROOTS"


@dataclass(frozen=True)
class ModeStateFileRef:
    """Reference to a discovered mode state file on disk."""

    mode: str
    path: str
    scope: StateFileScope


@dataclass(frozen=True)
class ResolvedStateScope:
    """The resolved scope used when reading/writing state."""

    source: StateScopeSource
    state_dir: str
    session_id: Optional[str] = None


# ── Working directory helpers ────────────────────────────────────────────────


def _parse_allowed_working_directory_roots() -> List[str]:
    """Parse the OMX_MCP_WORKDIR_ROOTS env var into a list of resolved paths."""
    raw = os.environ.get(WORKDIR_ALLOWLIST_ENV, "")
    if not raw.strip():
        return []

    roots: list[str] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        if "\0" in part:
            raise ValueError(
                f"{WORKDIR_ALLOWLIST_ENV} contains an invalid root with a NUL byte"
            )
        roots.append(str(Path(part).resolve()))

    return list(dict.fromkeys(roots))  # dedupe preserving order


def _is_within_root(path: str, root: str) -> bool:
    """Check whether *path* is equal to or a descendant of *root*."""
    try:
        Path(path).relative_to(root)
        return True
    except ValueError:
        return False


def _enforce_working_directory_policy(resolved: str) -> None:
    roots = _parse_allowed_working_directory_roots()
    if not roots:
        return
    if not any(_is_within_root(resolved, r) for r in roots):
        raise ValueError(
            f'workingDirectory "{resolved}" is outside allowed roots ({WORKDIR_ALLOWLIST_ENV})'
        )


def resolve_working_directory_for_state(working_directory: Optional[str] = None) -> str:
    """Resolve and validate the effective working directory.

    When *working_directory* is ``None`` or empty, ``os.getcwd()`` is used.
    Raises ``ValueError`` on policy violations.
    """
    raw = (working_directory or "").strip()

    if "\0" in raw:
        raise ValueError("workingDirectory contains a NUL byte")

    if not raw:
        cwd = str(Path.cwd().resolve())
        _enforce_working_directory_policy(cwd)
        return cwd

    resolved = str(Path(raw).resolve())

    if "\0" in resolved:
        raise ValueError("workingDirectory contains a NUL byte")

    _enforce_working_directory_policy(resolved)
    return resolved


# ── State directory / path helpers ───────────────────────────────────────────


def get_base_state_dir(working_directory: Optional[str] = None) -> str:
    """Return the root state directory, honoring OMX_TEAM_STATE_ROOT."""
    team_root = os.environ.get("OMX_TEAM_STATE_ROOT", "").strip()
    if (working_directory is None or working_directory == "") and team_root:
        try:
            return resolve_working_directory_for_state(team_root)
        except Exception:
            pass

    wd = resolve_working_directory_for_state(working_directory)
    return str(Path(wd) / ".omx" / "state")


def get_state_dir(working_directory: Optional[str] = None, session_id: Optional[str] = None) -> str:
    base = get_base_state_dir(working_directory)
    if session_id:
        return str(Path(base) / "sessions" / session_id)
    return base


def get_state_path(mode: str, working_directory: Optional[str] = None, session_id: Optional[str] = None) -> str:
    return str(Path(get_state_dir(working_directory, session_id)) / get_state_filename(mode))


# ── Session ID resolution ────────────────────────────────────────────────────


def read_current_session_id(working_directory: Optional[str] = None) -> Optional[str]:
    """Read the current session ID from session.json, if it exists."""
    import json

    session_path = Path(get_base_state_dir(working_directory)) / "session.json"
    if not session_path.exists():
        return None
    try:
        data = json.loads(session_path.read_text("utf-8"))
        return validate_session_id(data.get("session_id"))
    except Exception:
        return None


def resolve_state_scope(
    working_directory: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
) -> ResolvedStateScope:
    """Determine which state scope (root or session) to use."""
    validated = validate_session_id(explicit_session_id)
    if validated:
        return ResolvedStateScope(
            source="explicit",
            session_id=validated,
            state_dir=get_state_dir(working_directory, validated),
        )

    current = read_current_session_id(working_directory)
    if current:
        return ResolvedStateScope(
            source="session",
            session_id=current,
            state_dir=get_state_dir(working_directory, current),
        )

    return ResolvedStateScope(
        source="root",
        state_dir=get_state_dir(working_directory),
    )


# ── Scoped path lists ───────────────────────────────────────────────────────


def get_read_scoped_state_dirs(
    working_directory: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
) -> List[str]:
    """Return state dirs in read-precedence order (session first, root fallback)."""
    scope = resolve_state_scope(working_directory, explicit_session_id)
    base = get_base_state_dir(working_directory)

    if scope.source == "root":
        return [scope.state_dir]
    if scope.source == "explicit":
        if Path(scope.state_dir).exists():
            return [scope.state_dir]
        return [scope.state_dir, base]
    # implicit session
    return [scope.state_dir, base]


def get_read_scoped_state_paths(
    mode: str,
    working_directory: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
) -> List[str]:
    dirs = get_read_scoped_state_dirs(working_directory, explicit_session_id)
    filename = get_state_filename(mode)
    return [str(Path(d) / filename) for d in dirs]


def get_all_session_scoped_state_dirs(working_directory: Optional[str] = None) -> List[str]:
    sessions_root = Path(get_base_state_dir(working_directory)) / "sessions"
    if not sessions_root.exists():
        return []
    return [
        str(sessions_root / entry.name)
        for entry in sorted(sessions_root.iterdir())
        if entry.is_dir() and SESSION_ID_PATTERN.match(entry.name)
    ]


def get_all_session_scoped_state_paths(mode: str, working_directory: Optional[str] = None) -> List[str]:
    dirs = get_all_session_scoped_state_dirs(working_directory)
    filename = get_state_filename(mode)
    return [str(Path(d) / filename) for d in dirs]


def get_all_scoped_state_paths(mode: str, working_directory: Optional[str] = None) -> List[str]:
    return [
        get_state_path(mode, working_directory),
        *get_all_session_scoped_state_paths(mode, working_directory),
    ]


def get_all_scoped_state_dirs(working_directory: Optional[str] = None) -> List[str]:
    return [
        get_base_state_dir(working_directory),
        *get_all_session_scoped_state_dirs(working_directory),
    ]


# ── Mode state file listing ─────────────────────────────────────────────────


def _list_mode_state_files_in_dir(directory: str, scope: StateFileScope) -> List[ModeStateFileRef]:
    d = Path(directory)
    if not d.exists():
        return []
    try:
        files = [f.name for f in d.iterdir() if f.is_file()]
    except OSError:
        return []
    suffix = "-state.json"
    return [
        ModeStateFileRef(
            mode=f[: -len(suffix)],
            path=str(d / f),
            scope=scope,
        )
        for f in sorted(files)
        if is_mode_state_filename(f)
    ]


def list_mode_state_files_with_scope_preference(
    working_directory: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
) -> List[ModeStateFileRef]:
    """List mode state files, with session-scoped files taking precedence over root."""
    read_dirs = get_read_scoped_state_dirs(working_directory, explicit_session_id)
    root_dir = get_base_state_dir(working_directory)
    preferred: dict[str, ModeStateFileRef] = {}

    # Process in reverse so higher-precedence dirs override
    for d in reversed(read_dirs):
        scope: StateFileScope = "root" if d == root_dir else "session"
        for ref in _list_mode_state_files_in_dir(d, scope):
            preferred[ref.mode] = ref

    return sorted(preferred.values(), key=lambda r: r.mode)
