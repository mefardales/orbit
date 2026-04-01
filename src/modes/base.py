"""Runtime mode state management for orbit sessions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MODES_DIR = Path.home() / ".orbit" / "modes"


@dataclass
class ModeState:
    """Represents the state of a runtime mode."""

    name: str
    active: bool = False
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.ended_at if self.ended_at else time.time()
        return end - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModeState:
        return cls(
            name=data["name"],
            active=data.get("active", False),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            metadata=data.get("metadata", {}),
            history=data.get("history", []),
        )


def _modes_dir(base: Optional[Path] = None) -> Path:
    d = base or DEFAULT_MODES_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mode_path(name: str, base: Optional[Path] = None) -> Path:
    return _modes_dir(base) / f"{name}.json"


def read_mode_state(name: str, base: Optional[Path] = None) -> Optional[ModeState]:
    """Read the state of a mode from disk."""
    path = _mode_path(name, base)
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return ModeState.from_dict(json.load(f))
    except (json.JSONDecodeError, KeyError):
        return None


def _save_mode_state(state: ModeState, base: Optional[Path] = None) -> None:
    path = _mode_path(state.name, base)
    with open(path, "w") as f:
        json.dump(state.to_dict(), f, indent=2)


def start_mode(
    name: str,
    metadata: Optional[Dict[str, Any]] = None,
    base: Optional[Path] = None,
) -> ModeState:
    """Start a mode, creating or reactivating it."""
    existing = read_mode_state(name, base)
    now = time.time()
    if existing and existing.active:
        return existing
    state = existing or ModeState(name=name)
    state.active = True
    state.started_at = now
    state.ended_at = None
    state.metadata = metadata or state.metadata
    state.history.append({"action": "started", "timestamp": now})
    _save_mode_state(state, base)
    return state


def cancel_mode(name: str, base: Optional[Path] = None) -> Optional[ModeState]:
    """Cancel (deactivate) a running mode."""
    state = read_mode_state(name, base)
    if state is None or not state.active:
        return state
    now = time.time()
    state.active = False
    state.ended_at = now
    state.history.append({"action": "cancelled", "timestamp": now})
    _save_mode_state(state, base)
    return state


def update_mode_state(
    name: str,
    metadata_updates: Optional[Dict[str, Any]] = None,
    base: Optional[Path] = None,
) -> Optional[ModeState]:
    """Update metadata on an existing mode."""
    state = read_mode_state(name, base)
    if state is None:
        return None
    if metadata_updates:
        state.metadata.update(metadata_updates)
    state.history.append({"action": "updated", "timestamp": time.time()})
    _save_mode_state(state, base)
    return state


def list_active_modes(base: Optional[Path] = None) -> List[ModeState]:
    """Return all currently active modes."""
    modes_dir = _modes_dir(base)
    active: List[ModeState] = []
    for path in modes_dir.glob("*.json"):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            state = ModeState.from_dict(data)
            if state.active:
                active.append(state)
        except (json.JSONDecodeError, KeyError):
            continue
    return active


def is_mode_active(name: str, base: Optional[Path] = None) -> bool:
    """Check whether a specific mode is currently active."""
    state = read_mode_state(name, base)
    return state is not None and state.active


def get_mode_history(name: str, base: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Get the full history log for a mode."""
    state = read_mode_state(name, base)
    if state is None:
        return []
    return list(state.history)
