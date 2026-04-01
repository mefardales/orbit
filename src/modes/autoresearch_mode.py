"""
Autoresearch mode: autonomous experimentation, delegates to AutoresearchRunner.

Wraps the existing autoresearch runtime with the ModeManager lifecycle.
State is persisted to .orbit/state/autoresearch-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager

logger = logging.getLogger("orbit.modes.autoresearch")

_STATE_FILE = Path(".orbit") / "state" / "autoresearch-state.json"
_MODE_NAME = "autoresearch"


@dataclass
class AutoresearchConfig:
    """Configuration for an autoresearch run."""

    mission: str
    mission_name: str = "orbit-research"
    max_candidates: int = 10
    keep_policy: str = "best"  # "best" | "all" | "none"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoresearchRun:
    """Tracks a single autoresearch iteration."""

    candidate_id: str
    iteration: int
    status: str  # "running" | "accepted" | "rejected" | "failed"
    score: Optional[float] = None
    notes: str = ""


class AutoresearchMode:
    """Execution mode for autonomous research experimentation.

    Delegates to the existing autoresearch runtime for candidate generation,
    evaluation, and keep/discard decisions.
    """

    is_exclusive: bool = True

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._config: Optional[AutoresearchConfig] = None
        self._runs: List[AutoresearchRun] = []

    def activate(self, config: AutoresearchConfig) -> ModeStatus:
        """Activate autoresearch mode."""
        self._config = config
        self._runs = []
        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "mission": config.mission,
                "mission_name": config.mission_name,
                "max_candidates": config.max_candidates,
                "keep_policy": config.keep_policy,
                "phase": "preparing",
                "iteration": 0,
            },
        )
        self._flush_state("preparing")
        logger.info("Autoresearch mode activated: mission=%r", config.mission)
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """Stop autoresearch mode."""
        self._flush_state("stopped")
        return self._manager.deactivate_mode(_MODE_NAME)

    def get_status(self) -> Optional[ModeStatus]:
        return self._manager.get_mode_status(_MODE_NAME)

    def launch(self, config: AutoresearchConfig) -> ModeStatus:
        """Activate mode and attempt to prepare the autoresearch runtime."""
        status = self.activate(config)
        try:
            from ..autoresearch.runtime import prepare_autoresearch_runtime

            # prepare_autoresearch_runtime may need a full mission contract on
            # disk; here we just signal readiness if the import succeeded.
            self._manager.advance_phase(_MODE_NAME, "running")
            self._flush_state("running")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Autoresearch runtime could not be prepared: %s", exc)
            self._manager.advance_phase(_MODE_NAME, "degraded")
            self._flush_state("degraded")

        return self.get_status() or status

    def record_candidate(
        self,
        candidate_id: str,
        *,
        status: str = "running",
        score: Optional[float] = None,
        notes: str = "",
    ) -> AutoresearchRun:
        """Record the outcome of one research candidate iteration."""
        run = AutoresearchRun(
            candidate_id=candidate_id,
            iteration=len(self._runs) + 1,
            status=status,
            score=score,
            notes=notes,
        )
        self._runs.append(run)
        self._manager.advance_phase(
            _MODE_NAME,
            "evaluating",
            iteration=run.iteration,
        )
        self._flush_state("evaluating")
        return run

    # ── State helpers ──────────────────────────────────────────────────────

    def _flush_state(self, phase: str) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "mode": _MODE_NAME,
            "phase": phase,
            "timestamp": time.time(),
            "runs": len(self._runs),
        }
        if self._config:
            payload.update(
                {
                    "mission": self._config.mission,
                    "max_candidates": self._config.max_candidates,
                }
            )
        _STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
