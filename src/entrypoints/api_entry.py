"""Programmatic API entry point for embedding pyclaude in other applications."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

logger = logging.getLogger(__name__)


@dataclass
class APIConfig:
    """Configuration for the programmatic API."""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    system_prompt: str = ""
    config_path: Path | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    timeout_seconds: float = 120.0


@dataclass
class APIResponse:
    """Response from a pyclaude API call."""
    content: str
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"
    session_id: str = ""

    @property
    def input_tokens(self) -> int:
        return self.usage.get("input_tokens", 0)

    @property
    def output_tokens(self) -> int:
        return self.usage.get("output_tokens", 0)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class PyClaude:
    """Main programmatic API for pyclaude."""

    def __init__(self, config: APIConfig | None = None) -> None:
        self.config = config or APIConfig()
        self._session_id: str = ""
        self._conversation: list[dict[str, str]] = []
        self._initialized = False

    def initialize(self) -> None:
        """Perform one-time initialization."""
        if self._initialized:
            return
        logger.info("Initializing PyClaude API with model=%s", self.config.model)
        self._initialized = True

    def ask(self, prompt: str, **kwargs: Any) -> APIResponse:
        """Send a single prompt and get a response (stateless)."""
        self.initialize()
        logger.info("API ask: %s", prompt[:80])
        # In a real implementation, this would call the Claude API
        return APIResponse(
            content=f"[Response to: {prompt[:50]}]",
            model=self.config.model,
            usage={"input_tokens": len(prompt) // 4, "output_tokens": 100},
            session_id=self._session_id,
        )

    def chat(self, message: str, **kwargs: Any) -> APIResponse:
        """Send a message in an ongoing conversation (stateful)."""
        self.initialize()
        self._conversation.append({"role": "user", "content": message})
        response = self.ask(message, **kwargs)
        self._conversation.append({"role": "assistant", "content": response.content})
        return response

    def stream(self, prompt: str, **kwargs: Any) -> Iterator[str]:
        """Stream a response token by token."""
        self.initialize()
        response = self.ask(prompt, **kwargs)
        # Simulate streaming by yielding word by word
        for word in response.content.split():
            yield word + " "

    def reset_conversation(self) -> None:
        """Clear conversation history."""
        self._conversation.clear()

    @property
    def conversation_length(self) -> int:
        return len(self._conversation)

    def set_system_prompt(self, prompt: str) -> None:
        self.config.system_prompt = prompt

    def register_tool(self, name: str, description: str, parameters: dict[str, Any]) -> None:
        """Register a tool for the assistant to use."""
        self.config.tools.append({
            "name": name,
            "description": description,
            "parameters": parameters,
        })

    def __enter__(self) -> PyClaude:
        self.initialize()
        return self

    def __exit__(self, *args: Any) -> None:
        self.reset_conversation()


def create_client(
    model: str | None = None,
    system_prompt: str = "",
    **kwargs: Any,
) -> PyClaude:
    """Convenience factory for creating a PyClaude client."""
    config = APIConfig(
        model=model or "claude-sonnet-4-20250514",
        system_prompt=system_prompt,
        **kwargs,
    )
    return PyClaude(config=config)
