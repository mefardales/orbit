"""Visual verdict parsing and loop feedback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import VISUAL_NEXT_ACTIONS_LIMIT, VISUAL_VERDICT_STATUSES, VisualVerdictStatus


@dataclass
class VisualVerdict:
    score: int
    verdict: VisualVerdictStatus
    category_match: bool
    differences: list[str]
    suggestions: list[str]
    reasoning: str


@dataclass
class VisualLoopFeedback(VisualVerdict):
    threshold: int = 90
    passes_threshold: bool = False
    next_actions: list[str] = field(default_factory=list)


def _as_trimmed_string_array(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"visual_verdict.{field_name} must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"visual_verdict.{field_name} must contain strings")
        trimmed = item.strip()
        if trimmed:
            result.append(trimmed)
    return result


def _parse_visual_verdict_status(value: Any) -> VisualVerdictStatus:
    if not isinstance(value, str):
        raise ValueError(f"visual_verdict.verdict must be one of: {'|'.join(VISUAL_VERDICT_STATUSES)}")
    normalized = value.strip().lower()
    if normalized not in VISUAL_VERDICT_STATUSES:
        raise ValueError(f"visual_verdict.verdict must be one of: {'|'.join(VISUAL_VERDICT_STATUSES)}")
    return normalized  # type: ignore[return-value]


def parse_visual_verdict(input_data: Any) -> VisualVerdict:
    """Parse and validate a visual verdict from raw input."""
    if not input_data or not isinstance(input_data, dict):
        raise ValueError("visual_verdict must be an object")
    raw: dict[str, Any] = input_data

    score = raw.get("score")
    if not isinstance(score, int) or score < 0 or score > 100:
        raise ValueError("visual_verdict.score must be an integer between 0 and 100")

    category_match = raw.get("category_match")
    if not isinstance(category_match, bool):
        raise ValueError("visual_verdict.category_match must be a boolean")

    reasoning = raw.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("visual_verdict.reasoning must be a non-empty string")

    return VisualVerdict(
        score=score,
        verdict=_parse_visual_verdict_status(raw.get("verdict")),
        category_match=category_match,
        differences=_as_trimmed_string_array(raw.get("differences"), "differences"),
        suggestions=_as_trimmed_string_array(raw.get("suggestions"), "suggestions"),
        reasoning=reasoning.strip(),
    )


def build_visual_loop_feedback(input_data: Any, threshold: int = 90) -> VisualLoopFeedback:
    """Build visual loop feedback with threshold evaluation."""
    verdict = parse_visual_verdict(input_data)
    next_actions = (
        verdict.suggestions
        + [f"Fix: {d}" for d in verdict.differences]
    )[:VISUAL_NEXT_ACTIONS_LIMIT]

    return VisualLoopFeedback(
        score=verdict.score,
        verdict=verdict.verdict,
        category_match=verdict.category_match,
        differences=verdict.differences,
        suggestions=verdict.suggestions,
        reasoning=verdict.reasoning,
        threshold=threshold,
        passes_threshold=verdict.score >= threshold,
        next_actions=next_actions,
    )
