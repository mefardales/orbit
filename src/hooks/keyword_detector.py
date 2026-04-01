"""
Keyword Detection Engine.

Detects magic keywords (like $plan, $team, etc.) in user prompts and maps
them to skill activations. Supports both explicit ($skill) and implicit
(natural language) keyword detection.
"""

from __future__ import annotations

import json
import re
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cmp_to_key
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from .keyword_registry import (
    KEYWORD_TRIGGER_DEFINITIONS,
    compare_keyword_matches,
)
from .task_size_detector import (
    TaskSizeResult,
    TaskSizeThresholds,
    classify_task_size,
    is_heavy_mode,
)


@dataclass
class KeywordMatch:
    """A detected keyword match with its skill and priority."""

    keyword: str
    skill: str
    priority: int


SkillActivePhase = Literal["planning", "executing", "reviewing", "completing"]


@dataclass
class DeepInterviewInputLock:
    """Lock state for deep interview auto-approval blocking."""

    active: bool
    scope: str = "deep-interview-auto-approval"
    acquired_at: str = ""
    released_at: Optional[str] = None
    exit_reason: Optional[str] = None
    blocked_inputs: List[str] = field(default_factory=list)
    message: str = ""


@dataclass
class SkillActiveState:
    """Persisted state for the currently active skill."""

    version: int = 1
    active: bool = False
    skill: str = ""
    keyword: str = ""
    phase: SkillActivePhase = "planning"
    activated_at: str = ""
    updated_at: str = ""
    source: str = "keyword-detector"
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    turn_id: Optional[str] = None
    input_lock: Optional[DeepInterviewInputLock] = None


SKILL_ACTIVE_STATE_FILE = "skill-active-state.json"

DEEP_INTERVIEW_BLOCKED_APPROVAL_INPUTS = (
    "yes", "y", "proceed", "continue", "ok", "sure", "go ahead", "next i should"
)

DEEP_INTERVIEW_INPUT_LOCK_MESSAGE = (
    "Deep interview is active; auto-approval shortcuts are blocked until the interview finishes."
)


# --- Internal helpers ---

def _escape_regex(text: str) -> str:
    return re.escape(text)


def _is_word_char(ch: Optional[str]) -> bool:
    if not ch:
        return False
    return bool(re.match(r"[A-Za-z0-9_]", ch))


def _keyword_to_pattern(keyword: str) -> re.Pattern[str]:
    escaped = _escape_regex(keyword)
    prefix = r"\b" if _is_word_char(keyword[0] if keyword else None) else ""
    suffix = r"\b" if _is_word_char(keyword[-1] if keyword else None) else ""
    return re.compile(f"{prefix}{escaped}{suffix}", re.IGNORECASE)


# Build keyword map from registry
_KEYWORD_MAP = [
    {
        "pattern": _keyword_to_pattern(entry.keyword),
        "skill": entry.skill,
        "priority": entry.priority,
    }
    for entry in KEYWORD_TRIGGER_DEFINITIONS
]

_KEYWORDS_REQUIRING_INTENT = {"team", "swarm"}

_TEAM_SWARM_INTENT_PATTERNS: Dict[str, List[re.Pattern[str]]] = {
    "team": [
        re.compile(r"(?:^|[^\w])\$(?:team)\b", re.IGNORECASE),
        re.compile(r"/prompts:team\b", re.IGNORECASE),
        re.compile(r"\b(?:use|run|start|enable|launch|invoke|activate|orchestrate|coordinate)\s+(?:a\s+|an\s+|the\s+)?team\b", re.IGNORECASE),
        re.compile(r"\bteam\s+(?:mode|orchestration|workflow|agents?)\b", re.IGNORECASE),
    ],
    "swarm": [
        re.compile(r"(?:^|[^\w])\$(?:swarm)\b", re.IGNORECASE),
        re.compile(r"/prompts:swarm\b", re.IGNORECASE),
        re.compile(r"\b(?:use|run|start|enable|launch|invoke|activate|orchestrate|coordinate)\s+(?:a\s+|an\s+|the\s+)?swarm\b", re.IGNORECASE),
        re.compile(r"\bswarm\s+(?:mode|orchestration|workflow|agents?)\b", re.IGNORECASE),
    ],
}


def _has_explicit_prompts_invocation(text: str) -> bool:
    return bool(re.search(r"(?:^|\s)/prompts:[\w.-]+(?=[\s.,!?;:]|$)", text, re.IGNORECASE))


