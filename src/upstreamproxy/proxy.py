"""Upstream API proxy with retry and back-off support."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import ProxyConfig

logger = logging.getLogger(__name__)


@dataclass
class ProxyResponse:
    """Normalised response from the upstream API."""

    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: float
    retries_used: int = 0

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        import json
        return json.loads(self.body)

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class UpstreamProxy:
    """Forward requests to an upstream API endpoint with automatic retries."""

    def __init__(self, config: Optional[ProxyConfig] = None) -> None:
        self.config = config or ProxyConfig()
        errors = self.config.validate()
        if errors:
            raise ValueError(f"Invalid ProxyConfig: {'; '.join(errors)}")
        self._session: Any = None  # lazy aiohttp.ClientSession

    async def _ensure_session(self) -> Any:
        if self._session is None or self._session.closed:
            try:
                import aiohttp
                self._session = aiohttp.ClientSession()
            except ImportError:
                raise RuntimeError(
                    "aiohttp is required for UpstreamProxy – "
                    "install it with: pip install aiohttp"
                )
        return self._session

    async def close(self) -> None:
        """Gracefully close the underlying HTTP session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- core API --------------------------------------------------------------

    async def forward_request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[bytes | str | dict] = None,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, str]] = None,
    ) -> ProxyResponse:
        """Send a request upstream, retrying on transient failures."""
        import json as _json

        url = self.config.effective_endpoint(path)
        merged_headers = self.config.merged_headers(headers)

        payload: Optional[bytes] = None
        if isinstance(body, dict):
            payload = _json.dumps(body).encode()
            merged_headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            payload = body.encode()
        else:
            payload = body

        last_response: Optional[ProxyResponse] = None
        retries = 0

        while True:
            t0 = time.monotonic()
            try:
                session = await self._ensure_session()
                async with session.request(
                    method,
                    url,
                    data=payload,
                    headers=merged_headers,
                    params=params,
                    timeout=__import__("aiohttp").ClientTimeout(
                        total=self.config.timeout
                    ),
                    ssl=self.config.verify_ssl,
                ) as resp:
                    resp_body = await resp.read()
                    elapsed = (time.monotonic() - t0) * 1000
                    last_response = ProxyResponse(
                        status=resp.status,
                        headers=dict(resp.headers),
                        body=resp_body,
                        elapsed_ms=round(elapsed, 2),
                        retries_used=retries,
                    )
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                logger.warning("Request to %s failed: %s", url, exc)
                last_response = ProxyResponse(
                    status=0,
                    headers={},
                    body=str(exc).encode(),
                    elapsed_ms=round(elapsed, 2),
                    retries_used=retries,
                )

            if last_response.ok:
                return self.handle_response(last_response)

            if (
                last_response.status not in self.config.retryable_status_codes
                and last_response.status != 0
            ):
                return self.handle_response(last_response)

            if retries >= self.config.max_retries:
                logger.error(
                    "Exhausted %d retries for %s %s (last status=%d)",
                    self.config.max_retries,
                    method,
                    url,
                    last_response.status,
                )
                return self.handle_response(last_response)

            delay = self.retry_with_backoff(retries)
            logger.info(
                "Retrying %s %s in %.2fs (attempt %d/%d)",
                method, url, delay, retries + 1, self.config.max_retries,
            )
            await asyncio.sleep(delay)
            retries += 1

    def handle_response(self, response: ProxyResponse) -> ProxyResponse:
        """Post-process a response (hook for subclasses)."""
        if not response.ok:
            logger.debug(
                "Upstream returned status=%d body=%s",
                response.status,
                response.body[:200],
            )
        return response

    def retry_with_backoff(self, attempt: int) -> float:
        """Calculate the delay before the next retry using exponential back-off."""
        base = self.config.retry_base_delay * (2 ** attempt)
        jitter = random.uniform(0, self.config.retry_jitter * base)
        return min(base + jitter, self.config.retry_max_delay)
