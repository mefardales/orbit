"""Ralph phase contract: validation and normalization of ralph mode state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

RALPH_PHASES = (
    "starting",
    "executing",
    "verifying",
    "fixing",
    "complete",
    "failed",
    "cancelled",
)

RalphPhase = Literal[
    "starting", "executing", "verifying", "fixing", "complete", "failed", "cancelled"
]

RALPH_TERMINAL_PHASES: frozenset[RalphPhase] = frozenset({"complete", "failed", "cancelled"})

_RALPH_PHASE_SET: set[str] = set(RALPH_PHASES)

_LEGACY_PHASE_ALIASES: dict[str, RalphPhase] = {
    "start": "starting",
    "started": "starting",
    "execution": "executing",
    "execute": "executing",
    "verify": "verifying",
    "verification": "verifying",
    "fix": "fixing",
    "complete": "complete",
    "completed": "complete",
    "fail": "failed",
    "error": "failed",
    "cancel": "cancelled",
}


def _as_finite_number(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    import math
    if not math.isfinite(value):
        return None
    return value


def _is_iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        pass
    # Fallback: try parsing more loosely
    try:
        from email.utils import parsedate_to_datetime
        parsedate_to_datetime(value)
        return True
    except Exception:
        return False


@dataclass
class NormalizedPhaseResult:
    phase: Optional[RalphPhase] = None
    warning: Optional[str] = None
    error: Optional[str] = None


@dataclass
class RalphStateValidationResult:
    ok: bool
    state: Optional[dict[str, Any]] = None
    warning: Optional[str] = None
    error: Optional[str] = None


def normalize_ralph_phase(raw_phase: Any) -> NormalizedPhaseResult:
    """Normalize a raw phase value to a canonical RalphPhase."""
    if not isinstance(raw_phase, str) or not raw_phase.strip():
        return NormalizedPhaseResult(error="ralph.current_phase must be a non-empty string")

    normalized = raw_phase.strip().lower()
    if normalized in _RALPH_PHASE_SET:
        return NormalizedPhaseResult(phase=normalized)  # type: ignore[arg-type]

    alias = _LEGACY_PHASE_ALIASES.get(normalized)
    if alias:
        return NormalizedPhaseResult(
            phase=alias,
            warning=f'normalized legacy Ralph phase "{raw_phase}" -> "{alias}"',
        )

    return NormalizedPhaseResult(
        error=f"ralph.current_phase must be one of: {', '.join(RALPH_PHASES)}"
    )


def validate_and_normalize_ralph_state(
    candidate: dict[str, Any],
    *,
    now_iso: Optional[str] = None,
) -> RalphStateValidationResult:
    """Validate and normalize a ralph mode state dict."""
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat()

    state: dict[str, Any] = {**candidate}
    warning: Optional[str] = None

    if state.get("current_phase") is not None:
        result = normalize_ralph_phase(state["current_phase"])
        if result.error:
            return RalphStateValidationResult(ok=False, error=result.error)
        state["current_phase"] = result.phase
        if result.warning:
            warning = result.warning

    if state.get("active") is True:
        if state.get("iteration") is None:
            state["iteration"] = 0
        if state.get("max_iterations") is None:
            state["max_iterations"] = 50
        if state.get("current_phase") is None:
            state["current_phase"] = "starting"
        if state.get("started_at") is None:
            state["started_at"] = now_iso

    if state.get("iteration") is not None:
        val = _as_finite_number(state["iteration"])
        if val is None or not float(val).is_integer() or val < 0:
            return RalphStateValidationResult(ok=False, error="ralph.iteration must be a finite integer >= 0")

    if state.get("max_iterations") is not None:
        val = _as_finite_number(state["max_iterations"])
        if val is None or not float(val).is_integer() or val <= 0:
            return RalphStateValidationResult(ok=False, error="ralph.max_iterations must be a finite integer > 0")

    current_phase = state.get("current_phase")
    if isinstance(current_phase, str) and current_phase in RALPH_TERMINAL_PHASES:
        if state.get("active") is True:
            return RalphStateValidationResult(ok=False, error="terminal Ralph phases require active=false")
        if state.get("completed_at") is None:
            state["completed_at"] = now_iso

    if state.get("started_at") is not None and not _is_iso_timestamp(state["started_at"]):
        return RalphStateValidationResult(ok=False, error="ralph.started_at must be an ISO8601 timestamp")
    if state.get("completed_at") is not None and not _is_iso_timestamp(state["completed_at"]):
        return RalphStateValidationResult(ok=False, error="ralph.completed_at must be an ISO8601 timestamp")

    return RalphStateValidationResult(ok=True, state=state, warning=warning)
