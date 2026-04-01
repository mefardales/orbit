"""Bootstrap stage definitions and result tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class BootstrapStage(Enum):
    """Ordered stages of system bootstrap."""
    PREFLIGHT = auto()
    CONFIG = auto()
    MIGRATIONS = auto()
    SERVICES = auto()
    PLUGINS = auto()
    READY = auto()

    @property
    def display_name(self) -> str:
        return self.name.replace("_", " ").title()

    def next_stage(self) -> BootstrapStage | None:
        members = list(BootstrapStage)
        idx = members.index(self)
        if idx + 1 < len(members):
            return members[idx + 1]
        return None


class StageStatus(Enum):
    """Status of a bootstrap stage."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result of executing a single bootstrap stage."""
    stage: BootstrapStage
    status: StageStatus
    duration_ms: float = 0.0
    message: str = ""
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == StageStatus.COMPLETED

    @property
    def failed(self) -> bool:
        return self.status == StageStatus.FAILED

    @classmethod
    def success(cls, stage: BootstrapStage, message: str = "", **kwargs: Any) -> StageResult:
        return cls(stage=stage, status=StageStatus.COMPLETED, message=message, **kwargs)

    @classmethod
    def failure(cls, stage: BootstrapStage, error: str, **kwargs: Any) -> StageResult:
        return cls(stage=stage, status=StageStatus.FAILED, error=error, **kwargs)

    @classmethod
    def skipped(cls, stage: BootstrapStage, reason: str = "") -> StageResult:
        return cls(stage=stage, status=StageStatus.SKIPPED, message=reason)


@dataclass
class BootstrapReport:
    """Aggregated report of all bootstrap stage results."""
    results: list[StageResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def all_passed(self) -> bool:
        return all(r.succeeded or r.status == StageStatus.SKIPPED for r in self.results)

    @property
    def failed_stages(self) -> list[StageResult]:
        return [r for r in self.results if r.failed]

    @property
    def warnings(self) -> list[str]:
        out: list[str] = []
        for r in self.results:
            out.extend(r.warnings)
        return out

    def add(self, result: StageResult) -> None:
        self.results.append(result)
        self.total_duration_ms += result.duration_ms

    def summary(self) -> str:
        lines = [f"Bootstrap completed in {self.total_duration_ms:.1f}ms"]
        for r in self.results:
            icon = "ok" if r.succeeded else ("FAIL" if r.failed else "skip")
            lines.append(f"  [{icon}] {r.stage.display_name}: {r.message or r.error or ''}")
        return "\n".join(lines)
