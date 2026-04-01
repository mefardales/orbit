"""Orbit cleanup - removes stale state, orphan tmux sessions, and old run artifacts.

Supports --dry-run to preview what would be removed without deleting anything.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .constants import EXIT_ERROR, EXIT_OK

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_MAX_AGE_DAYS = 7
AUTORESEARCH_MAX_AGE_DAYS = 7
RALPH_MAX_AGE_DAYS = 7
TMUX_SESSION_PREFIX = "orbit-team-"

_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _c(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

ActionKind = Literal["removed_file", "removed_dir", "killed_session", "skipped"]


@dataclass
class CleanAction:
    kind: ActionKind
    path: str
    reason: str = ""


@dataclass
class CleanupReport:
    dry_run: bool
    actions: list[CleanAction] = field(default_factory=list)

    @property
    def removed_count(self) -> int:
        return sum(1 for a in self.actions if a.kind in ("removed_file", "removed_dir", "killed_session"))

    @property
    def skipped_count(self) -> int:
        return sum(1 for a in self.actions if a.kind == "skipped")

    def add(self, action: CleanAction) -> None:
        self.actions.append(action)

    def print_summary(self) -> None:
        prefix = _c("[DRY RUN] ", _YELLOW) if self.dry_run else ""
        print(f"\n{prefix}{_c('Orbit Cleanup', _BOLD)}\n")
        if not self.actions:
            print("  Nothing to clean.\n")
            return
        for a in self.actions:
            if a.kind == "skipped":
                continue
            verb = "Would remove" if self.dry_run else "Removed"
            if a.kind == "killed_session":
                verb = "Would kill" if self.dry_run else "Killed"
            print(f"  {_c(verb, _GREEN)}  {a.path}  {_c(a.reason, _DIM)}")
        print(
            f"\n  {self.removed_count} item(s) cleaned"
            + (", 0 written (dry run)" if self.dry_run else "")
            + f", {self.skipped_count} skipped.\n"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _orbit_dir() -> Path:
    return Path.home() / ".orbit"


def _cwd_omx_dir() -> Path:
    return Path.cwd() / ".omx"


def _age_days(path: Path) -> float:
    """Return age in days based on mtime."""
    try:
        mtime = path.stat().st_mtime
        now = datetime.now(timezone.utc).timestamp()
        return (now - mtime) / 86400
    except OSError:
        return 0.0


def _is_empty_dir(path: Path) -> bool:
    try:
        return path.is_dir() and not any(path.iterdir())
    except OSError:
        return False


def _remove(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Clean tasks
# ---------------------------------------------------------------------------

def _clean_stale_state_files(report: CleanupReport, dry_run: bool) -> None:
    """Remove state files older than STATE_MAX_AGE_DAYS."""
    state_dirs = [
        _orbit_dir() / "state",
        _cwd_omx_dir() / "state",
    ]
    for state_dir in state_dirs:
        if not state_dir.is_dir():
            continue
        for p in state_dir.rglob("*"):
            if not p.is_file():
                continue
            age = _age_days(p)
            if age > STATE_MAX_AGE_DAYS:
                reason = f"({int(age)}d old)"
                report.add(CleanAction(kind="removed_file", path=str(p), reason=reason))
                _remove(p, dry_run)


def _clean_orphan_tmux_sessions(report: CleanupReport, dry_run: bool) -> None:
    """Kill orphan tmux sessions matching orbit-team-* pattern."""
    if shutil.which("tmux") is None:
        return
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return
    except Exception:
        return

    sessions = [s.strip() for s in result.stdout.splitlines() if s.strip()]
    for session in sessions:
        if not session.startswith(TMUX_SESSION_PREFIX):
            continue
        report.add(CleanAction(kind="killed_session", path=session, reason="orphan orbit-team-* session"))
        if not dry_run:
            subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True, timeout=5)


def _clean_empty_worktrees(report: CleanupReport, dry_run: bool) -> None:
    """Remove empty worktree directories created by team mode."""
    worktrees_root = _cwd_omx_dir() / "worktrees"
    if not worktrees_root.is_dir():
        return
    for d in sorted(worktrees_root.iterdir()):
        if _is_empty_dir(d):
            report.add(CleanAction(kind="removed_dir", path=str(d), reason="empty worktree directory"))
            _remove(d, dry_run)


def _clean_autoresearch_runs(report: CleanupReport, dry_run: bool) -> None:
    """Remove old autoresearch run directories."""
    candidates = [
        _orbit_dir() / "autoresearch",
        _cwd_omx_dir() / "autoresearch",
    ]
    for base in candidates:
        if not base.is_dir():
            continue
        for run_dir in sorted(base.iterdir()):
            if not run_dir.is_dir():
                continue
            age = _age_days(run_dir)
            if age > AUTORESEARCH_MAX_AGE_DAYS:
                reason = f"({int(age)}d old)"
                report.add(CleanAction(kind="removed_dir", path=str(run_dir), reason=reason))
                _remove(run_dir, dry_run)


def _clean_ralph_sessions(report: CleanupReport, dry_run: bool) -> None:
    """Remove completed ralph session directories older than RALPH_MAX_AGE_DAYS."""
    candidates = [
        _orbit_dir() / "ralph",
        _cwd_omx_dir() / "ralph",
    ]
    for base in candidates:
        if not base.is_dir():
            continue
        for session_dir in sorted(base.iterdir()):
            if not session_dir.is_dir():
                continue
            # Check if this session has a 'completed' marker or is simply old
            completed_marker = session_dir / "completed"
            done_marker = session_dir / "done.json"
            is_complete = completed_marker.exists() or done_marker.exists()
            age = _age_days(session_dir)

            if is_complete or age > RALPH_MAX_AGE_DAYS:
                reason = "completed" if is_complete else f"({int(age)}d old)"
                report.add(CleanAction(kind="removed_dir", path=str(session_dir), reason=reason))
                _remove(session_dir, dry_run)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_cleanup(dry_run: bool = False) -> int:
    """Run all cleanup tasks.

    Args:
        dry_run: If True, report what would be removed but don't delete anything.

    Returns:
        EXIT_OK on success, EXIT_ERROR if any task raised an unhandled exception.
    """
    report = CleanupReport(dry_run=dry_run)

    tasks = [
        _clean_stale_state_files,
        _clean_orphan_tmux_sessions,
        _clean_empty_worktrees,
        _clean_autoresearch_runs,
        _clean_ralph_sessions,
    ]

    error_count = 0
    for task in tasks:
        try:
            task(report, dry_run)
        except Exception as exc:
            print(f"  {_c('[ERROR]', _RED)} {task.__name__}: {exc}", file=sys.stderr)
            error_count += 1

    report.print_summary()
    return EXIT_OK if error_count == 0 else EXIT_ERROR
