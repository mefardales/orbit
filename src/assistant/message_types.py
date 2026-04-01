"""Message types and data structures for the assistant subsystem."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageRole(Enum):
    """Role of a message participant."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ToolCallStatus(Enum):
    """Status of a tool call execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ToolCall:
    """Represents a single tool invocation requested by the assistant."""
    tool_name: str
    arguments: dict[str, Any]
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def mark_running(self) -> None:
        self.status = ToolCallStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, result: Any) -> None:
        self.status = ToolCallStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        self.status = ToolCallStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    @property
    def duration_ms(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None


@dataclass
class AssistantMessage:
    """A message in an assistant conversation."""
    role: MessageRole
    content: str
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: list[ToolCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def pending_tool_calls(self) -> list[ToolCall]:
        return [tc for tc in self.tool_calls if tc.status == ToolCallStatus.PENDING]

    @property
    def all_tools_resolved(self) -> bool:
        return all(
            tc.status in (ToolCallStatus.COMPLETED, ToolCallStatus.FAILED, ToolCallStatus.CANCELLED)
            for tc in self.tool_calls
        )

    def add_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
        tc = ToolCall(tool_name=tool_name, arguments=arguments)
        self.tool_calls.append(tc)
        return tc


@dataclass
class ConversationTurn:
    """A pair of user message and assistant response."""
    user_message: AssistantMessage
    assistant_message: AssistantMessage | None = None
    turn_number: int = 0

    @property
    def is_complete(self) -> bool:
        return self.assistant_message is not None and (
            not self.assistant_message.has_tool_calls
            or self.assistant_message.all_tools_resolved
        )
