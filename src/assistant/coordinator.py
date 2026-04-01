"""Assistant coordinator - routes messages, handles tool calls, manages context."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .message_types import (
    AssistantMessage,
    ConversationTurn,
    MessageRole,
    ToolCall,
    ToolCallStatus,
)

logger = logging.getLogger(__name__)


class ToolHandler(Protocol):
    """Protocol for objects that can execute tool calls."""

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass
class ContextWindow:
    """Manages the sliding context window for conversations."""
    max_turns: int = 50
    max_tokens_estimate: int = 100_000
    turns: deque[ConversationTurn] = field(default_factory=deque)
    system_prompt: str = ""

    @property
    def current_turn_count(self) -> int:
        return len(self.turns)

    def add_turn(self, turn: ConversationTurn) -> None:
        self.turns.append(turn)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        while len(self.turns) > self.max_turns:
            self.turns.popleft()

    def to_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        for turn in self.turns:
            messages.append({"role": turn.user_message.role.value, "content": turn.user_message.content})
            if turn.assistant_message:
                messages.append({"role": "assistant", "content": turn.assistant_message.content})
        return messages

    def clear(self) -> None:
        self.turns.clear()

    def summarize_old_turns(self, keep_recent: int = 10) -> str:
        """Return a summary string of older turns and trim context."""
        if len(self.turns) <= keep_recent:
            return ""
        old = list(self.turns)[:len(self.turns) - keep_recent]
        summary_parts = []
        for turn in old:
            summary_parts.append(f"User: {turn.user_message.content[:80]}...")
            if turn.assistant_message:
                summary_parts.append(f"Assistant: {turn.assistant_message.content[:80]}...")
        for _ in range(len(old)):
            self.turns.popleft()
        return "\n".join(summary_parts)


class AssistantCoordinator:
    """Coordinates message routing, tool execution, and context management."""

    def __init__(
        self,
        system_prompt: str = "",
        max_turns: int = 50,
    ) -> None:
        self.context = ContextWindow(max_turns=max_turns, system_prompt=system_prompt)
        self._tool_handlers: dict[str, Callable[..., Any]] = {}
        self._middleware: list[Callable[[AssistantMessage], AssistantMessage]] = []
        self._turn_counter = 0

    def register_tool(self, name: str, handler: Callable[..., Any]) -> None:
        """Register a callable as a tool handler."""
        self._tool_handlers[name] = handler
        logger.debug("Registered tool handler: %s", name)

    def register_middleware(self, fn: Callable[[AssistantMessage], AssistantMessage]) -> None:
        """Add middleware that transforms messages before processing."""
        self._middleware.append(fn)

    def route_message(self, content: str, metadata: dict[str, Any] | None = None) -> ConversationTurn:
        """Route an incoming user message and create a conversation turn."""
        user_msg = AssistantMessage(
            role=MessageRole.USER,
            content=content,
            metadata=metadata or {},
        )
        for mw in self._middleware:
            user_msg = mw(user_msg)

        self._turn_counter += 1
        turn = ConversationTurn(
            user_message=user_msg,
            turn_number=self._turn_counter,
        )
        self.context.add_turn(turn)
        logger.info("Routed message for turn %d", self._turn_counter)
        return turn

    def set_response(self, turn: ConversationTurn, content: str, tool_calls: list[dict[str, Any]] | None = None) -> AssistantMessage:
        """Set the assistant response for a conversation turn."""
        msg = AssistantMessage(
            role=MessageRole.ASSISTANT,
            content=content,
            parent_id=turn.user_message.message_id,
        )
        if tool_calls:
            for tc in tool_calls:
                msg.add_tool_call(tc["name"], tc.get("arguments", {}))
        turn.assistant_message = msg
        return msg

    def handle_tool_call(self, tool_call: ToolCall) -> Any:
        """Execute a single tool call using registered handlers."""
        handler = self._tool_handlers.get(tool_call.tool_name)
        if handler is None:
            tool_call.mark_failed(f"No handler registered for tool: {tool_call.tool_name}")
            raise KeyError(f"Unknown tool: {tool_call.tool_name}")

        tool_call.mark_running()
        try:
            result = handler(**tool_call.arguments)
            tool_call.mark_completed(result)
            logger.info("Tool %s completed in %.1fms", tool_call.tool_name, tool_call.duration_ms or 0)
            return result
        except Exception as exc:
            tool_call.mark_failed(str(exc))
            logger.error("Tool %s failed: %s", tool_call.tool_name, exc)
            raise

    def handle_all_tool_calls(self, message: AssistantMessage) -> dict[str, Any]:
        """Execute all pending tool calls on a message, returning results keyed by call_id."""
        results: dict[str, Any] = {}
        for tc in message.pending_tool_calls:
            try:
                results[tc.call_id] = self.handle_tool_call(tc)
            except Exception:
                results[tc.call_id] = {"error": tc.error}
        return results

    def manage_context(self, *, compact: bool = False) -> dict[str, Any]:
        """Return context stats and optionally compact old turns."""
        stats = {
            "turn_count": self.context.current_turn_count,
            "max_turns": self.context.max_turns,
            "registered_tools": list(self._tool_handlers.keys()),
        }
        if compact:
            summary = self.context.summarize_old_turns()
            stats["compacted_summary_length"] = len(summary)
        return stats

    @property
    def available_tools(self) -> list[str]:
        return list(self._tool_handlers.keys())
