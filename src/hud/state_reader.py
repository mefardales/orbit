"""
HUD State Reader — reads mode state JSON files from .orbit/state/.

Reads ralph-state.json, team-state.json, autopilot-state.json, etc.
Tracks token usage, active modes, and session duration.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Known mode state file names (without -state.json suffix).
# ---------------------------------------------------------------------------

KNOWN_MODES = [
    "ralph",
    "team",
    "autopilot",
    "autoresearch",
    "ralplan",
    "buddy",
    "moreright",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ModeState:
    """State of a single orbit mode."""

    name: str
    active: bool = False
    phase: Optional[str] = None
    started_at: Optional[str] = None   # ISO timestamp
    tokens_used: int = 0
    tokens_limit: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    used: int = 0
    limit: int = 0

    @property
    def fraction(self) -> float:
        if self.limit <= 0:
            return 0.0
        return min(1.0, self.used / self.limit)

    @property
    def display(self) -> str:
        """Return abbreviated token display, e.g. '45k / 200k'."""
        def _abbrev(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.0f}k"
            return str(n)

        if self.limit > 0:
            return f"{_abbrev(self.used)} / {_abbrev(self.limit)}"
        return _abbrev(self.used)


@dataclass
class HudRuntimeState:
    """Aggregated state consumed by the HUD renderer."""

    modes: List[ModeState] = field(default_factory=list)
    tokens: TokenUsage = field(default_factory=TokenUsage)
    session_started_at: Optional[float] = None  # unix timestamp
    cwd: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)  # per-file raw data

    @property
    def active_modes(self) -> List[ModeState]:
        return [m for m in self.modes if m.active]

    @property
    def session_duration_s(self) -> Optional[float]:
        if self.session_started_at is None:
            return None
        return time.time() - self.session_started_at

    @property
    def session_duration_display(self) -> str:
        s = self.session_duration_s
        if s is None:
            return "—"
        minutes, seconds = divmod(int(s), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h{minutes:02d}m"
        if minutes:
            return f"{minutes}m{seconds:02d}s"
        return f"{seconds}s"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_mode_state(name: str, data: Dict[str, Any]) -> ModeState:
    tokens_used = _safe_int(data.get("tokens_used") or data.get("token_count") or 0)
    tokens_limit = _safe_int(data.get("tokens_limit") or data.get("token_limit") or 0)
    return ModeState(
        name=name,
        active=bool(data.get("active")),
        phase=data.get("phase") or data.get("status"),
        started_at=data.get("started_at") or data.get("session_start"),
        tokens_used=tokens_used,
        tokens_limit=tokens_limit,
        extra=data,
    )


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _read_current_session_start(state_dir: Path) -> Optional[float]:
    """Try to read session start timestamp from current-session.json."""
    candidate = state_dir / "current-session.json"
    data = _read_json_file(candidate)
    if not data:
        return None
    raw_ts = data.get("started_at") or data.get("session_start")
    if isinstance(raw_ts, (int, float)):
        return float(raw_ts)
    if isinstance(raw_ts, str):
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            return dt.timestamp()
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Public reader
# ---------------------------------------------------------------------------

def read_all_state(cwd: Optional[str] = None) -> HudRuntimeState:
    """
    Read all mode state files from .orbit/state/ in *cwd*.

    Searches the base state dir and any session-scoped subdirectory.

    Returns:
        HudRuntimeState with aggregated mode, token, and session information.
    """
    import os
    root = Path(cwd) if cwd else Path(os.getcwd())
    state_dir = root / ".orbit" / "state"

    result = HudRuntimeState(cwd=str(root))

    if not state_dir.exists():
        return result

    result.session_started_at = _read_current_session_start(state_dir)

    # Aggregate token usage and modes across all known modes.
    total_used = 0
    total_limit = 0
    raw_data: Dict[str, Any] = {}

    # Also scan session-scoped sub-directories.
    dirs_to_scan: List[Path] = [state_dir]
    try:
        for child in state_dir.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                dirs_to_scan.append(child)
    except OSError:
        pass

    seen_modes: Dict[str, ModeState] = {}

    for scan_dir in dirs_to_scan:
        for mode_name in KNOWN_MODES:
            state_file = scan_dir / f"{mode_name}-state.json"
            data = _read_json_file(state_file)
            if data is None:
                continue
            raw_data[mode_name] = data
            ms = _parse_mode_state(mode_name, data)
            # Prefer active state over stale state.
            existing = seen_modes.get(mode_name)
            if existing is None or (ms.active and not existing.active):
                seen_modes[mode_name] = ms

    for ms in seen_modes.values():
        total_used += ms.tokens_used
        total_limit = max(total_limit, ms.tokens_limit)
        result.modes.append(ms)

    result.tokens = TokenUsage(used=total_used, limit=total_limit)
    result.raw = raw_data
    return result
