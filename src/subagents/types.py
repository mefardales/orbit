"""Types for the subagent tracking subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SubagentStatus(Enum):
    """Lifecycle states a subagent can be in."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (
            SubagentStatus.COMPLETED,
            SubagentStatus.FAILED,
            SubagentStatus.CANCELLED,
        )

    @property
    def is_active(self) -> bool:
        return self in (SubagentStatus.INITIALIZING, SubagentStatus.RUNNING, SubagentStatus.PAUSED)


@dataclass
class TrackedSubagent:
    """Represents a subagent being tracked by the system."""

    agent_id: str
    role: str = "executor"
    parent_id: Optional[str] = None
    status: SubagentStatus = SubagentStatus.INITIALIZING
    task_description: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    tool_calls: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return round(end - self.started_at, 3)

    @property
    def is_active(self) -> bool:
        return self.status.is_active

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "parent_id": self.parent_id,
            "status": self.status.value,
            "task_description": self.task_description,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tool_calls": self.tool_calls,
            "tokens_used": self.tokens_used,
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
        }
