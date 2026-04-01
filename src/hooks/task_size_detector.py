"""
Task Size Detector - classifies user prompts as small, medium, or large
to determine appropriate orchestration level.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional


TaskSize = Literal["small", "medium", "large"]


@dataclass
class TaskSizeResult:
    """Result of task size classification."""

    size: TaskSize
    reason: str
    word_count: int
    has_escape_hatch: bool
    escape_prefix_used: Optional[str] = None


@dataclass
class TaskSizeThresholds:
    """Word limit thresholds for task size classification."""

    small_word_limit: int = 50
    large_word_limit: int = 200


DEFAULT_THRESHOLDS = TaskSizeThresholds()

ESCAPE_HATCH_PREFIXES = [
    "quick:",
    "simple:",
    "tiny:",
    "minor:",
    "small:",
    "just:",
    "only:",
]

SMALL_TASK_SIGNALS = [
    re.compile(r"\btypo\b", re.IGNORECASE),
    re.compile(r"\bspelling\b", re.IGNORECASE),
    re.compile(r"\brename\s+\w+\s+to\b", re.IGNORECASE),
    re.compile(r"\bone[\s-]liner?\b", re.IGNORECASE),
    re.compile(r"\bone[\s-]line\s+fix\b", re.IGNORECASE),
    re.compile(r"\bsingle\s+file\b", re.IGNORECASE),
    re.compile(r"\bin\s+this\s+file\b", re.IGNORECASE),
    re.compile(r"\bthis\s+function\b", re.IGNORECASE),
    re.compile(r"\bthis\s+line\b", re.IGNORECASE),
    re.compile(r"\bminor\s+(?:fix|change|update|tweak)\b", re.IGNORECASE),
    re.compile(r"\bfix\s+(?:a\s+)?typo\b", re.IGNORECASE),
    re.compile(r"\badd\s+a?\s*comment\b", re.IGNORECASE),
    re.compile(r"\bwhitespace\b", re.IGNORECASE),
    re.compile(r"\bindentation\b", re.IGNORECASE),
    re.compile(r"\bformat(?:ting)?\s+(?:this|the)\b", re.IGNORECASE),
    re.compile(r"\bquick\s+fix\b", re.IGNORECASE),
    re.compile(r"\bsmall\s+(?:fix|change|tweak|update)\b", re.IGNORECASE),
    re.compile(r"\bupdate\s+(?:the\s+)?version\b", re.IGNORECASE),
    re.compile(r"\bbump\s+version\b", re.IGNORECASE),
]

LARGE_TASK_SIGNALS = [
    re.compile(r"\barchitect(?:ure|ural)?\b", re.IGNORECASE),
    re.compile(r"\brefactor\b", re.IGNORECASE),
    re.compile(r"\bredesign\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+scratch\b", re.IGNORECASE),
    re.compile(r"\bcross[\s-]cutting\b", re.IGNORECASE),
    re.compile(r"\bentire\s+(?:codebase|project|application|app|system)\b", re.IGNORECASE),
    re.compile(r"\ball\s+(?:files|modules|components)\b", re.IGNORECASE),
    re.compile(r"\bmultiple\s+files\b", re.IGNORECASE),
    re.compile(r"\bacross\s+(?:the\s+)?(?:codebase|project|files|modules)\b", re.IGNORECASE),
    re.compile(r"\bsystem[\s-]wide\b", re.IGNORECASE),
    re.compile(r"\bmigrat(?:e|ion)\b", re.IGNORECASE),
    re.compile(r"\bfull[\s-]stack\b", re.IGNORECASE),
    re.compile(r"\bend[\s-]to[\s-]end\b", re.IGNORECASE),
    re.compile(r"\boverhaul\b", re.IGNORECASE),
    re.compile(r"\bcomprehensive\b", re.IGNORECASE),
    re.compile(r"\bextensive\b", re.IGNORECASE),
    re.compile(r"\bimplement\s+(?:a\s+)?(?:new\s+)?system\b", re.IGNORECASE),
    re.compile(r"\bbuild\s+(?:a\s+)?(?:complete|full|new)\b", re.IGNORECASE),
]

HEAVY_MODE_KEYWORDS = frozenset([
    "ralph",
    "autopilot",
    "team",
    "ultrawork",
    "swarm",
    "ralplan",
    "ccg",
])


def count_words(text: str) -> int:
    """Count words in a prompt (splits on whitespace)."""
    return len([w for w in text.strip().split() if w])


def detect_escape_hatch(text: str) -> Optional[str]:
    """Check if the prompt starts with a lightweight escape hatch prefix."""
    trimmed = text.strip().lower()
    for prefix in ESCAPE_HATCH_PREFIXES:
        if trimmed.startswith(prefix):
            return prefix
    return None


def has_small_task_signals(text: str) -> bool:
    """Check for small task signal patterns."""
    return any(p.search(text) for p in SMALL_TASK_SIGNALS)


def has_large_task_signals(text: str) -> bool:
    """Check for large task signal patterns."""
    return any(p.search(text) for p in LARGE_TASK_SIGNALS)


def classify_task_size(
    text: str,
    thresholds: Optional[TaskSizeThresholds] = None,
) -> TaskSizeResult:
    """
    Classify a user prompt as small, medium, or large.

    Classification rules (in priority order):
    1. Escape hatch prefix (quick:, simple:, etc.) -> always small
    2. Large task signals (architecture, refactor, entire codebase) -> large
    3. Prompt > large_word_limit words -> large
    4. Small task signals (typo, single file, rename) AND prompt < large_word_limit -> small
    5. Prompt < small_word_limit words -> small
    6. Everything else -> medium
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    word_count = count_words(text)
    escape_prefix = detect_escape_hatch(text)

    # Rule 1: Explicit escape hatch
    if escape_prefix is not None:
        return TaskSizeResult(
            size="small",
            reason=f'Escape hatch prefix detected: "{escape_prefix}"',
            word_count=word_count,
            has_escape_hatch=True,
            escape_prefix_used=escape_prefix,
        )

    has_large = has_large_task_signals(text)
    has_small = has_small_task_signals(text)

    # Rule 2: Large task signals
    if has_large:
        return TaskSizeResult(
            size="large",
            reason="Large task signals detected (architecture/refactor/cross-cutting scope)",
            word_count=word_count,
            has_escape_hatch=False,
        )

    # Rule 3: Long prompt
    if word_count > thresholds.large_word_limit:
        return TaskSizeResult(
            size="large",
            reason=f"Prompt length ({word_count} words) exceeds large task threshold ({thresholds.large_word_limit})",
            word_count=word_count,
            has_escape_hatch=False,
        )

    # Rule 4: Small signals + within limits
    if has_small and not has_large:
        return TaskSizeResult(
            size="small",
            reason="Small task signals detected (single file / minor change)",
            word_count=word_count,
            has_escape_hatch=False,
        )

    # Rule 5: Short prompt
    if word_count <= thresholds.small_word_limit:
        return TaskSizeResult(
            size="small",
            reason=f"Prompt length ({word_count} words) is within small task threshold ({thresholds.small_word_limit})",
            word_count=word_count,
            has_escape_hatch=False,
        )

    # Rule 6: Default
    return TaskSizeResult(
        size="medium",
        reason=f"Prompt length ({word_count} words) is in medium range",
        word_count=word_count,
        has_escape_hatch=False,
    )


def is_heavy_mode(keyword_type: str) -> bool:
    """Check if a keyword type is a heavy orchestration mode."""
    return keyword_type in HEAVY_MODE_KEYWORDS
