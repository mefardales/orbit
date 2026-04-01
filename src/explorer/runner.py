"""
ExploreRunner — safely execute allowlisted commands and capture their output.

Enforces:
  - Safety classification via CommandClassifier before any execution.
  - Working-directory restriction: cwd must be within the project root.
  - Output truncation (max 10 000 output lines combined).
  - Per-command timeout (30 seconds default).
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .classifier import ClassificationResult, CommandClassifier

MAX_OUTPUT_LINES = 10_000
DEFAULT_TIMEOUT_S = 30.0

_classifier = CommandClassifier()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ExploreResult:
    command: str
    argv: List[str]
    stdout: str
    stderr: str
    exit_code: int
    is_truncated: bool = False
    truncated_lines: int = 0
    error: Optional[str] = None      # set when execution itself failed
    blocked: bool = False            # set when classifier rejected the command
    block_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------

def _resolve_within_root(cwd: str, project_root: str) -> str:
    """
    Return cwd resolved to an absolute path, raising ValueError if it is
    outside project_root.
    """
    resolved_cwd = Path(cwd).resolve()
    resolved_root = Path(project_root).resolve()
    try:
        resolved_cwd.relative_to(resolved_root)
    except ValueError:
        raise ValueError(
            f"working directory {resolved_cwd!r} is outside project root {resolved_root!r}"
        )
    return str(resolved_cwd)


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------

def _truncate(text: str, max_lines: int) -> tuple[str, bool, int]:
    """
    Truncate *text* to at most *max_lines* lines.

    Returns (truncated_text, was_truncated, original_line_count).
    """
    lines = text.splitlines(keepends=True)
    total = len(lines)
    if total <= max_lines:
        return text, False, total
    kept = lines[:max_lines]
    omitted = total - max_lines
    kept.append(f"\n[... {omitted} lines truncated ...]\n")
    return "".join(kept), True, total


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class ExploreRunner:
    """
    Runs allowlisted exploration commands safely.

    Args:
        project_root: Absolute path of the project root.  cwd must be within
                      this directory.
        timeout_s:    Per-command timeout in seconds.
        max_lines:    Maximum combined output lines before truncation.
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_lines: int = MAX_OUTPUT_LINES,
    ) -> None:
        self.project_root = project_root or os.getcwd()
        self.timeout_s = timeout_s
        self.max_lines = max_lines

    def run(
        self,
        command: str,
        cwd: Optional[str] = None,
    ) -> ExploreResult:
        """
        Execute *command* if it passes the safety classifier.

        Args:
            command: Raw command string (e.g. "git log --oneline -10").
            cwd:     Working directory for the subprocess.  Must be within
                     self.project_root.  Defaults to project_root.

        Returns:
            ExploreResult.  Check .blocked and .error before using output.
        """
        # Classify first.
        result: ClassificationResult = _classifier.classify(command)
        if not result.safe:
            return ExploreResult(
                command=command,
                argv=[],
                stdout="",
                stderr="",
                exit_code=1,
                blocked=True,
                block_reason=result.reason,
                error=result.reason,
            )

        # Resolve and validate working directory.
        effective_cwd = cwd or self.project_root
        try:
            effective_cwd = _resolve_within_root(effective_cwd, self.project_root)
        except ValueError as exc:
            return ExploreResult(
                command=command,
                argv=[],
                stdout="",
                stderr="",
                exit_code=1,
                blocked=True,
                block_reason=str(exc),
                error=str(exc),
            )

        # Parse argv (already validated by classifier — shlex.split is safe here).
        argv = shlex.split(command)

        # Execute.
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                cwd=effective_cwd,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ExploreResult(
                command=command,
                argv=argv,
                stdout="",
                stderr="",
                exit_code=124,
                error=f"command timed out after {self.timeout_s}s",
            )
        except FileNotFoundError:
            return ExploreResult(
                command=command,
                argv=argv,
                stdout="",
                stderr="",
                exit_code=127,
                error=f"executable not found: {argv[0]!r}",
            )
        except OSError as exc:
            return ExploreResult(
                command=command,
                argv=argv,
                stdout="",
                stderr="",
                exit_code=1,
                error=f"OS error: {exc}",
            )

        # Truncate combined output.
        combined = proc.stdout + proc.stderr
        combined_lines = len(combined.splitlines())

        stdout, stdout_truncated, stdout_total = _truncate(proc.stdout, self.max_lines)
        # Reserve remaining budget for stderr.
        stderr_budget = max(0, self.max_lines - stdout_total)
        stderr, stderr_truncated, _ = _truncate(proc.stderr, stderr_budget)

        is_truncated = stdout_truncated or stderr_truncated
        truncated_lines = max(0, combined_lines - self.max_lines)

        return ExploreResult(
            command=command,
            argv=argv,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            is_truncated=is_truncated,
            truncated_lines=truncated_lines,
        )
