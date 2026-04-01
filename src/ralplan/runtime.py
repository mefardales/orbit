"""Ralplan: multi-agent consensus planning runtime."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class PlanStatus(Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    CONSENSUS = "consensus"
    FINALIZED = "finalized"
    REJECTED = "rejected"


@dataclass
class PlanStep:
    """A single step in a plan."""

    step_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    assignee: str = ""
    depends_on: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewVote:
    """A vote from a reviewer on a plan."""

    reviewer: str
    approve: bool
    comments: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class Plan:
    """A complete plan with steps and review history."""

    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    objective: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: float = field(default_factory=time.time)
    finalized_at: Optional[float] = None
    votes: list[ReviewVote] = field(default_factory=list)
    revision: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def approval_count(self) -> int:
        return sum(1 for v in self.votes if v.approve)

    @property
    def rejection_count(self) -> int:
        return sum(1 for v in self.votes if not v.approve)


class RalplanRuntime:
    """Orchestrates plan creation, multi-agent review, and consensus checking."""

    def __init__(
        self,
        *,
        consensus_threshold: float = 0.67,
        max_review_cycles: int = 5,
        reviewers: Optional[list[str]] = None,
    ) -> None:
        self.consensus_threshold = consensus_threshold
        self.max_review_cycles = max_review_cycles
        self.reviewers = reviewers or []
        self._plans: dict[str, Plan] = {}

    # -- plan lifecycle --------------------------------------------------------

    def plan(
        self,
        title: str,
        objective: str,
        steps: list[dict[str, Any]],
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Plan:
        """Create a new plan from a title, objective, and list of step dicts."""
        plan_steps = []
        for s in steps:
            plan_steps.append(
                PlanStep(
                    description=s.get("description", ""),
                    assignee=s.get("assignee", ""),
                    depends_on=s.get("depends_on", []),
                    estimated_tokens=s.get("estimated_tokens", 0),
                    metadata=s.get("metadata", {}),
                )
            )
        p = Plan(
            title=title,
            objective=objective,
            steps=plan_steps,
            metadata=metadata or {},
        )
        self._plans[p.plan_id] = p
        logger.info("Created plan %s: %s (%d steps)", p.plan_id, title, len(plan_steps))
        return p

    def review_cycle(
        self,
        plan_id: str,
        votes: list[dict[str, Any]],
    ) -> Plan:
        """Submit a batch of review votes and advance the plan status."""
        p = self._get(plan_id)
        if p.status == PlanStatus.FINALIZED:
            raise RuntimeError(f"Plan {plan_id} is already finalized")

        p.status = PlanStatus.IN_REVIEW
        p.revision += 1

        for v in votes:
            p.votes.append(
                ReviewVote(
                    reviewer=v["reviewer"],
                    approve=v.get("approve", False),
                    comments=v.get("comments", ""),
                )
            )

        if self.consensus_check(plan_id):
            p.status = PlanStatus.CONSENSUS
            logger.info("Plan %s reached consensus after %d revisions", plan_id, p.revision)
        elif p.revision >= self.max_review_cycles:
            p.status = PlanStatus.REJECTED
            logger.warning("Plan %s rejected after %d review cycles", plan_id, p.revision)
        else:
            logger.info(
                "Plan %s review cycle %d: %d approvals, %d rejections",
                plan_id,
                p.revision,
                p.approval_count,
                p.rejection_count,
            )

        return p

    def consensus_check(self, plan_id: str) -> bool:
        """Return ``True`` if approval ratio meets the consensus threshold."""
        p = self._get(plan_id)
        total = len(p.votes)
        if total == 0:
            return False
        ratio = p.approval_count / total
        return ratio >= self.consensus_threshold

    def finalize(self, plan_id: str, *, force: bool = False) -> Plan:
        """Finalize a plan that has reached consensus (or force-finalize)."""
        p = self._get(plan_id)
        if not force and p.status != PlanStatus.CONSENSUS:
            raise RuntimeError(
                f"Plan {plan_id} has not reached consensus (status={p.status.value}). "
                "Pass force=True to override."
            )
        p.status = PlanStatus.FINALIZED
        p.finalized_at = time.time()
        logger.info("Finalized plan %s", plan_id)
        return p

    # -- queries ---------------------------------------------------------------

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        return self._plans.get(plan_id)

    def list_plans(self, *, status: Optional[PlanStatus] = None) -> list[Plan]:
        plans = list(self._plans.values())
        if status is not None:
            plans = [p for p in plans if p.status == status]
        return plans

    def summary(self, plan_id: str) -> dict[str, Any]:
        p = self._get(plan_id)
        return {
            "plan_id": p.plan_id,
            "title": p.title,
            "status": p.status.value,
            "steps": len(p.steps),
            "revision": p.revision,
            "approvals": p.approval_count,
            "rejections": p.rejection_count,
            "consensus": self.consensus_check(plan_id),
        }

    # -- internal --------------------------------------------------------------

    def _get(self, plan_id: str) -> Plan:
        p = self._plans.get(plan_id)
        if p is None:
            raise KeyError(f"No plan with id {plan_id!r}")
        return p
