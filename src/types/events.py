"""Event dataclasses representing things that happen during a session."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Event:
    """Base event emitted during a pyclaude session."""

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "metadata": self.metadata,
        }


@dataclass
class CommandEvent(Event):
    """A user or system command was issued."""

    command: str = ""
    args: list[str] = field(default_factory=list)
    raw_input: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(command=self.command, args=self.args, raw_input=self.raw_input)
        return d


@dataclass
class ToolEvent(Event):
    """A tool invocation started, completed, or failed."""

    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_output: Optional[Any] = None
    duration_ms: Optional[float] = None
    status: str = "pending"  # pending | running | success | error

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            tool_name=self.tool_name,
            tool_input=self.tool_input,
            tool_output=self.tool_output,
            duration_ms=self.duration_ms,
            status=self.status,
        )
        return d


@dataclass
class ErrorEvent(Event):
    """An error occurred during execution."""

    error_type: str = ""
    message: str = ""
    traceback: Optional[str] = None
    recoverable: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            error_type=self.error_type,
            message=self.message,
            traceback=self.traceback,
            recoverable=self.recoverable,
        )
        return d
