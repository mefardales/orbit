"""
Team mode: multi-agent coordination, delegates to TeamRuntime.

Wraps the existing team orchestration system with the ModeManager lifecycle.
State is persisted to .orbit/state/team-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager

logger = logging.getLogger("orbit.modes.team")

_STATE_FILE = Path(".orbit") / "state" / "team-state.json"
_MODE_NAME = "team"


@dataclass
class TeamModeConfig:
    """Configuration for a team mode run."""

    task: str
    team_name: str = "orbit-team"
    worker_count: int = 3
    roles: List[str] = field(default_factory=lambda: ["builder", "reviewer", "coordinator"])
    metadata: Dict[str, Any] = field(default_factory=dict)


class TeamMode:
    """Execution mode that coordinates multiple agents in parallel.

    Delegates the actual worker spawning to TeamRuntime (src/team/runtime.py).
    This class provides the ModeManager lifecycle wrapper.
    """

    is_exclusive: bool = True

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._config: Optional[TeamModeConfig] = None
        self._runtime: Any = None  # TeamRuntime, imported lazily to avoid circular deps

    def activate(self, config: TeamModeConfig) -> ModeStatus:
        """Start team mode and initialize the underlying TeamRuntime."""
        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "task": config.task,
                "team_name": config.team_name,
                "worker_count": config.worker_count,
                "roles": config.roles,
                "phase": "initializing",
                "iteration": 0,
            },
        )
        self._config = config
        self._flush_state("initializing", worker_count=config.worker_count)
        logger.info(
            "Team mode activated: team=%r task=%r workers=%d",
            config.team_name,
            config.task,
            config.worker_count,
        )
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """Tear down team mode."""
        if self._runtime is not None:
            try:
                self._runtime.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("TeamRuntime.stop() raised: %s", exc)
            self._runtime = None
        self._flush_state("stopped")
        return self._manager.deactivate_mode(_MODE_NAME)

    def get_status(self) -> Optional[ModeStatus]:
        return self._manager.get_mode_status(_MODE_NAME)

    def launch(self, config: TeamModeConfig) -> ModeStatus:
        """Activate mode and attempt to start the TeamRuntime.

        Falls back gracefully if the team runtime dependencies (tmux) are
        unavailable in the current environment.
        """
        status = self.activate(config)
        try:
            from ..team.runtime import TeamRuntime, StartTeamOptions

            options = StartTeamOptions(
                team_name=config.team_name,
                task=config.task,
            )
            self._runtime = TeamRuntime(options)
            self._manager.advance_phase(_MODE_NAME, "running")
            self._flush_state("running", worker_count=config.worker_count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("TeamRuntime could not be started: %s", exc)
            self._manager.advance_phase(_MODE_NAME, "degraded")
            self._flush_state("degraded (runtime unavailable)")
        return self.get_status() or status

    # ── State helpers ──────────────────────────────────────────────────────

    def _flush_state(self, phase: str, **extra: Any) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "mode": _MODE_NAME,
            "phase": phase,
            "timestamp": time.time(),
        }
        if self._config:
            payload.update(
                {
                    "task": self._config.task,
                    "team_name": self._config.team_name,
                }
            )
        payload.update(extra)
        _STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
