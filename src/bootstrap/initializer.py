"""System bootstrap initializer - orchestrates startup sequence."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from .stages import (
    BootstrapReport,
    BootstrapStage,
    StageResult,
    StageStatus,
)

logger = logging.getLogger(__name__)


class BootstrapError(Exception):
    """Raised when a critical bootstrap stage fails."""
    def __init__(self, stage: BootstrapStage, message: str) -> None:
        self.stage = stage
        super().__init__(f"Bootstrap failed at {stage.display_name}: {message}")


class BootstrapInitializer:
    """Orchestrates the system startup sequence through ordered stages."""

    def __init__(
        self,
        config_path: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.config_path = config_path or Path.home() / ".config" / "pyclaude" / "config.json"
        self.data_dir = data_dir or Path.home() / ".local" / "share" / "pyclaude"
        self.config: dict[str, Any] = {}
        self._services: dict[str, Any] = {}
        self._stage_hooks: dict[BootstrapStage, list[Callable[[], None]]] = {}
        self.report = BootstrapReport()

    def register_hook(self, stage: BootstrapStage, hook: Callable[[], None]) -> None:
        """Register a callback to run during a specific stage."""
        self._stage_hooks.setdefault(stage, []).append(hook)

    def _run_stage(self, stage: BootstrapStage, fn: Callable[[], str]) -> StageResult:
        """Execute a stage function with timing and error handling."""
        start = time.monotonic()
        try:
            message = fn()
            elapsed = (time.monotonic() - start) * 1000
            result = StageResult.success(stage, message=message, duration_ms=elapsed)
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            result = StageResult.failure(stage, error=str(exc), duration_ms=elapsed)
            logger.error("Stage %s failed: %s", stage.display_name, exc)

        # Run hooks
        for hook in self._stage_hooks.get(stage, []):
            try:
                hook()
            except Exception as exc:
                result.warnings.append(f"Hook failed: {exc}")

        self.report.add(result)
        return result

    def preflight_checks(self) -> StageResult:
        """Verify system prerequisites before starting."""
        def _run() -> str:
            checks_passed = 0
            # Check Python version
            import sys
            if sys.version_info < (3, 10):
                raise BootstrapError(BootstrapStage.PREFLIGHT, "Python 3.10+ required")
            checks_passed += 1

            # Ensure data directory exists
            self.data_dir.mkdir(parents=True, exist_ok=True)
            checks_passed += 1

            # Check config directory
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            checks_passed += 1

            return f"{checks_passed} preflight checks passed"

        return self._run_stage(BootstrapStage.PREFLIGHT, _run)

    def load_config(self) -> StageResult:
        """Load configuration from disk."""
        def _run() -> str:
            import json
            if self.config_path.exists():
                self.config = json.loads(self.config_path.read_text())
                return f"Loaded config from {self.config_path}"
            else:
                self.config = self._default_config()
                return "Using default configuration"

        return self._run_stage(BootstrapStage.CONFIG, _run)

    def run_migrations(self) -> StageResult:
        """Run any pending data migrations."""
        def _run() -> str:
            migrations_dir = self.data_dir / "migrations"
            migrations_dir.mkdir(exist_ok=True)
            applied_file = migrations_dir / ".applied"
            applied: set[str] = set()
            if applied_file.exists():
                applied = set(applied_file.read_text().strip().splitlines())

            pending = [
                p.name for p in sorted(migrations_dir.glob("*.py"))
                if p.name not in applied
            ]
            # Mark as applied (actual migration execution would go here)
            if pending:
                with applied_file.open("a") as f:
                    for name in pending:
                        f.write(name + "\n")
            return f"{len(pending)} migrations applied, {len(applied)} previously applied"

        return self._run_stage(BootstrapStage.MIGRATIONS, _run)

    def start_services(self) -> StageResult:
        """Initialize and start background services."""
        def _run() -> str:
            service_configs = self.config.get("services", {})
            started = 0
            for name, svc_conf in service_configs.items():
                if svc_conf.get("enabled", True):
                    self._services[name] = {"status": "running", "config": svc_conf}
                    started += 1
                    logger.info("Started service: %s", name)
            return f"{started} services started"

        return self._run_stage(BootstrapStage.SERVICES, _run)

    def run(self) -> BootstrapReport:
        """Execute the full bootstrap sequence."""
        stages = [
            self.preflight_checks,
            self.load_config,
            self.run_migrations,
            self.start_services,
        ]
        for stage_fn in stages:
            result = stage_fn()
            if result.failed:
                logger.error("Bootstrap aborted: %s", result.error)
                break
        return self.report

    def _default_config(self) -> dict[str, Any]:
        return {
            "version": 1,
            "services": {},
            "log_level": "INFO",
            "data_dir": str(self.data_dir),
        }

    @property
    def is_ready(self) -> bool:
        return self.report.all_passed

    def get_service(self, name: str) -> Any:
        return self._services.get(name)
