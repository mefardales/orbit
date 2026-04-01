"""
Autopilot mode: automated task execution with configurable iteration limits.

Runs a task loop autonomously up to max_iterations, writing state to
.orbit/state/autopilot-state.json after each iteration.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager

logger = logging.getLogger("orbit.modes.autopilot")

_STATE_FILE = Path(".orbit") / "state" / "autopilot-state.json"

_MODE_NAME = "autopilot"
_DEFAULT_MAX_ITERATIONS = 20


@dataclass
class AutopilotConfig:
    """Configuration for a single autopilot run."""

    task: str
    max_iterations: int = _DEFAULT_MAX_ITERATIONS
    stop_on_success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AutopilotResult:
    """Outcome of one autopilot iteration."""

    iteration: int
    success: bool
    output: str = ""
    error: Optional[str] = None


class AutopilotMode:
    """Runs tasks automatically for up to max_iterations steps.

    Each iteration calls the provided *step_fn* and records the result.
    The run stops early if stop_on_success is True and a step returns
    success=True.
    """

    is_exclusive: bool = True

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._results: List[AutopilotResult] = []

    def activate(self, config: AutopilotConfig) -> ModeStatus:
        """Start autopilot mode with the provided configuration.

        Args:
            config: Task and iteration settings.

        Returns:
            ModeStatus snapshot after activation.
        """
        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "task": config.task,
                "max_iterations": config.max_iterations,
                "stop_on_success": config.stop_on_success,
                "phase": "starting",
                "iteration": 0,
            },
        )
        self._persist_state(config, status)
        logger.info("Autopilot activated: task=%r max_iterations=%d", config.task, config.max_iterations)
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """Stop autopilot mode."""
        status = self._manager.deactivate_mode(_MODE_NAME)
        self._update_state_field("phase", "cancelled")
        return status

    def get_status(self) -> Optional[ModeStatus]:
        """Return the current mode status."""
        return self._manager.get_mode_status(_MODE_NAME)

    def run(
        self,
        config: AutopilotConfig,
        step_fn: Callable[[int, str], AutopilotResult],
    ) -> List[AutopilotResult]:
        """Execute the autopilot loop.

        Args:
            config:  Task configuration.
            step_fn: Callable(iteration, task) → AutopilotResult. Called once
                     per iteration. Implementations should be idempotent.

        Returns:
            List of results from each iteration.
        """
        self.activate(config)
        self._results = []

        try:
            for i in range(1, config.max_iterations + 1):
                self._manager.advance_phase(_MODE_NAME, "executing", iteration=i)
                self._update_state_field("iteration", i)

                logger.debug("Autopilot iteration %d / %d", i, config.max_iterations)

                try:
                    result = step_fn(i, config.task)
                except Exception as exc:  # noqa: BLE001
                    result = AutopilotResult(iteration=i, success=False, error=str(exc))
                    logger.warning("Autopilot step %d raised: %s", i, exc)

                self._results.append(result)
                self._manager.advance_phase(_MODE_NAME, "verifying", iteration=i)

                if result.success and config.stop_on_success:
                    logger.info("Autopilot completed successfully at iteration %d", i)
                    self._manager.advance_phase(_MODE_NAME, "complete", iteration=i)
                    break
        finally:
            # Ensure we always cleanly deactivate
            if self._manager.is_active(_MODE_NAME):
                self.deactivate()

        return self._results

    # ── State persistence ──────────────────────────────────────────────────

    def _persist_state(self, config: AutopilotConfig, status: ModeStatus) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps(
                {
                    "mode": _MODE_NAME,
                    "task": config.task,
                    "max_iterations": config.max_iterations,
                    "active": True,
                    "phase": "starting",
                    "iteration": 0,
                    "started_at": status.started_at,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _update_state_field(self, key: str, value: Any) -> None:
        if not _STATE_FILE.exists():
            return
        try:
            data = json.loads(_STATE_FILE.read_text("utf-8"))
            data[key] = value
            _STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass
