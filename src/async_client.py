"""Async model client for concurrent operations.

Wraps the synchronous ModelClient providers with asyncio for:
  - Parallel multi-provider queries (ask multiple models at once)
  - Non-blocking streaming
  - Concurrent tool execution
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import AsyncIterator

from .model_client import (
    ModelClient,
    ModelConfig,
    ModelResponse,
    create_provider,
    PROVIDER_PRESETS,
)

_executor = ThreadPoolExecutor(max_workers=4)


class AsyncModelClient:
    """Async wrapper around ModelClient for concurrent operations."""

    def __init__(self, config: ModelConfig | None = None) -> None:
        self._sync = ModelClient(config)

    @property
    def config(self) -> ModelConfig:
        return self._sync.config

    async def chat(self, message: str) -> ModelResponse:
        """Send a message asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._sync.chat, message)

    async def stream_chat(self, message: str) -> AsyncIterator[str]:
        """Stream tokens asynchronously."""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _producer():
            try:
                for token in self._sync.stream_chat(message):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        _executor.submit(_producer)

        while True:
            token = await queue.get()
            if token is None:
                break
            yield token

    def clear_history(self) -> None:
        self._sync.clear_history()


@dataclass
class ParallelResult:
    """Result from a parallel multi-provider query."""
    provider: str
    model: str
    response: ModelResponse | None
    error: str | None = None
    elapsed_ms: float = 0.0


async def parallel_ask(
    prompt: str,
    providers: list[str] | None = None,
    models: dict[str, str] | None = None,
) -> list[ParallelResult]:
    """Ask multiple providers in parallel and return all results.

    Args:
        prompt:    The prompt to send.
        providers: List of provider names. Defaults to all configured providers.
        models:    Optional {provider: model} overrides.

    Returns:
        List of ParallelResult, one per provider (in completion order).
    """
    import time

    if providers is None:
        providers = ['anthropic', 'openai', 'ollama']

    models = models or {}

    async def _ask_one(provider_name: str) -> ParallelResult:
        start = time.monotonic()
        try:
            config = ModelConfig.from_env()
            preset = PROVIDER_PRESETS.get(provider_name, {})
            config.provider = provider_name
            config.base_url = preset.get('base_url', '')
            config.model = models.get(provider_name, preset.get('default_model', ''))

            # Resolve API key
            import os
            env_key = preset.get('env_key', '')
            if env_key:
                config.api_key = os.environ.get(env_key, '')

            if not config.is_configured:
                return ParallelResult(
                    provider=provider_name,
                    model=config.model,
                    response=None,
                    error=f'{provider_name} not configured',
                    elapsed_ms=(time.monotonic() - start) * 1000,
                )

            client = AsyncModelClient(config)
            response = await client.chat(prompt)
            return ParallelResult(
                provider=provider_name,
                model=response.model,
                response=response,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ParallelResult(
                provider=provider_name,
                model=models.get(provider_name, ''),
                response=None,
                error=str(e),
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

    tasks = [_ask_one(p) for p in providers]
    return await asyncio.gather(*tasks)


async def race_ask(
    prompt: str,
    providers: list[str],
) -> ParallelResult:
    """Race multiple providers — return the first successful response.

    Useful for latency-sensitive queries where you want the fastest answer.
    """
    import time

    async def _ask_one(provider_name: str) -> ParallelResult:
        start = time.monotonic()
        try:
            config = ModelConfig.from_env()
            preset = PROVIDER_PRESETS.get(provider_name, {})
            config.provider = provider_name
            config.base_url = preset.get('base_url', '')
            config.model = preset.get('default_model', '')

            import os
            env_key = preset.get('env_key', '')
            if env_key:
                config.api_key = os.environ.get(env_key, '')

            if not config.is_configured:
                raise RuntimeError(f'{provider_name} not configured')

            client = AsyncModelClient(config)
            response = await client.chat(prompt)
            return ParallelResult(
                provider=provider_name,
                model=response.model,
                response=response,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            raise RuntimeError(str(e))

    tasks = [asyncio.create_task(_ask_one(p)) for p in providers]

    # Return first successful result
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    # Cancel remaining
    for task in pending:
        task.cancel()

    for task in done:
        if not task.exception():
            return task.result()

    # All failed - return last error
    for task in done:
        exc = task.exception()
        if exc:
            return ParallelResult(
                provider=providers[0],
                model='',
                response=None,
                error=str(exc),
            )

    return ParallelResult(provider='', model='', response=None, error='All providers failed')
