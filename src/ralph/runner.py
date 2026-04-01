"""
RalphRunner: Persistence-loop execution engine for Ralph mode.

Manages the full lifecycle of a Ralph session: plan → execute → verify → complete.
State is persisted in .orbit/ralph/ so sessions survive process restarts.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .contract import (
    RALPH_PHASES,
    RALPH_TERMINAL_PHASES,
    RalphPhase,
    normalize_ralph_phase,
    validate_and_normalize_ralph_state,
)
from .persistence import (
    RalphCanonicalArtifacts,
    ensure_canonical_ralph_artifacts,
)

# ---------------------------------------------------------------------------
# Phase ordering — determines what "next phase" means and gate enforcement.
# ---------------------------------------------------------------------------

_PHASE_ORDER: list[RalphPhase] = [
    "starting",
    "executing",
    "verifying",
    "fixing",
    "complete",
]

_PHASE_INDEX: dict[str, int] = {p: i for i, p in enumerate(_PHASE_ORDER)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# On-disk state schema
# ---------------------------------------------------------------------------


@dataclass
class RalphSessionState:
    """Full state of a Ralph session, persisted as JSON."""

    schema_version: int = 1
    session_id: str = ""
    active: bool = False
    current_phase: RalphPhase = "starting"
    iteration: int = 0
    max_iterations: int = 50
    prompt: str = ""
    prd_path: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    changed_files: list[str] = field(default_factory=list)
    phase_history: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _state_to_dict(state: RalphSessionState) -> dict[str, Any]:
    return asdict(state)


def _state_from_dict(data: dict[str, Any]) -> RalphSessionState:
    allowed = set(RalphSessionState.__dataclass_fields__)
    filtered = {k: v for k, v in data.items() if k in allowed}
    return RalphSessionState(**filtered)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _ralph_dir(cwd: str) -> Path:
    return Path(cwd) / ".orbit" / "ralph"


def _state_path(cwd: str) -> Path:
    return _ralph_dir(cwd) / "state.json"


def _progress_path(cwd: str) -> Path:
    return _ralph_dir(cwd) / "progress.txt"


def _changed_files_path(cwd: str) -> Path:
    return _ralph_dir(cwd) / "changed-files.txt"


def _prd_path(cwd: str, session_id: str) -> Path:
    return Path(cwd) / ".orbit" / "plans" / f"prd-{session_id}.md"


def _ensure_ralph_dirs(cwd: str) -> None:
    _ralph_dir(cwd).mkdir(parents=True, exist_ok=True)
    (Path(cwd) / ".orbit" / "plans").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# State I/O
# ---------------------------------------------------------------------------


def _write_state(cwd: str, state: RalphSessionState) -> None:
    state.updated_at = _now_iso()
    _ensure_ralph_dirs(cwd)
    _state_path(cwd).write_text(_stable_json(_state_to_dict(state)) + "\n", encoding="utf-8")


def _read_state(cwd: str) -> Optional[RalphSessionState]:
    path = _state_path(cwd)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _state_from_dict(data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Progress & changed-files I/O
# ---------------------------------------------------------------------------


def _append_progress(cwd: str, line: str) -> None:
    path = _progress_path(cwd)
    _ensure_ralph_dirs(cwd)
    timestamp = _now_iso()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {line}\n")


def _write_changed_files(cwd: str, files: list[str]) -> None:
    _ensure_ralph_dirs(cwd)
    _changed_files_path(cwd).write_text("\n".join(files) + ("\n" if files else ""), encoding="utf-8")


def _read_changed_files(cwd: str) -> list[str]:
    path = _changed_files_path(cwd)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_changed_files(cwd: str) -> list[str]:
    """Return files changed since HEAD (staged + unstaged + untracked)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        lines = []
        for line in result.stdout.splitlines():
            line = line.rstrip()
            if len(line) >= 4:
                lines.append(line[3:].strip())
        return lines
    except (subprocess.SubprocessError, OSError):
        return []


