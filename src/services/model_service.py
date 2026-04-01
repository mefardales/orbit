"""Service for interacting with Claude models: query, streaming, and token counting."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """Response from a model query."""
    content: str
    model: str
    stop_reason: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""
    text: str
    is_final: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class ModelServiceBase(ABC):
    """Abstract base for model service implementations."""

    @abstractmethod
    def query(self, messages: List[Message], **kwargs: Any) -> ModelResponse:
        ...

    @abstractmethod
    def stream(self, messages: List[Message], **kwargs: Any) -> Iterator[StreamChunk]:
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        ...


class ModelService(ModelServiceBase):
    """Concrete model service that talks to the Anthropic API."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 8192,
        temperature: float = 0.7,
        base_url: str = "https://api.anthropic.com",
        timeout: float = 120.0,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._request_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def _build_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_payload(self, messages: List[Message], **kwargs: Any) -> Dict[str, Any]:
        formatted = []
        system_prompt = None
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                formatted.append({"role": msg.role, "content": msg.content})

        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": formatted,
        }
        if system_prompt:
            payload["system"] = system_prompt
        return payload

    def query(self, messages: List[Message], **kwargs: Any) -> ModelResponse:
        """Send a synchronous query to the model."""
        import urllib.request
        import urllib.error

        start = time.monotonic()
        payload = self._build_payload(messages, **kwargs)

        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API error {e.code}: {body}") from e

        elapsed = (time.monotonic() - start) * 1000
        self._request_count += 1

        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")

        usage = data.get("usage", {})
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        self._total_input_tokens += inp
        self._total_output_tokens += out

        return ModelResponse(
            content=text,
            model=data.get("model", self.model),
            stop_reason=data.get("stop_reason"),
            input_tokens=inp,
            output_tokens=out,
            latency_ms=elapsed,
        )

    def stream(self, messages: List[Message], **kwargs: Any) -> Iterator[StreamChunk]:
        """Send a streaming query, yielding chunks as they arrive."""
        import urllib.request

        payload = self._build_payload(messages, **kwargs)
        payload["stream"] = True

        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            buffer = ""
            for raw_line in resp:
                line = raw_line.decode("utf-8")
                buffer += line
                if not line.strip():
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        yield StreamChunk(text="", is_final=True)
                        return
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    evt_type = event.get("type", "")
                    if evt_type == "content_block_delta":
                        delta = event.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            yield StreamChunk(text=text)
                    elif evt_type == "message_stop":
                        yield StreamChunk(text="", is_final=True)
                        return

    def count_tokens(self, text: str) -> int:
        """Estimate token count. Uses a simple heuristic (~4 chars per token)."""
        # A real implementation would use the tokenizer API
        return max(1, len(text) // 4)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "requests": self._request_count,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
        }