def _extract_explicit_skill_invocations(text: str) -> List[KeywordMatch]:
    """Extract explicit $skill invocations from text, left-to-right."""
    results: List[KeywordMatch] = []
    regex = re.compile(r"(?:^|[^\w])\$([a-z][a-z0-9-]*)\b", re.IGNORECASE)
    capture_started = False
    last_match_end = -1

    for match in regex.finditer(text):
        token = (match.group(1) or "").lower()
        if not token:
            continue

        normalized_skill = "team" if token == "swarm" else token
        registry_entry = next(
            (e for e in KEYWORD_TRIGGER_DEFINITIONS if e.skill.lower() == normalized_skill),
            None,
        )
        if not registry_entry:
            continue

        match_start = match.start() + match.group(0).rfind("$")
        if capture_started:
            between = text[last_match_end:match_start]
            if not re.match(r"^\s*$", between):
                break

        capture_started = True
        last_match_end = match_start + len(token) + 1

        if any(item.skill == normalized_skill for item in results):
            continue

        results.append(KeywordMatch(
            keyword=f"${token}",
            skill=normalized_skill,
            priority=registry_entry.priority,
        ))

    return results


def _has_intent_context_for_keyword(text: str, keyword: str) -> bool:
    k = keyword.lower()
    if k not in _KEYWORDS_REQUIRING_INTENT:
        return True
    patterns = _TEAM_SWARM_INTENT_PATTERNS.get(k, [])
    return any(p.search(text) for p in patterns)


def detect_keywords(text: str) -> List[KeywordMatch]:
    """
    Detect keywords in user input text.
    Returns explicit $skill matches first (left-to-right),
    then appends implicit keyword matches sorted by priority.
    """
    explicit = _extract_explicit_skill_invocations(text)
    if _has_explicit_prompts_invocation(text) and len(explicit) == 0:
        return []
    if len(explicit) > 0:
        return explicit

    implicit: List[KeywordMatch] = []
    for entry in _KEYWORD_MAP:
        match = entry["pattern"].search(text)
        if match:
            if not _has_intent_context_for_keyword(text, match.group(0).lower()):
                continue
            implicit.append(KeywordMatch(
                keyword=match.group(0),
                skill=entry["skill"],
                priority=entry["priority"],
            ))

    merged: List[KeywordMatch] = list(explicit)
    sorted_implicit = sorted(
        implicit,
        key=cmp_to_key(lambda a, b: compare_keyword_matches(
            {"priority": a.priority, "keyword": a.keyword},
            {"priority": b.priority, "keyword": b.keyword},
        )),
    )
    for item in sorted_implicit:
        if any(existing.skill == item.skill for existing in merged):
            continue
        merged.append(item)

    return merged


def detect_primary_keyword(text: str) -> Optional[KeywordMatch]:
    """Get the highest-priority keyword match."""
    matches = detect_keywords(text)
    return matches[0] if matches else None


async def record_skill_activation(
    state_dir: str,
    text: str,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    now_iso: Optional[str] = None,
) -> Optional[SkillActiveState]:
    """Record a skill activation to the state directory."""
    match = detect_primary_keyword(text)
    if not match:
        return None

    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat()

    state_path = Path(state_dir) / SKILL_ACTIVE_STATE_FILE
    previous = _read_existing_skill_state(state_path)
    had_deep_interview_lock = (
        previous is not None
        and previous.skill == "deep-interview"
        and previous.input_lock is not None
        and previous.input_lock.active
    )

    matches = detect_keywords(text)
    has_cancel_intent = any(m.skill == "cancel" for m in matches)

    if has_cancel_intent and had_deep_interview_lock:
        input_lock = _release_deep_interview_input_lock(
            previous.input_lock if previous else None, now_iso, "abort"
        )
        state = SkillActiveState(
            version=1,
            active=False,
            skill="deep-interview",
            keyword=previous.keyword if previous else "deep interview",
            phase="completing",
            activated_at=previous.activated_at if previous else now_iso,
            updated_at=now_iso,
            source="keyword-detector",
            session_id=session_id or (previous.session_id if previous else None),
            thread_id=thread_id or (previous.thread_id if previous else None),
            turn_id=turn_id or (previous.turn_id if previous else None),
            input_lock=input_lock,
        )
        _write_skill_state(state_path, state)
        return state

    same_skill = previous is not None and previous.active and previous.skill == match.skill
    same_keyword = (
        previous is not None
        and previous.keyword.lower() == match.keyword.lower()
    )

    if match.skill == "deep-interview":
        input_lock = _create_deep_interview_input_lock(
            now_iso, previous.input_lock if previous else None
        )
    else:
        input_lock = _release_deep_interview_input_lock(
            previous.input_lock if previous else None, now_iso
        )

    state = SkillActiveState(
        version=1,
        active=True,
        skill=match.skill,
        keyword=match.keyword,
        phase="planning",
        activated_at=previous.activated_at if (same_skill and same_keyword and previous) else now_iso,
        updated_at=now_iso,
        source="keyword-detector",
        session_id=session_id,
        thread_id=thread_id,
        turn_id=turn_id,
        input_lock=input_lock,
    )

    _write_skill_state(state_path, state)
    return state


