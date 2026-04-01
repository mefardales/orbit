"""Type definitions for the multi-stage execution pipeline."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class StageStatus(enum.Enum):
    """Execution status of a pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class PipelineStage:
    """A single stage in the execution pipeline."""

    name: str
    handler: Callable[..., Any]
    depends_on: List[str] = field(default_factory=list)
    timeout: float = 60.0
    max_retries: int = 1
    retry_delay: float = 1.0
    allow_failure: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError(f"Stage timeout must be positive, got {self.timeout}")
        if self.max_retries < 1:
            raise ValueError(f"max_retries must be >= 1, got {self.max_retries}")


@dataclass
class PipelineResult:
    """Result from executing a single pipeline stage."""

    stage_name: str
    status: StageStatus
    output: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    attempts: int = 1
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    @property
    def succeeded(self) -> bool:
        return self.status == StageStatus.SUCCESS

    def finalize(self, status: StageStatus, output: Any = None, error: Optional[str] = None) -> None:
        self.status = status
        self.output = output
        self.error = error
        self.finished_at = time.time()
        self.duration = self.finished_at - self.started_at


@dataclass
class PipelineConfig:
    """Configuration for a pipeline run."""

    name: str = "default"
    fail_fast: bool = True
    max_parallel: int = 1
    global_timeout: float = 300.0
    on_stage_complete: Optional[Callable[[PipelineResult], None]] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.global_timeout <= 0:
            raise ValueError("global_timeout must be positive")
        if self.max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")
