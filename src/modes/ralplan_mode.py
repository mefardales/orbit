"""
Ralplan mode: consensus-based planning with multiple perspectives.

Wraps the existing RalplanRuntime with the ModeManager lifecycle.
Not exclusive — can run alongside non-exclusive modes.
State is persisted to .orbit/state/ralplan-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager
from ..ralplan.runtime import Plan, PlanStatus, RalplanRuntime

logger = logging.getLogger("orbit.modes.ralplan")

_STATE_FILE = Path(".orbit") / "state" / "ralplan-state.json"
_MODE_NAME = "ralplan"


@dataclass
class RalplanConfig:
    """Configuration for a ralplan session."""

    title: str
    objective: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    reviewers: List[str] = field(default_factory=list)
    consensus_threshold: float = 0.67
    max_review_cycles: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)


class RalplanMode:
    """Consensus-based planning mode.

    Creates a plan via RalplanRuntime, drives it through review cycles, and
    finalises it once consensus is reached or max cycles are exhausted.
    """

    is_exclusive: bool = False

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._runtime: Optional[RalplanRuntime] = None
        self._config: Optional[RalplanConfig] = None
        self._plan: Optional[Plan] = None

    def activate(self, config: RalplanConfig) -> ModeStatus:
        """Start ralplan mode and initialise the RalplanRuntime."""
        self._config = config
        self._runtime = RalplanRuntime(
            consensus_threshold=config.consensus_threshold,
            max_review_cycles=config.max_review_cycles,
            reviewers=config.reviewers,
        )
        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "title": config.title,
                "objective": config.objective,
                "step_count": len(config.steps),
                "reviewers": config.reviewers,
                "consensus_threshold": config.consensus_threshold,
                "phase": "drafting",
                "iteration": 0,
            },
        )
        self._flush_state("drafting")
        logger.info("Ralplan mode activated: title=%r objective=%r", config.title, config.objective)
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """End ralplan mode."""
        self._flush_state("stopped")
        return self._manager.deactivate_mode(_MODE_NAME)

    def get_status(self) -> Optional[ModeStatus]:
        return self._manager.get_mode_status(_MODE_NAME)

    # ── Plan lifecycle ─────────────────────────────────────────────────────

    def create_plan(self) -> Plan:
        """Create a plan from the config's steps and advance to 'reviewing'."""
        if self._runtime is None or self._config is None:
            raise RuntimeError("RalplanMode has not been activated")

        self._plan = self._runtime.plan(
            title=self._config.title,
            objective=self._config.objective,
            steps=self._config.steps,
            metadata=self._config.metadata,
        )
        self._manager.advance_phase(_MODE_NAME, "reviewing")
        self._flush_state("reviewing")
        logger.info("Plan created: plan_id=%r", self._plan.plan_id)
        return self._plan

    def submit_votes(self, votes: List[Dict[str, Any]]) -> Plan:
        """Submit a batch of review votes and advance the plan.

        Each vote dict must have: reviewer (str), approve (bool),
        and optionally comments (str).

        Returns:
            The updated Plan after processing the votes.
        """
        if self._runtime is None or self._plan is None:
            raise RuntimeError("No active plan — call create_plan() first")

        plan = self._runtime.review_cycle(self._plan.plan_id, votes)
        self._plan = plan

        if plan.status == PlanStatus.CONSENSUS:
            self._manager.advance_phase(_MODE_NAME, "consensus", iteration=plan.revision)
            self._flush_state("consensus")
        elif plan.status == PlanStatus.REJECTED:
            self._manager.advance_phase(_MODE_NAME, "rejected", iteration=plan.revision)
            self._flush_state("rejected")
        else:
            self._manager.advance_phase(_MODE_NAME, "reviewing", iteration=plan.revision)
            self._flush_state("reviewing")

        return plan

    def finalize(self, *, force: bool = False) -> Plan:
        """Finalize the plan.

        Args:
            force: If True, finalize even if consensus has not been reached.

        Returns:
            The finalized Plan.
        """
        if self._runtime is None or self._plan is None:
            raise RuntimeError("No active plan")
        plan = self._runtime.finalize(self._plan.plan_id, force=force)
        self._plan = plan
        self._manager.advance_phase(_MODE_NAME, "finalized")
        self._flush_state("finalized")
        return plan

    def run_to_consensus(self, config: RalplanConfig, vote_fn: Any) -> Dict[str, Any]:
        """Activate mode, run full plan lifecycle to consensus or rejection.

        Args:
            config:  Plan configuration.
            vote_fn: Callable(plan) → list[dict] — returns votes for a given
                     plan revision. Called once per review cycle.

        Returns:
            Summary dict from RalplanRuntime.summary().
        """
        self.activate(config)
        try:
            plan = self.create_plan()
            while plan.status not in (PlanStatus.CONSENSUS, PlanStatus.REJECTED, PlanStatus.FINALIZED):
                votes = vote_fn(plan)
                plan = self.submit_votes(votes)

            if plan.status == PlanStatus.CONSENSUS:
                plan = self.finalize()
        finally:
            if self._manager.is_active(_MODE_NAME):
                self.deactivate()

        assert self._runtime is not None
        assert self._plan is not None
        return self._runtime.summary(self._plan.plan_id)

    @property
    def plan(self) -> Optional[Plan]:
        return self._plan

    @property
    def runtime(self) -> Optional[RalplanRuntime]:
        return self._runtime

    # ── State persistence ──────────────────────────────────────────────────

    def _flush_state(self, phase: str) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "mode": _MODE_NAME,
            "phase": phase,
            "timestamp": time.time(),
        }
        if self._config:
            payload.update(
                {
                    "title": self._config.title,
                    "objective": self._config.objective,
                    "consensus_threshold": self._config.consensus_threshold,
                }
            )
        if self._plan:
            payload.update(
                {
                    "plan_id": self._plan.plan_id,
                    "plan_status": self._plan.status.value,
                    "revision": self._plan.revision,
                    "approvals": self._plan.approval_count,
                    "rejections": self._plan.rejection_count,
                }
            )
        _STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
