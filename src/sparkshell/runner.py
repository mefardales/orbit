"""
SparkshellRunner and OutputSummarizer — high-level API over exec_runner.

SparkshellRunner:
  - Direct argv execution (no shell metacharacter interpretation).
  - Captures stdout + stderr as text.
  - Counts visible vs invisible lines.
  - Enforces a configurable timeout (default 60 s).

OutputSummarizer:
  - Returns output as-is when it fits within max_lines.
  - Truncates with a "[... N lines truncated ...]" marker otherwise.
  - Provides language-aware pattern detection for test runners, build tools,
    and git log output.

TmuxCapture:
  - capture_pane(pane_id, tail_lines) → captured output string.
  - Uses `tmux capture-pane -p -t {pane_id}`.
  - Validates tail_lines in the 100-1000 range.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .error import SparkshellError
from .exec_runner import CommandOutput, execute_command
from .threshold import count_visible_lines

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_S = 60.0
MIN_TMUX_TAIL = 100
MAX_TMUX_TAIL = 1000
DEFAULT_TMUX_TAIL = 200


# ---------------------------------------------------------------------------
# SparkshellResult
# ---------------------------------------------------------------------------

@dataclass
class SparkshellResult:
    """Result returned by SparkshellRunner.execute()."""

    command: List[str]
    stdout: str
    stderr: str
    exit_code: int
    visible_lines: int
    invisible_lines: int        # ANSI escape / carriage-return lines
    timed_out: bool = False
    error: Optional[str] = None

    @property
    def total_lines(self) -> int:
        return self.visible_lines + self.invisible_lines

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.error is None


# ---------------------------------------------------------------------------
# Line classification helpers
# ---------------------------------------------------------------------------

# ANSI escape sequences (colour codes, cursor movement, …).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Carriage-return overwrite lines (e.g. progress bars).
_CR_RE = re.compile(r"\r(?!\n)")


def _classify_lines(text: str) -> tuple[int, int]:
    """
    Return (visible_lines, invisible_lines) for *text*.

    A line is "invisible" when it consists solely of ANSI codes / CR control.
    """
    if not text:
        return 0, 0
    visible = 0
    invisible = 0
    for line in text.splitlines():
        stripped = _ANSI_RE.sub("", _CR_RE.sub("", line)).strip()
        if stripped:
            visible += 1
        else:
            invisible += 1
    return visible, invisible


# ---------------------------------------------------------------------------
# SparkshellRunner
# ---------------------------------------------------------------------------

class SparkshellRunner:
    """
    Execute a command given as an argv list (no shell interpretation).

    Args:
        timeout_s: Wall-clock timeout per execution in seconds.
        cwd:       Optional working directory.
    """

    def __init__(
        self,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        cwd: Optional[str] = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.cwd = cwd

    def execute(self, command: List[str]) -> SparkshellResult:
        """
        Run *command* directly (argv list, no shell).

        Returns a SparkshellResult.  Never raises — errors are captured in
        result.error and result.exit_code.
        """
        if not command:
            return SparkshellResult(
                command=command,
                stdout="",
                stderr="",
                exit_code=2,
                visible_lines=0,
                invisible_lines=0,
                error="empty command",
            )

        try:
            import subprocess as _sp
            proc = _sp.run(
                command,
                capture_output=True,
                cwd=self.cwd,
                timeout=self.timeout_s,
            )
        except _sp.TimeoutExpired:
            return SparkshellResult(
                command=command,
                stdout="",
                stderr="",
                exit_code=124,
                visible_lines=0,
                invisible_lines=0,
                timed_out=True,
                error=f"timed out after {self.timeout_s}s",
            )
        except FileNotFoundError:
            return SparkshellResult(
                command=command,
                stdout="",
                stderr="",
                exit_code=127,
                visible_lines=0,
                invisible_lines=0,
                error=f"executable not found: {command[0]!r}",
            )
        except OSError as exc:
            return SparkshellResult(
                command=command,
                stdout="",
                stderr="",
                exit_code=1,
                visible_lines=0,
                invisible_lines=0,
                error=str(exc),
            )

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")

        vis_out, inv_out = _classify_lines(stdout)
        vis_err, inv_err = _classify_lines(stderr)

        return SparkshellResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            visible_lines=vis_out + vis_err,
            invisible_lines=inv_out + inv_err,
        )


# ---------------------------------------------------------------------------
# Language-aware pattern detection
# ---------------------------------------------------------------------------

# Each entry: (name, compiled pattern on a single line, summary template).
_KNOWN_PATTERNS = [
    # pytest  "5 passed, 2 failed in 1.23s"
    ("pytest", re.compile(r"\d+ passed(?:,\s*\d+ \w+)*\s+in\s+[\d.]+s"), "pytest"),
    # jest  "Tests: 5 failed, 10 passed, 15 total"
    ("jest", re.compile(r"Tests:\s+\d+\s+\w+,\s+\d+\s+\w+"), "jest"),
    # go test  "ok  github.com/foo 0.123s"
    ("go-test", re.compile(r"^ok\s+\S+\s+[\d.]+s"), "go test"),
    # cargo  "test result: ok. 7 passed;"
    ("cargo-test", re.compile(r"test result:\s+(?:ok|FAILED)\.\s+\d+ passed"), "cargo test"),
    # make  "make[1]: Leaving directory"
    ("make", re.compile(r"make\[\d+\]:\s+(?:Leaving|Entering) directory"), "make build"),
    # git log  "commit <sha>"
    ("git-log", re.compile(r"^commit\s+[0-9a-f]{7,40}$"), "git log"),
    # npm/yarn  "found N vulnerabilities"
    ("npm-audit", re.compile(r"found\s+\d+\s+(?:low|moderate|high|critical)?\s*vulnerabilit"), "npm audit"),
]


def _detect_pattern(output: str) -> Optional[str]:
    """Return a short label if the output matches a known pattern family."""
    for line in output.splitlines()[:50]:  # scan first 50 lines only
        for name, pat, label in _KNOWN_PATTERNS:
            if pat.search(line):
                return label
    return None


# ---------------------------------------------------------------------------
# OutputSummarizer
# ---------------------------------------------------------------------------

class OutputSummarizer:
    """
    Condense large command output for display.

    If output fits in max_lines, it is returned as-is.
    Otherwise, the head and tail are kept and a "[... N lines truncated ...]"
    marker is inserted in the middle.

    Language-aware: for known output patterns (test results, git log, build
    output) the truncation marker includes a context hint.
    """

    def __init__(self, max_lines: int = 200) -> None:
        self.max_lines = max_lines

    def summarize(self, output: str, max_lines: Optional[int] = None) -> str:
        """
        Return output summarized to at most *max_lines* visible lines.

        Args:
            output:    Raw text output.
            max_lines: Override for self.max_lines.

        Returns:
            The original string if it fits, or a truncated version with a
            count marker.
        """
        limit = max_lines if max_lines is not None else self.max_lines
        if not output:
            return output

        lines = output.splitlines(keepends=True)
        total = len(lines)

        if total <= limit:
            return output

        omitted = total - limit
        head_count = limit // 2
        tail_count = limit - head_count

        head = lines[:head_count]
        tail = lines[-tail_count:]

        # Language-aware hint in the truncation marker.
        pattern_label = _detect_pattern(output)
        if pattern_label:
            marker = f"\n[... {omitted} lines truncated ({pattern_label} output) ...]\n"
        else:
            marker = f"\n[... {omitted} lines truncated ...]\n"

        return "".join(head) + marker + "".join(tail)


# ---------------------------------------------------------------------------
# TmuxCapture
# ---------------------------------------------------------------------------

class TmuxCapture:
    """
    Capture the visible contents of a tmux pane.

    Uses: tmux capture-pane -p -t {pane_id} -S -{tail_lines}
    """

    def capture_pane(
        self,
        pane_id: str,
        tail_lines: int = DEFAULT_TMUX_TAIL,
    ) -> str:
        """
        Capture the last *tail_lines* lines from the given pane.

        Args:
            pane_id:    tmux pane target (e.g. "main:0.1" or "%3").
            tail_lines: Number of history lines to include.  Clamped to
                        [MIN_TMUX_TAIL, MAX_TMUX_TAIL].

        Returns:
            Captured pane content as a string.

        Raises:
            SparkshellError: if tmux is not available or the capture fails.
        """
        if not pane_id or not pane_id.strip():
            raise SparkshellError.invalid_args("pane_id must not be empty")

        clamped = max(MIN_TMUX_TAIL, min(MAX_TMUX_TAIL, tail_lines))

        cmd = ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{clamped}"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
        except FileNotFoundError:
            raise SparkshellError.io_error(
                FileNotFoundError("tmux not found; is it installed and on PATH?")
            )
        except subprocess.TimeoutExpired as exc:
            raise SparkshellError.summary_timeout(10_000)
        except OSError as exc:
            raise SparkshellError.io_error(exc)

        if result.returncode != 0:
            err = result.stderr.strip() or "unknown error"
            raise SparkshellError.summary_bridge(
                f"tmux capture-pane failed (exit {result.returncode}): {err}"
            )

        return result.stdout