# --- Ralplan gate ---

EXECUTION_GATE_KEYWORDS = frozenset(["ralph", "autopilot", "team", "ultrawork"])

GATE_BYPASS_PREFIXES = ["force:", "!"]

WELL_SPECIFIED_SIGNALS = [
    re.compile(r"\b[\w/.-]+\.(?:ts|js|py|go|rs|java|tsx|jsx|vue|svelte|rb|c|cpp|h|css|scss|html|json|yaml|yml|toml)\b"),
    re.compile(r"(?:src|lib|test|spec|app|pages|components|hooks|utils|services|api|dist|build|scripts)/\w+"),
    re.compile(r"\b(?:function|class|method|interface|type|const|let|var|def|fn|struct|enum)\s+\w{2,}", re.IGNORECASE),
    re.compile(r"\b[a-z]+(?:[A-Z][a-z]+)+\b"),
    re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]*)+\b"),
    re.compile(r"\b[a-z]+(?:_[a-z]+)+\b"),
    re.compile(r"(?:^|\s)#\d+\b"),
    re.compile(r"(?:^|\n)\s*(?:\d+[.)]\s|-\s+\S|\*\s+\S)", re.MULTILINE),
    re.compile(r"\b(?:acceptance\s+criteria|test\s+(?:spec|plan|case)|should\s+(?:return|throw|render|display|create|delete|update))\b", re.IGNORECASE),
    re.compile(r"\b(?:error:|bug\s*#?\d+|issue\s*#\d+|stack\s*trace|exception|TypeError|ReferenceError|SyntaxError)\b", re.IGNORECASE),
    re.compile(r"```[\s\S]{20,}?```"),
    re.compile(r"\b(?:PR\s*#\d+|commit\s+[0-9a-f]{7}|pull\s+request)\b", re.IGNORECASE),
    re.compile(r"\bin\s+[\w/.-]+\.(?:ts|js|py|go|rs|java|tsx|jsx)\b"),
    re.compile(r"\b(?:npm\s+test|npx\s+(?:vitest|jest)|pytest|cargo\s+test|go\s+test|make\s+test)\b", re.IGNORECASE),
]


def is_underspecified_for_execution(text: str) -> bool:
    """
    Check if a prompt is underspecified for direct execution.
    Returns True if the prompt lacks enough specificity for heavy execution modes.
    """
    trimmed = text.strip()
    if not trimmed:
        return True

    for prefix in GATE_BYPASS_PREFIXES:
        if trimmed.startswith(prefix):
            return False

    if any(p.search(trimmed) for p in WELL_SPECIFIED_SIGNALS):
        return False

    stripped = re.sub(r"\b(?:ralph|autopilot|team|ultrawork|ulw|swarm)\b", "", trimmed, flags=re.IGNORECASE).strip()
    effective_words = len([w for w in stripped.split() if w])

    if effective_words <= 15:
        return True

    return False


@dataclass
class RalplanGateResult:
    """Result of applying the ralplan-first gate."""

    keywords: List[str]
    gate_applied: bool
    gated_keywords: List[str]


def apply_ralplan_gate(
    keywords: List[str],
    text: str,
    cwd: Optional[str] = None,
    prior_skill: Optional[str] = None,
) -> RalplanGateResult:
    """
    Apply the ralplan-first gate: if execution keywords are present
    but the prompt is underspecified, redirect to ralplan.
    """
    if not keywords:
        return RalplanGateResult(keywords=keywords, gate_applied=False, gated_keywords=[])

    if "cancel" in keywords:
        return RalplanGateResult(keywords=keywords, gate_applied=False, gated_keywords=[])

    if "ralplan" in keywords:
        return RalplanGateResult(keywords=keywords, gate_applied=False, gated_keywords=[])

    execution_keywords = [k for k in keywords if k in EXECUTION_GATE_KEYWORDS]
    if not execution_keywords:
        return RalplanGateResult(keywords=keywords, gate_applied=False, gated_keywords=[])

    if not is_underspecified_for_execution(text):
        return RalplanGateResult(keywords=keywords, gate_applied=False, gated_keywords=[])

    # Gate: replace execution keywords with ralplan
    filtered = [k for k in keywords if k not in EXECUTION_GATE_KEYWORDS]
    if "ralplan" not in filtered:
        filtered.append("ralplan")

    return RalplanGateResult(
        keywords=filtered,
        gate_applied=True,
        gated_keywords=execution_keywords,
    )


@dataclass
class KeywordSizeCheckResult:
    """Result of keyword detection with task size filtering."""

    keywords: List[str]
    task_size_result: Optional[TaskSizeResult]
    suppressed_keywords: List[str]