def _git_head_short(cwd: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None
    except (subprocess.SubprocessError, OSError):
        return None


# ---------------------------------------------------------------------------
# PRD I/O
# ---------------------------------------------------------------------------


def _write_prd(cwd: str, session_id: str, prompt: str, state: RalphSessionState) -> str:
    """Write a PRD markdown file and return its path."""
    path = _prd_path(cwd, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    content_lines = [
        f"# Ralph PRD: {session_id}",
        "",
        f"> Generated at: {now}",
        "",
        "## Prompt",
        "",
        prompt,
        "",
        "## Session Metadata",
        "",
        f"- Session ID: `{session_id}`",
        f"- Started: `{state.started_at}`",
        f"- Max iterations: {state.max_iterations}",
        "",
        "## Phase Plan",
        "",
        "1. **starting** — Analyse prompt, plan work, create this PRD.",
        "2. **executing** — Implement changes according to the plan.",
        "3. **verifying** — Run tests/checks, capture results.",
        "4. **fixing** — Address failures discovered during verification.",
        "5. **complete** — Session finished successfully.",
        "",
    ]
    path.write_text("\n".join(content_lines), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Phase gate
# ---------------------------------------------------------------------------


def _assert_phase_reachable(current: RalphPhase, target: RalphPhase) -> None:
    """Raise ValueError if jumping to *target* would skip a mandatory phase."""
    if current in RALPH_TERMINAL_PHASES:
        raise ValueError(
            f"Cannot advance phase: session is already in terminal phase '{current}'."
        )
    curr_idx = _PHASE_INDEX.get(current, -1)
    tgt_idx = _PHASE_INDEX.get(target, -1)
    if tgt_idx < 0:
        # Terminal phases (failed, cancelled) are always reachable.
        return
    if tgt_idx < curr_idx:
        raise ValueError(
            f"Cannot move backwards from '{current}' to '{target}'. "
            "Ralph phases are strictly ordered."
        )
    if tgt_idx > curr_idx + 1:
        skipped = _PHASE_ORDER[curr_idx + 1 : tgt_idx]
        raise ValueError(
            f"Cannot skip phases {skipped!r} when advancing from '{current}' to '{target}'."
        )


# ---------------------------------------------------------------------------
# Public status dataclass
# ---------------------------------------------------------------------------


@dataclass
class RalphStatus:
    """Snapshot returned by RalphRunner.get_status()."""

    session_id: str
    active: bool
    current_phase: RalphPhase
    iteration: int
    max_iterations: int
    changed_files: list[str]
    prd_path: Optional[str]
    started_at: Optional[str]
    updated_at: Optional[str]
    completed_at: Optional[str]
    notes: list[str]


# ---------------------------------------------------------------------------
# RalphRunner
# ---------------------------------------------------------------------------


class RalphRunner:
    """
    Manages a persistent Ralph execution session.

    All state is stored under ``<cwd>/.orbit/ralph/`` so the session survives
    process restarts and can be resumed at any point.

    Phase lifecycle (strictly ordered, no skipping):
        starting → executing → verifying → fixing → complete

    Terminal phases (no further advancement):
        complete | failed | cancelled
    """

    def __init__(self, cwd: str) -> None:
        """
        Args:
            cwd: Working directory root. Must contain (or will contain) a ``.orbit/`` directory.
        """
        self._cwd = str(Path(cwd).resolve())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, prompt: str, *, max_iterations: int = 50) -> RalphStatus:
        """
        Begin a new Ralph session.

        Creates .orbit/ralph/state.json, writes a PRD, and sets phase to
        'starting'. Raises RuntimeError if a non-terminal session already exists.

        Args:
            prompt: The goal / task description for this Ralph session.
            max_iterations: Hard cap on iteration count (default 50).

        Returns:
            RalphStatus snapshot after initialisation.
        """
        existing = _read_state(self._cwd)
        if existing and existing.active:
            raise RuntimeError(
                f"ralph_session_already_active:{existing.session_id} "
                f"(phase={existing.current_phase}). Call resume() or complete() first."
            )

        now = _now_iso()
        session_id = self._build_session_id(now)
        state = RalphSessionState(
            session_id=session_id,
            active=True,
            current_phase="starting",
            iteration=0,
            max_iterations=max_iterations,
            prompt=prompt,
            started_at=now,
            updated_at=now,
        )

        # Ensure canonical artifacts exist (migrates legacy files if present).
        ensure_canonical_ralph_artifacts(self._cwd, session_id)

        # Write PRD.
        prd_path = _write_prd(self._cwd, session_id, prompt, state)
        state.prd_path = prd_path

        # Snapshot changed files at start.
        changed = _git_changed_files(self._cwd)
        state.changed_files = changed
        _write_changed_files(self._cwd, changed)

        state.phase_history.append({"phase": "starting", "entered_at": now})
        _write_state(self._cwd, state)
        _append_progress(self._cwd, f"SESSION START  session={session_id}  phase=starting")

        return self._status_from_state(state)

    def resume(self) -> RalphStatus:
        """
        Resume the most recent Ralph session from its last checkpoint.

        Raises RuntimeError if no persisted session exists or if the session
        has already reached a terminal phase.

        Returns:
            RalphStatus snapshot of the resumed session.
        """
        state = _read_state(self._cwd)
        if state is None:
            raise RuntimeError(
                "ralph_no_session_found: no .orbit/ralph/state.json exists. "
                "Call start() to begin a new session."
            )
        if state.current_phase in RALPH_TERMINAL_PHASES:
            raise RuntimeError(
                f"ralph_session_terminal:{state.session_id} "
                f"(phase={state.current_phase}). Start a new session."
            )

        state.active = True
        _write_state(self._cwd, state)
        _append_progress(
            self._cwd,
            f"SESSION RESUME  session={state.session_id}  phase={state.current_phase}  "
            f"iteration={state.iteration}",
        )
        return self._status_from_state(state)

    def advance_phase(self, target_phase: str) -> RalphStatus:
        """
        Advance the session to *target_phase*.

        Enforces strict phase ordering — phases cannot be skipped and the session
        cannot move backwards. Terminal phases (complete, failed, cancelled) can
        only be reached via complete() / fail() / cancel().

        Args:
            target_phase: One of the RALPH_PHASES strings.

        Returns:
            RalphStatus after the transition.
        """
        state = self._require_active_state()
        result = normalize_ralph_phase(target_phase)
        if result.error:
            raise ValueError(result.error)
        new_phase: RalphPhase = result.phase  # type: ignore[assignment]

        _assert_phase_reachable(state.current_phase, new_phase)

        now = _now_iso()
        state.current_phase = new_phase
        state.phase_history.append({"phase": new_phase, "entered_at": now})
        state.iteration += 1

        # Refresh changed files on every phase advance.
        changed = _git_changed_files(self._cwd)
        state.changed_files = list(set(state.changed_files) | set(changed))
        _write_changed_files(self._cwd, state.changed_files)

        if new_phase in RALPH_TERMINAL_PHASES:
            state.active = False
            state.completed_at = now

        _write_state(self._cwd, state)
        _append_progress(
            self._cwd,
            f"PHASE ADVANCE  session={state.session_id}  "
            f"phase={new_phase}  iteration={state.iteration}",
        )
        return self._status_from_state(state)

    def record_changed_files(self, files: Optional[list[str]] = None) -> list[str]:
        """
        Refresh the changed-files ledger.

        If *files* is None, re-queries git status. Otherwise uses the provided
        list. Merges with any previously recorded files.

        Returns:
            Deduplicated list of all changed files seen so far.
        """
        state = self._require_active_state()
        new_files = files if files is not None else _git_changed_files(self._cwd)
        state.changed_files = sorted(set(state.changed_files) | set(new_files))
        _write_changed_files(self._cwd, state.changed_files)
        _write_state(self._cwd, state)
        return state.changed_files

    def add_note(self, note: str) -> None:
        """Append a free-form note to the session state."""
        state = self._require_active_state()
        state.notes.append(f"[{_now_iso()}] {note}")
        _write_state(self._cwd, state)
        _append_progress(self._cwd, f"NOTE  {note}")

    def get_status(self) -> RalphStatus:
        """
        Return the current session status without mutating state.

        Returns:
            RalphStatus with current phase, iteration, changed files, etc.

        Raises:
            RuntimeError if no session exists.
        """
        state = _read_state(self._cwd)
        if state is None:
            raise RuntimeError(
                "ralph_no_session_found: no state.json present under .orbit/ralph/."
            )
        # Refresh changed files from disk each time.
        state.changed_files = _read_changed_files(self._cwd)
        return self._status_from_state(state)

    def complete(self) -> RalphStatus:
        """
        Mark the session as complete.

        Transitions to the 'complete' terminal phase regardless of the current
        phase — this is a forced finalisation. Sets active=False.

        Returns:
            Final RalphStatus.
        """
        state = self._require_active_state()
        now = _now_iso()
        state.current_phase = "complete"
        state.active = False
        state.completed_at = now
        state.phase_history.append({"phase": "complete", "entered_at": now})

        # Final changed-files snapshot.
        changed = _git_changed_files(self._cwd)
        state.changed_files = sorted(set(state.changed_files) | set(changed))
        _write_changed_files(self._cwd, state.changed_files)
        _write_state(self._cwd, state)
        _append_progress(
            self._cwd,
            f"SESSION COMPLETE  session={state.session_id}  "
            f"total_iterations={state.iteration}  "
            f"changed_files={len(state.changed_files)}",
        )
        return self._status_from_state(state)

    def fail(self, reason: str = "") -> RalphStatus:
        """
        Mark the session as failed.

        Args:
            reason: Short human-readable reason for the failure.

        Returns:
            Final RalphStatus.
        """
        state = _read_state(self._cwd)
        if state is None:
            raise RuntimeError("ralph_no_session_found")
        now = _now_iso()
        state.current_phase = "failed"
        state.active = False
        state.completed_at = now
        if reason:
            state.notes.append(f"[{now}] FAILED: {reason}")
        state.phase_history.append({"phase": "failed", "entered_at": now, "reason": reason})
        _write_state(self._cwd, state)
        _append_progress(self._cwd, f"SESSION FAILED  session={state.session_id}  reason={reason!r}")
        return self._status_from_state(state)

    def cancel(self, reason: str = "") -> RalphStatus:
        """
        Cancel the session.

        Args:
            reason: Optional cancellation reason.

        Returns:
            Final RalphStatus.
        """
        state = _read_state(self._cwd)
        if state is None:
            raise RuntimeError("ralph_no_session_found")
        now = _now_iso()
        state.current_phase = "cancelled"
        state.active = False
        state.completed_at = now
        if reason:
            state.notes.append(f"[{now}] CANCELLED: {reason}")
        state.phase_history.append({"phase": "cancelled", "entered_at": now, "reason": reason})
        _write_state(self._cwd, state)
        _append_progress(self._cwd, f"SESSION CANCELLED  session={state.session_id}  reason={reason!r}")
        return self._status_from_state(state)

    def update_prd(self, content: str) -> str:
        """
        Overwrite the PRD file with *content*.

        Args:
            content: Full markdown content of the new PRD.

        Returns:
            Absolute path to the PRD file.
        """
        state = self._require_active_state()
        prd = _prd_path(self._cwd, state.session_id)
        prd.parent.mkdir(parents=True, exist_ok=True)
        prd.write_text(content, encoding="utf-8")
        state.prd_path = str(prd)
        _write_state(self._cwd, state)
        _append_progress(self._cwd, f"PRD UPDATED  path={prd}")
        return str(prd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_active_state(self) -> RalphSessionState:
        state = _read_state(self._cwd)
        if state is None:
            raise RuntimeError(
                "ralph_no_session_found: call start() before performing session operations."
            )
        if not state.active:
            raise RuntimeError(
                f"ralph_session_inactive:{state.session_id} "
                f"(phase={state.current_phase}). The session is not active."
            )
        return state

    @staticmethod
    def _build_session_id(now_iso: str) -> str:
        # e.g. "ralph-20260401t123456z"
        compact = now_iso[:19].replace("-", "").replace(":", "").replace("T", "t") + "z"
        return f"ralph-{compact}"

    @staticmethod
    def _status_from_state(state: RalphSessionState) -> RalphStatus:
        return RalphStatus(
            session_id=state.session_id,
            active=state.active,
            current_phase=state.current_phase,
            iteration=state.iteration,
            max_iterations=state.max_iterations,
            changed_files=list(state.changed_files),
            prd_path=state.prd_path,
            started_at=state.started_at,
            updated_at=state.updated_at,
            completed_at=state.completed_at,
            notes=list(state.notes),
        )
