"""
ModeManager: orchestrates activation and deactivation of execution modes.

Enforces mutual exclusivity, tracks active modes with phase information,
and persists state to .orbit/state/{mode}-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    ModeState,
    cancel_mode,
    is_mode_active,
    list_active_modes,
    read_mode_state,
    start_mode,
    update_mode_state,
)

logger = logging.getLogger("orbit.modes.manager")

_HISTORY_FILE = Path(".orbit") / "state" / "mode-history.json"


# ── ModeStatus ────────────────────────────────────────────────────────────────


@dataclass
class ModeStatus:
    """Public status snapshot for a mode."""

    name: str
    active: bool
    phase: Optional[str] = None
    started_at: Optional[float] = None
    iteration: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Exclusive modes ───────────────────────────────────────────────────────────

# Modes that cannot run alongside other exclusive modes.
_EXCLUSIVE_MODES = frozenset(
    {
        "autopilot",
        "ralph",
        "team",
        "autoresearch",
        "ultrawork",
    }
)


def _is_exclusive(name: str) -> bool:
    return name in _EXCLUSIVE_MODES


# ── History log ───────────────────────────────────────────────────────────────


def _append_history(entry: Dict[str, Any]) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history: List[Dict[str, Any]] = []
    if _HISTORY_FILE.exists():
        try:
            history = json.loads(_HISTORY_FILE.read_text("utf-8"))
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError):
            history = []
    history.append(entry)
    _HISTORY_FILE.write_text(json.dumps(history[-500:], indent=2), encoding="utf-8")


# ── ModeManager ───────────────────────────────────────────────────────────────


class ModeManager:
    """Activates, deactivates, and queries execution modes.

    Each mode's state is persisted to ~/.orbit/modes/{name}.json (via the
    existing base-layer helpers) and also to .orbit/state/{name}-state.json
    for the MCP state server.
    """

    def __init__(self, modes_dir: Optional[Path] = None) -> None:
        self._modes_dir = modes_dir

    # ── Activation ────────────────────────────────────────────────────────────

    def activate_mode(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> ModeStatus:
        """Activate a named execution mode.

        Enforces the exclusive-mode constraint: if *name* is exclusive and
        another exclusive mode is already active, raises RuntimeError.

        Args:
            name:   The mode identifier.
            config: Optional configuration dict merged into mode metadata.

        Returns:
            A ModeStatus snapshot of the newly activated mode.

        Raises:
            RuntimeError: if exclusivity would be violated.
        """
        config = config or {}

        if _is_exclusive(name):
            for active_state in list_active_modes(self._modes_dir):
                if active_state.name != name and _is_exclusive(active_state.name):
                    raise RuntimeError(
                        f"Cannot activate exclusive mode {name!r}: "
                        f"exclusive mode {active_state.name!r} is already active. "
                        f"Deactivate it first."
                    )

        metadata = {
            "phase": config.get("phase", "starting"),
            "iteration": config.get("iteration", 0),
            "config": config,
        }
        state = start_mode(name, metadata=metadata, base=self._modes_dir)

        _append_history(
            {
                "action": "activated",
                "mode": name,
                "timestamp": time.time(),
                "config": config,
            }
        )

        logger.info("Activated mode %r (exclusive=%s)", name, _is_exclusive(name))
        return self._state_to_status(state)

    # ── Deactivation ──────────────────────────────────────────────────────────

    def deactivate_mode(self, name: str) -> Optional[ModeStatus]:
        """Deactivate a named mode.

        If the mode is not currently active, logs a debug message and returns
        None. Otherwise cancels the mode and returns its final ModeStatus.
        """
        state = cancel_mode(name, base=self._modes_dir)
        if state is None:
            logger.debug("deactivate_mode(%r): mode not found", name)
            return None

        _append_history(
            {
                "action": "deactivated",
                "mode": name,
                "timestamp": time.time(),
            }
        )
        logger.info("Deactivated mode %r", name)
        return self._state_to_status(state)

    # ── Phase tracking ────────────────────────────────────────────────────────

    def advance_phase(self, name: str, phase: str, **extra: Any) -> Optional[ModeStatus]:
        """Update the current phase of an active mode.

        Args:
            name:  The mode name.
            phase: The new phase string.
            extra: Additional metadata fields to merge.

        Returns:
            Updated ModeStatus or None if the mode doesn't exist.
        """
        updates: Dict[str, Any] = {"phase": phase, **extra}
        state = update_mode_state(name, metadata_updates=updates, base=self._modes_dir)
        if state is None:
            return None
        _append_history(
            {
                "action": "phase_change",
                "mode": name,
                "phase": phase,
                "timestamp": time.time(),
            }
        )
        return self._state_to_status(state)

    def increment_iteration(self, name: str) -> Optional[ModeStatus]:
        """Increment the iteration counter for a mode."""
        state = read_mode_state(name, base=self._modes_dir)
        if state is None:
            return None
        current = state.metadata.get("iteration", 0)
        return self.advance_phase(name, state.metadata.get("phase", ""), iteration=current + 1)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_active_modes(self) -> List[str]:
        """Return a sorted list of currently active mode names."""
        return sorted(s.name for s in list_active_modes(self._modes_dir))

    def get_mode_status(self, name: str) -> Optional[ModeStatus]:
        """Return the current status of a mode, or None if not found."""
        state = read_mode_state(name, base=self._modes_dir)
        if state is None:
            return None
        return self._state_to_status(state)

    def is_active(self, name: str) -> bool:
        return is_mode_active(name, base=self._modes_dir)

    def has_exclusive_active(self) -> Optional[str]:
        """Return the name of any currently active exclusive mode, or None."""
        for state in list_active_modes(self._modes_dir):
            if _is_exclusive(state.name):
                return state.name
        return None

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent mode history entries, newest first."""
        if not _HISTORY_FILE.exists():
            return []
        try:
            entries = json.loads(_HISTORY_FILE.read_text("utf-8"))
            if not isinstance(entries, list):
                return []
            return list(reversed(entries[-limit:]))
        except (json.JSONDecodeError, OSError):
            return []

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _state_to_status(state: ModeState) -> ModeStatus:
        return ModeStatus(
            name=state.name,
            active=state.active,
            phase=state.metadata.get("phase"),
            started_at=state.started_at,
            iteration=state.metadata.get("iteration"),
            metadata=dict(state.metadata),
        )


# ── Module-level default manager ─────────────────────────────────────────────

_default_manager = ModeManager()


def get_mode_manager() -> ModeManager:
    """Return the module-level default ModeManager instance."""
    return _default_manager
