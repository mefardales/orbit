"""
Deep interview mode: guided parameter collection.

Interactively prompts the user for required parameters before handing off
to a downstream task. Not exclusive — it can run alongside non-exclusive modes.
State is persisted to .orbit/state/deep-interview-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager

logger = logging.getLogger("orbit.modes.deep_interview")

_STATE_FILE = Path(".orbit") / "state" / "deep-interview-state.json"
_MODE_NAME = "deep-interview"


@dataclass
class InterviewQuestion:
    """A single parameter question in the interview."""

    key: str
    prompt: str
    required: bool = True
    default: Optional[str] = None
    validator: Optional[Callable[[str], bool]] = field(default=None, repr=False)


@dataclass
class InterviewConfig:
    """Configuration for a deep interview session."""

    title: str
    questions: List[InterviewQuestion] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InterviewResult:
    """Collected answers from the interview."""

    completed: bool
    answers: Dict[str, str] = field(default_factory=dict)
    skipped: List[str] = field(default_factory=list)


class DeepInterviewMode:
    """Collects structured parameters via a series of guided prompts.

    This mode is NOT exclusive — it may run alongside other non-exclusive modes.
    """

    is_exclusive: bool = False

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._config: Optional[InterviewConfig] = None
        self._answers: Dict[str, str] = {}
        self._current_q_index: int = 0

    def activate(self, config: InterviewConfig) -> ModeStatus:
        """Start the interview session."""
        self._config = config
        self._answers = {}
        self._current_q_index = 0

        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "title": config.title,
                "question_count": len(config.questions),
                "phase": "questioning",
                "iteration": 0,
            },
        )
        self._flush_state()
        logger.info("Deep interview started: %r (%d questions)", config.title, len(config.questions))
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """End the interview session."""
        self._flush_state()
        return self._manager.deactivate_mode(_MODE_NAME)

    def get_status(self) -> Optional[ModeStatus]:
        return self._manager.get_mode_status(_MODE_NAME)

    # ── Interview loop ─────────────────────────────────────────────────────

    def current_question(self) -> Optional[InterviewQuestion]:
        """Return the next unanswered question, or None if the interview is done."""
        if self._config is None:
            return None
        if self._current_q_index >= len(self._config.questions):
            return None
        return self._config.questions[self._current_q_index]

    def answer(self, value: str) -> bool:
        """Provide an answer for the current question.

        Returns True if the answer was accepted (validation passed or no
        validator); False if validation failed (question remains current).
        """
        q = self.current_question()
        if q is None:
            return False

        if q.validator and not q.validator(value):
            logger.debug("Validation failed for key=%r value=%r", q.key, value)
            return False

        effective_value = value if value.strip() else (q.default or "")
        self._answers[q.key] = effective_value
        self._current_q_index += 1

        self._manager.advance_phase(
            _MODE_NAME,
            "questioning",
            iteration=self._current_q_index,
        )
        self._flush_state()
        return True

    def skip(self) -> None:
        """Skip the current question (only allowed for non-required questions)."""
        q = self.current_question()
        if q is None:
            return
        if q.required:
            logger.warning("Cannot skip required question: %r", q.key)
            return
        if q.default is not None:
            self._answers[q.key] = q.default
        self._current_q_index += 1
        self._flush_state()

    def run(
        self,
        config: InterviewConfig,
        ask_fn: Callable[[InterviewQuestion], str],
    ) -> InterviewResult:
        """Run the full interview using *ask_fn* to obtain each answer.

        Args:
            config: Interview configuration.
            ask_fn: Callable(question) → str. Called for each question.

        Returns:
            InterviewResult with all collected answers.
        """
        self.activate(config)
        skipped: List[str] = []

        try:
            while True:
                q = self.current_question()
                if q is None:
                    break
                raw = ask_fn(q)
                if not self.answer(raw):
                    # Re-ask on validation failure (max 3 attempts)
                    for _ in range(2):
                        raw = ask_fn(q)
                        if self.answer(raw):
                            break
                    else:
                        if not q.required:
                            self.skip()
                            skipped.append(q.key)
                        else:
                            logger.warning("Required question %r could not be answered", q.key)
        finally:
            self.deactivate()

        return InterviewResult(
            completed=self._current_q_index >= len(config.questions),
            answers=dict(self._answers),
            skipped=skipped,
        )

    # ── State persistence ──────────────────────────────────────────────────

    def _flush_state(self) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        total = len(self._config.questions) if self._config else 0
        payload: Dict[str, Any] = {
            "mode": _MODE_NAME,
            "title": self._config.title if self._config else "",
            "answered": self._current_q_index,
            "total": total,
            "phase": "questioning" if self._current_q_index < total else "complete",
            "timestamp": time.time(),
        }
        _STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