def get_all_keywords_with_size_check(
    text: str,
    enabled: bool = True,
    small_word_limit: int = 50,
    large_word_limit: int = 200,
    suppress_heavy_modes_for_small_tasks: bool = True,
) -> KeywordSizeCheckResult:
    """
    Get all keywords with task-size-based filtering applied.
    For small tasks, heavy orchestration modes are suppressed.
    """
    keywords = [m.skill for m in detect_keywords(text)]

    if not enabled or not suppress_heavy_modes_for_small_tasks or not keywords:
        return KeywordSizeCheckResult(
            keywords=keywords,
            task_size_result=None,
            suppressed_keywords=[],
        )

    thresholds = TaskSizeThresholds(
        small_word_limit=small_word_limit,
        large_word_limit=large_word_limit,
    )
    task_size_result = classify_task_size(text, thresholds)

    if task_size_result.size != "small":
        return KeywordSizeCheckResult(
            keywords=keywords,
            task_size_result=task_size_result,
            suppressed_keywords=[],
        )

    suppressed: List[str] = []
    filtered: List[str] = []
    for kw in keywords:
        if is_heavy_mode(kw):
            suppressed.append(kw)
        else:
            filtered.append(kw)

    return KeywordSizeCheckResult(
        keywords=filtered,
        task_size_result=task_size_result,
        suppressed_keywords=suppressed,
    )


# --- Private helpers for state persistence ---

def _read_existing_skill_state(state_path: Path) -> Optional[SkillActiveState]:
    try:
        data = json.loads(state_path.read_text())
        lock_data = data.get("input_lock")
        input_lock = None
        if lock_data and isinstance(lock_data, dict):
            input_lock = DeepInterviewInputLock(
                active=lock_data.get("active", False),
                scope=lock_data.get("scope", "deep-interview-auto-approval"),
                acquired_at=lock_data.get("acquired_at", ""),
                released_at=lock_data.get("released_at"),
                exit_reason=lock_data.get("exit_reason"),
                blocked_inputs=lock_data.get("blocked_inputs", []),
                message=lock_data.get("message", ""),
            )
        return SkillActiveState(
            version=data.get("version", 1),
            active=data.get("active", False),
            skill=data.get("skill", ""),
            keyword=data.get("keyword", ""),
            phase=data.get("phase", "planning"),
            activated_at=data.get("activated_at", ""),
            updated_at=data.get("updated_at", ""),
            source=data.get("source", "keyword-detector"),
            session_id=data.get("session_id"),
            thread_id=data.get("thread_id"),
            turn_id=data.get("turn_id"),
            input_lock=input_lock,
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _write_skill_state(state_path: Path, state: SkillActiveState) -> None:
    data: Dict[str, Any] = {
        "version": state.version,
        "active": state.active,
        "skill": state.skill,
        "keyword": state.keyword,
        "phase": state.phase,
        "activated_at": state.activated_at,
        "updated_at": state.updated_at,
        "source": state.source,
    }
    if state.session_id:
        data["session_id"] = state.session_id
    if state.thread_id:
        data["thread_id"] = state.thread_id
    if state.turn_id:
        data["turn_id"] = state.turn_id
    if state.input_lock:
        data["input_lock"] = {
            "active": state.input_lock.active,
            "scope": state.input_lock.scope,
            "acquired_at": state.input_lock.acquired_at,
            "blocked_inputs": state.input_lock.blocked_inputs,
            "message": state.input_lock.message,
        }
        if state.input_lock.released_at:
            data["input_lock"]["released_at"] = state.input_lock.released_at
        if state.input_lock.exit_reason:
            data["input_lock"]["exit_reason"] = state.input_lock.exit_reason

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(data, indent=2))
    except OSError:
        import sys
        print("[orbit] warning: failed to persist keyword activation state", file=sys.stderr)


def _create_deep_interview_input_lock(
    now_iso: str,
    previous: Optional[DeepInterviewInputLock] = None,
) -> DeepInterviewInputLock:
    return DeepInterviewInputLock(
        active=True,
        scope="deep-interview-auto-approval",
        acquired_at=previous.acquired_at if (previous and previous.active) else now_iso,
        blocked_inputs=list(DEEP_INTERVIEW_BLOCKED_APPROVAL_INPUTS),
        message=DEEP_INTERVIEW_INPUT_LOCK_MESSAGE,
    )


def _release_deep_interview_input_lock(
    previous: Optional[DeepInterviewInputLock],
    now_iso: str,
    reason: str = "handoff",
) -> Optional[DeepInterviewInputLock]:
    if not previous:
        return None
    return DeepInterviewInputLock(
        active=False,
        scope=previous.scope,
        acquired_at=previous.acquired_at,
        released_at=now_iso,
        exit_reason=reason,
        blocked_inputs=previous.blocked_inputs,
        message=previous.message,
    )
