"""
Ralph mode: sequential persistence, delegates to RalphRunner.

Wraps the existing Ralph phase/contract system with the ModeManager lifecycle.
State is persisted to .orbit/state/ralph-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager
from ..ralph.contract import (
    RALPH_PHASES,
    RALPH_TERMINAL_PHASES,
    RalphPhase,
    validate_and_normalize_ralph_state,
)

logger = logging.getLogger("orbit.modes.ralph")

_STATE_FILE = Path(".orbit") / "state" / "ralph-state.json"
_MODE_NAME = "ralph"
_DEFAULT_MAX_ITERATIONS = 50


@dataclass
class RalphConfig:
    """Configuration for a ralph run."""

    task: str
    max_iterations: int = _DEFAULT_MAX_ITERATIONS
    metadata: Dict[str, Any] = field(default_factory=dict)


class RalphRunner:
    """Thin sequential runner that advances ralph through its defined phases.

    Phase progression:
        starting → executing → verifying → fixing (if needed) → complete | failed
    """

    def __init__(self, config: RalphConfig) -> None:
        self._config = config
        self._iteration = 0
        self._phase: RalphPhase = "starting"
        self._logs: List[Dict[str, Any]] = []

    @property
    def phase(self) -> RalphPhase:
        return self._phase

    @property
    def iteration(self) -> int:
        return self._iteration

    def advance(self) -> bool:
        """Advance one step. Returns False when in a terminal phase."""
        if self._phase in RALPH_TERMINAL_PHASES:
            return False

        now_iso = datetime.now(timezone.utc).isoformat()
        self._iteration += 1

        if self._phase == "starting":
            self._phase = "executing"
        elif self._phase == "executing":
            self._phase = "verifying"
        elif self._phase == "verifying":
            # Decide: complete or fix
            self._phase = "complete" if self._iteration >= self._config.max_iterations else "executing"
        elif self._phase == "fixing":
            self._phase = "verifying"

        entry = {
            "phase": self._phase,
            "iteration": self._iteration,
            "timestamp": now_iso,
        }
        self._logs.append(entry)
        return self._phase not in RALPH_TERMINAL_PHASES

    def force_complete(self) -> None:
        self._phase = "complete"

    def force_fail(self) -> None:
        self._phase = "failed"

    def get_state_dict(self) -> Dict[str, Any]:
        active = self._phase not in RALPH_TERMINAL_PHASES
        state: Dict[str, Any] = {
            "active": active,
            "current_phase": self._phase,
            "iteration": self._iteration,
            "max_iterations": self._config.max_iterations,
            "task": self._config.task,
        }
        result = validate_and_normalize_ralph_state(state)
        return result.state if result.ok else state


class RalphMode:
    """Execution mode that drives sequential ralph task persistence."""

    is_exclusive: bool = True

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._runner: Optional[RalphRunner] = None

    def activate(self, config: RalphConfig) -> ModeStatus:
        """Activate ralph mode."""
        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "task": config.task,
                "max_iterations": config.max_iterations,
                "phase": "starting",
                "iteration": 0,
            },
        )
        self._runner = RalphRunner(config)
        self._flush_state()
        logger.info("Ralph mode activated: task=%r", config.task)
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """Deactivate ralph mode."""
        if self._runner:
            self._runner.force_complete()
            self._flush_state()
        return self._manager.deactivate_mode(_MODE_NAME)

    def get_status(self) -> Optional[ModeStatus]:
        return self._manager.get_mode_status(_MODE_NAME)

    def step(self) -> bool:
        """Advance the runner one step and persist state.

        Returns:
            True if the runner is still active, False if it reached a terminal phase.
        """
        if self._runner is None:
            raise RuntimeError("RalphMode has not been activated")
        alive = self._runner.advance()
        self._manager.advance_phase(
            _MODE_NAME,
            self._runner.phase,
            iteration=self._runner.iteration,
        )
        self._flush_state()
        return alive

    def run_to_completion(self, config: RalphConfig) -> Dict[str, Any]:
        """Activate and run ralph until a terminal phase is reached.

        Returns the final state dict.
        """
        self.activate(config)
        try:
            while self.step():
                pass
        finally:
            if self._manager.is_active(_MODE_NAME):
                self.deactivate()
        return self._runner.get_state_dict() if self._runner else {}

    def _flush_state(self) -> None:
        if not self._runner:
            return
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps(self._runner.get_state_dict(), indent=2),
            encoding="utf-8",
        )
