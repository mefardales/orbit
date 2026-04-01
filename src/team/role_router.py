"""Role router for team orchestration.

Layer 1: Prompt loading utilities (load_role_prompt, is_known_role, list_available_roles)
Layer 2: Heuristic role routing (route_task_to_role)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from .orchestrator import TeamPhase


# ── Layer 1: Prompt Loading ───────────────────────────────────────────────────

SAFE_ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def load_role_prompt(role: str, prompts_dir: str) -> Optional[str]:
    """Load behavioral prompt content for a given agent role.

    Returns None if the prompt file does not exist or the role name is invalid.
    """
    if not SAFE_ROLE_PATTERN.match(role):
        return None
    path = Path(prompts_dir) / f"{role}.md"
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content if content else None
    except (OSError, UnicodeDecodeError):
        return None


def is_known_role(role: str, prompts_dir: str) -> bool:
    """Check whether a role has a corresponding prompt file."""
    if not SAFE_ROLE_PATTERN.match(role):
        return False
    return (Path(prompts_dir) / f"{role}.md").exists()


def list_available_roles(prompts_dir: str) -> List[str]:
    """List all available roles by scanning the prompts directory."""
    try:
        p = Path(prompts_dir)
        if not p.exists():
            return []
        return sorted(
            f.stem for f in p.iterdir() if f.is_file() and f.suffix == ".md"
        )
    except OSError:
        return []


# ── Layer 2: Heuristic Role Routing ──────────────────────────────────────────

Confidence = Literal["high", "medium", "low"]
LaneIntent = Literal[
    "implementation", "verification", "review", "debug", "design",
    "docs", "build-fix", "cleanup", "unknown"
]


@dataclass
class RoleRouterResult:
    role: str
    confidence: Confidence
    reason: str


# Keyword-to-role mapping (order matters within each group)
ROLE_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("test-engineer", [
        "test", "spec", "coverage", "tdd", "jest", "vitest", "mocha", "pytest",
        "unit test", "integration test", "e2e",
    ]),
    ("designer", [
        "ui", "component", "layout", "css", "design", "responsive", "tailwind",
        "react", "frontend", "styling", "ux",
    ]),
    ("build-fixer", [
        "build", "compile", "tsc", "type error", "typescript error",
        "build error", "compilation",
    ]),
    ("debugger", [
        "debug", "investigate", "root cause", "regression", "stack trace",
        "bisect", "diagnose",
    ]),
    ("writer", [
        "doc", "readme", "migration guide", "changelog", "comment",
        "documentation", "api doc",
    ]),
    ("quality-reviewer", [
        "review", "audit", "quality", "lint", "anti-pattern", "code review",
    ]),
    ("security-reviewer", [
        "security", "owasp", "xss", "injection", "cve", "vulnerability",
    ]),
    ("code-simplifier", [
        "refactor", "simplify", "clean up", "reduce complexity", "consolidate",
    ]),
]

# Intent detection patterns
_IMPLEMENTATION = re.compile(
    r"\b(?:add|build|create|fix|implement|make|migrate|repair|ship|support|update|wire)\b", re.I
)
_REVIEW = re.compile(r"\b(?:audit|check|inspect|review|validate|verify)\b", re.I)
_TEST_PRIMARY = re.compile(
    r"^(?:add|create|expand|improve|increase|write)\b.*\b(?:tests?|specs?|coverage)\b", re.I
)
_DOCS = re.compile(r"\b(?:docs?|documentation|readme|guide|changelog)\b", re.I)
_DOCS_PRIMARY = re.compile(
    r"^(?:document|draft|write|update)\b.*\b(?:docs?|documentation|readme|guide|changelog)\b", re.I
)
_DEBUG = re.compile(r"\b(?:debug|diagnose|investigate|root cause|trace|bisect)\b", re.I)
_DESIGN = re.compile(
    r"\b(?:design|layout|style)\b|\b(?:build|create)\b.*\b(?:ui|component|frontend)\b", re.I
)
_BUILD_FIX = re.compile(r"\b(?:build|compile|tsc|type error|compilation)\b", re.I)
_CLEANUP = re.compile(
    r"\b(?:clean up|consolidate|reduce complexity|refactor|simplify)\b", re.I
)
_SECURITY = re.compile(
    r"\b(?:auth|authentication|authorization|cve|injection|owasp|security|vulnerability|xss)\b", re.I
)
_FIX_VERB = re.compile(r"\b(?:fix|resolve|repair)\b", re.I)

# Phase context labels (diagnostic only, not used as role assignments)
PHASE_CONTEXT_LABELS: Dict[str, str] = {
    "team-verify": "verifier",
    "team-fix": "build-fixer",
    "team-plan": "planner",
    "team-prd": "analyst",
}


def _infer_lane_intent(text: str) -> LaneIntent:
    """Classify intent from combined task text."""
    if _BUILD_FIX.search(text) and _FIX_VERB.search(text):
        return "build-fix"
    if _DEBUG.search(text):
        return "debug"
    if _REVIEW.search(text):
        return "review"
    if _TEST_PRIMARY.search(text):
        return "verification"
    if _DOCS_PRIMARY.search(text) or _DOCS.search(text):
        return "docs"
    if _DESIGN.search(text):
        return "design"
    if _CLEANUP.search(text):
        return "cleanup"
    if _IMPLEMENTATION.search(text):
        return "implementation"
    return "unknown"


def route_task_to_role(
    task_subject: str,
    task_description: str,
    phase: Optional[TeamPhase],
    fallback_role: str,
) -> RoleRouterResult:
    """Map a task description to the best agent role using keyword heuristics.

    Falls back to fallback_role when confidence is low.
    """
    text = f"{task_subject} {task_description}".lower()
    intent = _infer_lane_intent(text)

    # Direct intent mapping (high confidence)
    intent_role_map: Dict[LaneIntent, Tuple[str, str]] = {
        "build-fix": ("build-fixer", "primary intent is build/compile repair"),
        "debug": ("debugger", "primary intent is investigation/debugging"),
        "docs": ("writer", "primary intent is documentation deliverable"),
        "design": ("designer", "primary intent is UI/design implementation"),
        "cleanup": ("code-simplifier", "primary intent is simplification/refactor work"),
        "verification": ("test-engineer", "primary intent is test/verification output"),
    }

    if intent in intent_role_map:
        role, reason = intent_role_map[intent]
        return RoleRouterResult(role=role, confidence="high", reason=reason)

    if intent == "review":
        if _SECURITY.search(text):
            return RoleRouterResult(
                role="security-reviewer",
                confidence="high",
                reason="primary intent is security-focused review",
            )
        return RoleRouterResult(
            role="quality-reviewer",
            confidence="high",
            reason="primary intent is review/verification",
        )

    if intent == "implementation" and _SECURITY.search(text):
        return RoleRouterResult(
            role=fallback_role,
            confidence="medium",
            reason="security/auth domain detected but task intent is implementation, using fallback",
        )

    # Score each role category by keyword match count
    best_role = ""
    best_count = 0
    best_keyword = ""

    for role, keywords in ROLE_KEYWORDS:
        count = 0
        matched = ""
        for kw in keywords:
            if kw in text:
                count += 1
                if not matched:
                    matched = kw
        if count > best_count:
            best_count = count
            best_role = role
            best_keyword = matched

    if best_count >= 2:
        return RoleRouterResult(
            role=best_role,
            confidence="high",
            reason=f'matched {best_count} keywords in {best_role} category (e.g., "{best_keyword}")',
        )

    if best_count == 1:
        return RoleRouterResult(
            role=best_role,
            confidence="medium",
            reason=f'matched keyword "{best_keyword}" for {best_role}',
        )

    # Low confidence: phase-context inference only
    if phase:
        phase_default = PHASE_CONTEXT_LABELS.get(phase)
        if phase_default:
            return RoleRouterResult(
                role=fallback_role,
                confidence="low",
                reason=f"no keyword match; phase {phase} suggests {phase_default} but using fallback",
            )

    return RoleRouterResult(
        role=fallback_role,
        confidence="low",
        reason="no keyword match; using fallback role",
    )
