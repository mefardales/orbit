"""
Memory and state validation utilities.
Provides input validation for notepad pruning, session IDs, and mode segments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_NOTEPAD_PRUNE_DAYS_OLD = 7

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STATE_MODE_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STATE_FILE_SUFFIX = "-state.json"


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PruneDaysOk:
    ok: bool = True
    days: int = DEFAULT_NOTEPAD_PRUNE_DAYS_OLD


@dataclass(frozen=True)
class PruneDaysError:
    ok: bool = False
    error: str = ""


PruneDaysResult = Union[PruneDaysOk, PruneDaysError]


# ── Validation functions ─────────────────────────────────────────────────────


def parse_notepad_prune_days_old(
    value: object,
    default_days: int = DEFAULT_NOTEPAD_PRUNE_DAYS_OLD,
) -> PruneDaysResult:
    """Validate and parse the daysOld parameter for notepad pruning.

    Returns PruneDaysOk on success or PruneDaysError on invalid input.
    """
    if value is None:
        return PruneDaysOk(days=default_days)

    if not isinstance(value, (int, float)):
        return PruneDaysError(error="daysOld must be a non-negative integer")

    if isinstance(value, float) and not value.is_integer():
        return PruneDaysError(error="daysOld must be a non-negative integer")

    int_value = int(value)
    if int_value < 0:
        return PruneDaysError(error="daysOld must be a non-negative integer")

    return PruneDaysOk(days=int_value)


def validate_session_id(session_id: object) -> Optional[str]:
    """Validate and return a session ID string, or None if not provided.

    Raises ValueError if the session_id is present but invalid.
    """
    if session_id is None:
        return None

    if not isinstance(session_id, str):
        raise ValueError("session_id must be a string")

    if not SESSION_ID_PATTERN.match(session_id):
        raise ValueError("session_id must match ^[A-Za-z0-9_-]{1,64}$")

    return session_id


def validate_state_mode_segment(mode: object) -> str:
    """Validate a mode name for use in state file paths.

    Raises ValueError on invalid mode strings.
    """
    if not isinstance(mode, str):
        raise ValueError("mode must be a string")

    normalized = mode.strip()
    if not normalized:
        raise ValueError("mode must be a non-empty string")

    if ".." in normalized:
        raise ValueError('mode must not contain ".."')

    if "/" in normalized or "\\" in normalized:
        raise ValueError("mode must not contain path separators")

    if not STATE_MODE_SEGMENT_PATTERN.match(normalized):
        raise ValueError("mode must match ^[A-Za-z0-9_-]{1,64}$")

    return normalized


def get_state_filename(mode: str) -> str:
    """Return the state file name for a given mode, e.g. 'autopilot-state.json'."""
    return f"{validate_state_mode_segment(mode)}{STATE_FILE_SUFFIX}"


def is_mode_state_filename(filename: str) -> bool:
    """Check if a filename looks like a mode state file."""
    return filename.endswith(STATE_FILE_SUFFIX) and filename != "session.json"
