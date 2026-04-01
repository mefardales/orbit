"""
Ultrawork mode: extended focused work sessions with higher token limits.

Configures the session for deep, sustained work by raising token budgets
and extending iteration windows. Exclusive — cannot run with other exclusive modes.
State is persisted to .orbit/state/ultrawork-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager

logger = logging.getLogger("orbit.modes.ultrawork")

_STATE_FILE = Path(".orbit") / "state" / "ultrawork-state.json"
_MODE_NAME = "ultrawork"

# Default elevated limits for ultrawork sessions
_DEFAULT_MAX_TOKENS = 200_000
_DEFAULT_MAX_TURNS = 100
_DEFAULT_EXTENDED_TIMEOUT = 600  # seconds per turn


@dataclass
class UltraworkConfig:
    """Configuration for an ultrawork session."""

    task: str
    max_tokens: int = _DEFAULT_MAX_TOKENS
    max_turns: int = _DEFAULT_MAX_TURNS
    turn_timeout: int = _DEFAULT_EXTENDED_TIMEOUT
    focus_tags: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class UltraworkMode:
    """Extended focused work session with elevated resource limits."""

    is_exclusive: bool = True

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._config: Optional[UltraworkConfig] = None
        self._turn_count: int = 0
        self._token_count: int = 0

    def activate(self, config: UltraworkConfig) -> ModeStatus:
        """Start ultrawork mode."""
        self._config = config
        self._turn_count = 0
        self._token_count = 0

        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "task": config.task,
                "max_tokens": config.max_tokens,
                "max_turns": config.max_turns,
                "turn_timeout": config.turn_timeout,
                "focus_tags": config.focus_tags,
                "phase": "focused",
                "iteration": 0,
            },
        )
        self._flush_state()
        logger.info(
            "Ultrawork activated: task=%r max_tokens=%d max_turns=%d",
            config.task,
            config.max_tokens,
            config.max_turns,
        )
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """End ultrawork mode and persist final stats."""
        self._flush_state(final=True)
        status = self._manager.deactivate_mode(_MODE_NAME)
        logger.info(
            "Ultrawork deactivated: turns=%d tokens_used=%d",
            self._turn_count,
            self._token_count,
        )
        return status

    def get_status(self) -> Optional[ModeStatus]:
        return self._manager.get_mode_status(_MODE_NAME)

    # ── Turn tracking ─────────────────────────────────────────────────────

    def record_turn(self, tokens_used: int = 0) -> bool:
        """Record one completed turn and update resource counters.

        Returns:
            True if more turns remain within budget, False if limits reached.
        """
        if self._config is None:
            raise RuntimeError("UltraworkMode has not been activated")

        self._turn_count += 1
        self._token_count += tokens_used

        self._manager.advance_phase(_MODE_NAME, "focused", iteration=self._turn_count)
        self._flush_state()

        exhausted = (
            self._turn_count >= self._config.max_turns
            or self._token_count >= self._config.max_tokens
        )
        if exhausted:
            logger.info("Ultrawork resource limits reached (turns=%d, tokens=%d)", self._turn_count, self._token_count)
        return not exhausted

    @property
    def remaining_tokens(self) -> int:
        if self._config is None:
            return 0
        return max(0, self._config.max_tokens - self._token_count)

    @property
    def remaining_turns(self) -> int:
        if self._config is None:
            return 0
        return max(0, self._config.max_turns - self._turn_count)

    # ── State persistence ──────────────────────────────────────────────────

    def _flush_state(self, *, final: bool = False) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "mode": _MODE_NAME,
            "phase": "complete" if final else "focused",
            "turn_count": self._turn_count,
            "token_count": self._token_count,
            "timestamp": time.time(),
        }
        if self._config:
            payload.update(
                {
                    "task": self._config.task,
                    "max_tokens": self._config.max_tokens,
                    "max_turns": self._config.max_turns,
                    "remaining_tokens": self.remaining_tokens,
                    "remaining_turns": self.remaining_turns,
                }
            )
        _STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
