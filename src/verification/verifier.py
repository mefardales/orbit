"""Verification protocol for orbit.

Evidence-backed verification of task completion.
Sizing: small (low), standard (medium), large (high).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional


EvidenceType = Literal["test", "typecheck", "lint", "build", "manual", "runtime"]
TaskSize = Literal["small", "standard", "large"]
Confidence = Literal["high", "medium", "low"]


@dataclass
class VerificationEvidence:
    type: EvidenceType
    passed: bool
    command: Optional[str] = None
    output: Optional[str] = None
    details: Optional[str] = None


@dataclass
class VerificationResult:
    passed: bool
    evidence: list[VerificationEvidence] = field(default_factory=list)
    summary: str = ""
    confidence: Confidence = "medium"


def has_structured_verification_evidence(summary: str | None) -> bool:
    """Heuristic check for structured verification evidence in a task completion summary."""
    if not isinstance(summary, str):
        return False
    text = summary.strip()
    if not text:
        return False

    has_verification_section = bool(
        re.search(r"verification(?:\s+evidence)?\s*:", text, re.IGNORECASE)
        or re.search(r"##\s*verification", text, re.IGNORECASE)
    )
    if not has_verification_section:
        return False

    has_evidence_signal = bool(
        re.search(r"\b(pass|passed|fail|failed)\b", text, re.IGNORECASE)
        or re.search(r"`[^`]+`", text)
        or re.search(r"\b(command|test|build|typecheck|lint)\b", text, re.IGNORECASE)
    )
    return has_evidence_signal


def get_verification_instructions(task_size: TaskSize, task_description: str) -> str:
    """Generate verification instructions for a given task size."""
    base = (
        f"\n## Verification Protocol\n\n"
        f"Verify the following task is complete: {task_description}\n\n"
        f"### Required Evidence:\n"
    )

    if task_size == "small":
        return base + (
            "\n1. Run type checker on modified files (if TypeScript/typed language)\n"
            "2. Run tests related to the change\n"
            "3. Confirm the change works as described\n\n"
            "Report: PASS/FAIL with evidence for each check.\n"
        )

    if task_size == "standard":
        return base + (
            "\n1. Run full type check (tsc --noEmit or equivalent)\n"
            "2. Run test suite (focus on changed areas)\n"
            "3. Run linter on modified files\n"
            "4. Verify the feature/fix works end-to-end\n"
            "5. Check for regressions in related functionality\n\n"
            "Report: PASS/FAIL with command output for each check.\n"
        )

    # large
    return base + (
        "\n1. Run full type check across the project\n"
        "2. Run complete test suite\n"
        "3. Run linter across modified files\n"
        "4. Security review of changes (OWASP top 10)\n"
        "5. Performance impact assessment\n"
        "6. API compatibility check (if applicable)\n"
        "7. End-to-end verification of all affected features\n"
        "8. Regression testing of adjacent functionality\n\n"
        "Report: PASS/FAIL with detailed evidence for each check.\n"
        "Include confidence level (high/medium/low) with justification.\n"
    )


def determine_task_size(file_count: int, line_changes: int) -> TaskSize:
    """Determine task size from file count and line changes."""
    if file_count <= 3 and line_changes < 100:
        return "small"
    if file_count <= 15 and line_changes < 500:
        return "standard"
    return "large"


def get_fix_loop_instructions(max_retries: int = 3) -> str:
    """Generate the verification fix-loop instructions."""
    return (
        f"\n## Fix-Verify Loop\n\n"
        f"If verification fails:\n"
        f"1. Identify the root cause of each failure\n"
        f"2. Fix the issue (prefer minimal changes)\n"
        f"3. Re-run verification\n"
        f"4. Repeat up to {max_retries} times\n"
        f"5. If still failing after {max_retries} attempts, escalate with:\n"
        f"   - What was attempted\n"
        f"   - What failed and why\n"
        f"   - Recommended next steps\n"
    )
