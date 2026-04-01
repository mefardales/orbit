"""
Ultraqa mode: quality assurance with verification checks.

Runs a series of QA checks, tracks pass/fail per check, and requires a
configurable pass threshold before declaring the session complete.
Not exclusive by default — can run alongside planning modes.
State is persisted to .orbit/state/ultraqa-state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .manager import ModeManager, ModeStatus, get_mode_manager

logger = logging.getLogger("orbit.modes.ultraqa")

_STATE_FILE = Path(".orbit") / "state" / "ultraqa-state.json"
_MODE_NAME = "ultraqa"


@dataclass
class QACheck:
    """A single quality assurance check definition."""

    name: str
    description: str = ""
    required: bool = True
    fn: Optional[Callable[[], bool]] = field(default=None, repr=False)


@dataclass
class QACheckResult:
    """Result of running a single QA check."""

    name: str
    passed: bool
    required: bool
    error: Optional[str] = None
    duration: float = 0.0


@dataclass
class UltraqaConfig:
    """Configuration for an ultraqa session."""

    title: str
    checks: List[QACheck] = field(default_factory=list)
    pass_threshold: float = 1.0  # fraction of required checks that must pass (0..1)
    metadata: Dict[str, Any] = field(default_factory=dict)


class UltraqaMode:
    """Quality assurance mode with structured verification checks.

    Runs each registered check, tracks pass/fail status, and determines
    overall QA outcome based on the pass_threshold.
    """

    is_exclusive: bool = False

    def __init__(self, manager: Optional[ModeManager] = None) -> None:
        self._manager = manager or get_mode_manager()
        self._config: Optional[UltraqaConfig] = None
        self._results: List[QACheckResult] = []

    def activate(self, config: UltraqaConfig) -> ModeStatus:
        """Start ultraqa mode."""
        self._config = config
        self._results = []

        status = self._manager.activate_mode(
            _MODE_NAME,
            config={
                "title": config.title,
                "check_count": len(config.checks),
                "pass_threshold": config.pass_threshold,
                "phase": "checking",
                "iteration": 0,
            },
        )
        self._flush_state()
        logger.info("Ultraqa activated: %r (%d checks)", config.title, len(config.checks))
        return status

    def deactivate(self) -> Optional[ModeStatus]:
        """End ultraqa mode."""
        self._flush_state()
        return self._manager.deactivate_mode(_MODE_NAME)

    def get_status(self) -> Optional[ModeStatus]:
        return self._manager.get_mode_status(_MODE_NAME)

    # ── Check execution ────────────────────────────────────────────────────

    def run_check(self, check: QACheck) -> QACheckResult:
        """Execute a single QA check and record the result.

        If check.fn is None, the check is skipped and counted as passed.
        """
        start = time.monotonic()
        if check.fn is None:
            result = QACheckResult(
                name=check.name,
                passed=True,
                required=check.required,
                duration=0.0,
            )
        else:
            try:
                passed = bool(check.fn())
                result = QACheckResult(
                    name=check.name,
                    passed=passed,
                    required=check.required,
                    duration=time.monotonic() - start,
                )
            except Exception as exc:  # noqa: BLE001
                result = QACheckResult(
                    name=check.name,
                    passed=False,
                    required=check.required,
                    error=str(exc),
                    duration=time.monotonic() - start,
                )

        self._results.append(result)
        self._manager.advance_phase(
            _MODE_NAME,
            "checking",
            iteration=len(self._results),
        )
        self._flush_state()
        return result

    def run_all(self, config: UltraqaConfig) -> Dict[str, Any]:
        """Activate, run all checks, and return the QA report.

        Returns a dict with keys: passed, failed, skipped, overall_pass,
        results (list), and pass_rate.
        """
        self.activate(config)
        try:
            for check in config.checks:
                self.run_check(check)
        finally:
            self.deactivate()

        return self.report()

    def report(self) -> Dict[str, Any]:
        """Return a summary of check results."""
        required = [r for r in self._results if r.required]
        passed_required = [r for r in required if r.passed]
        pass_rate = len(passed_required) / len(required) if required else 1.0
        threshold = self._config.pass_threshold if self._config else 1.0
        overall = pass_rate >= threshold

        return {
            "title": self._config.title if self._config else "",
            "overall_pass": overall,
            "pass_rate": round(pass_rate, 4),
            "pass_threshold": threshold,
            "total": len(self._results),
            "passed": sum(1 for r in self._results if r.passed),
            "failed": sum(1 for r in self._results if not r.passed),
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "required": r.required,
                    "error": r.error,
                    "duration": round(r.duration, 3),
                }
                for r in self._results
            ],
        }

    # ── State persistence ──────────────────────────────────────────────────

    def _flush_state(self) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        total = len(self._config.checks) if self._config else 0
        passed = sum(1 for r in self._results if r.passed)
        failed = len(self._results) - passed
        payload: Dict[str, Any] = {
            "mode": _MODE_NAME,
            "phase": "checking" if len(self._results) < total else "complete",
            "checked": len(self._results),
            "total": total,
            "passed": passed,
            "failed": failed,
            "timestamp": time.time(),
        }
        if self._config:
            payload["title"] = self._config.title
        _STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
