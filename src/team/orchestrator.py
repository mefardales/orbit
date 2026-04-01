"""Team orchestration: phased pipeline for plan -> prd -> exec -> verify -> fix.

Manages the team lifecycle through well-defined phases with transition rules,
fix-loop limits, and per-phase agent role recommendations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

from .state.types import TeamTask


# ── Phase types ───────────────────────────────────────────────────────────────

TeamPhase = Literal["team-plan", "team-prd", "team-exec", "team-verify", "team-fix"]
TerminalPhase = Literal["complete", "failed", "cancelled"]
AnyPhase = Union[TeamPhase, TerminalPhase]

TERMINAL_PHASES: List[TerminalPhase] = ["complete", "failed", "cancelled"]
FIX_LOOP_EXCEEDED_REASON = "team-fix loop limit reached"


# ── Phase transition rules ────────────────────────────────────────────────────

TRANSITIONS: Dict[TeamPhase, List[AnyPhase]] = {
    "team-plan": ["team-prd"],
    "team-prd": ["team-exec"],
    "team-exec": ["team-verify"],
    "team-verify": ["team-fix", "complete", "failed"],
    "team-fix": ["team-exec", "team-verify", "complete", "failed"],
}


def is_valid_transition(from_phase: TeamPhase, to_phase: AnyPhase) -> bool:
    """Check if a phase transition is allowed."""
    allowed = TRANSITIONS.get(from_phase)
    if allowed is None:
        return False
    return to_phase in allowed


def is_terminal_phase(phase: AnyPhase) -> bool:
    """Check if a phase is terminal (complete, failed, or cancelled)."""
    return phase in TERMINAL_PHASES


# ── Team state ────────────────────────────────────────────────────────────────


@dataclass
class PhaseTransition:
    from_phase: str
    to_phase: str
    at: str
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        d: Dict[str, Optional[str]] = {
            "from": self.from_phase,
            "to": self.to_phase,
            "at": self.at,
        }
        if self.reason:
            d["reason"] = self.reason
        return d


@dataclass
class TeamState:
    active: bool = True
    phase: AnyPhase = "team-plan"
    task_description: str = ""
    created_at: str = ""
    phase_transitions: List[PhaseTransition] = field(default_factory=list)
    tasks: List[TeamTask] = field(default_factory=list)
    max_fix_attempts: int = 3
    current_fix_attempt: int = 0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"


def create_team_state(task_description: str, max_fix_attempts: int = 3) -> TeamState:
    """Create initial team state in the planning phase."""
    return TeamState(
        active=True,
        phase="team-plan",
        task_description=task_description,
        max_fix_attempts=max_fix_attempts,
        current_fix_attempt=0,
    )


def can_resume_team_state(state: TeamState) -> bool:
    """Check if a team state can be resumed (active and non-terminal)."""
    return state.active and not is_terminal_phase(state.phase)


def transition_phase(
    state: TeamState,
    to: AnyPhase,
    reason: Optional[str] = None,
) -> TeamState:
    """Transition team state to the next phase.

    Returns a new TeamState with the updated phase. Raises ValueError
    if the transition is invalid.
    """
    from_phase = state.phase
    now_iso = datetime.utcnow().isoformat() + "Z"

    if is_terminal_phase(from_phase):
        raise ValueError(f"Cannot transition from terminal phase: {from_phase}")

    # Type narrowing: from_phase must be a TeamPhase here
    if not is_valid_transition(from_phase, to):  # type: ignore[arg-type]
        raise ValueError(f"Invalid transition: {from_phase} -> {to}")

    next_fix = state.current_fix_attempt
    if to == "team-fix":
        next_fix += 1
        if next_fix > state.max_fix_attempts:
            # Auto-fail when fix loop limit exceeded
            fail_transition = PhaseTransition(
                from_phase=from_phase,
                to_phase="failed",
                at=now_iso,
                reason=f"{FIX_LOOP_EXCEEDED_REASON} ({state.max_fix_attempts})",
            )
            return TeamState(
                active=False,
                phase="failed",
                task_description=state.task_description,
                created_at=state.created_at,
                phase_transitions=[*state.phase_transitions, fail_transition],
                tasks=list(state.tasks),
                max_fix_attempts=state.max_fix_attempts,
                current_fix_attempt=next_fix,
            )

    is_terminal = is_terminal_phase(to)
    transition = PhaseTransition(
        from_phase=from_phase,
        to_phase=to,
        at=now_iso,
        reason=reason,
    )

    return TeamState(
        active=not is_terminal,
        phase=to,
        task_description=state.task_description,
        created_at=state.created_at,
        phase_transitions=[*state.phase_transitions, transition],
        tasks=list(state.tasks),
        max_fix_attempts=state.max_fix_attempts,
        current_fix_attempt=next_fix,
    )


# ── Phase agent recommendations ──────────────────────────────────────────────


def get_phase_agents(phase: TeamPhase) -> List[str]:
    """Get recommended agent roles for a given phase."""
    agents: Dict[TeamPhase, List[str]] = {
        "team-plan": ["analyst", "planner"],
        "team-prd": ["product-manager", "analyst"],
        "team-exec": ["executor", "designer", "test-engineer"],
        "team-verify": ["verifier", "quality-reviewer", "security-reviewer"],
        "team-fix": ["executor", "build-fixer", "debugger"],
    }
    return agents.get(phase, [])


def get_phase_instructions(phase: TeamPhase) -> str:
    """Get human-readable phase instructions for worker context."""
    instructions: Dict[TeamPhase, str] = {
        "team-plan": (
            "PHASE: Planning. Use /analyst for requirements, "
            "/planner for task breakdown. Output: task list with dependencies."
        ),
        "team-prd": (
            "PHASE: Requirements. Use /product-manager for PRD, "
            "/analyst for acceptance criteria. Output: explicit scope and success metrics."
        ),
        "team-exec": (
            "PHASE: Execution. Use /executor for implementation, "
            "/test-engineer for tests. Output: working code with tests."
        ),
        "team-verify": (
            "PHASE: Verification. Use /verifier for evidence collection, "
            "/quality-reviewer for review. Output: pass/fail with evidence."
        ),
        "team-fix": (
            "PHASE: Fixing. Use /debugger for root cause, "
            "/executor for fixes. Output: fixed code, re-verify needed."
        ),
    }
    result = instructions.get(phase)
    if result is None:
        raise ValueError(f"Unknown team phase: {phase}")
    return result
