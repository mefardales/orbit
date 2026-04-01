"""Dispatcher for sending events through openclaw gateways."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .types import OpenclawConfig, OpenclawEvent, OpenclawPayload

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Result of a single dispatch attempt."""

    success: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 1


@dataclass
class OpenclawDispatcher:
    """Dispatches events to an openclaw gateway."""

    config: OpenclawConfig
    _dispatch_count: int = field(default=0, init=False, repr=False)

    def format_payload(self, event: OpenclawEvent) -> OpenclawPayload:
        """Format an event into a gateway-ready payload."""
        return OpenclawPayload(
            endpoint="/events",
            method="POST",
            body=event.to_dict(),
            headers={"X-Event-Type": event.event_type},
        )

    def dispatch(self, event: OpenclawEvent) -> DispatchResult:
        """Dispatch a single event to the gateway with retries."""
        payload = self.format_payload(event)
        last_error: Optional[str] = None
        for attempt in range(1, self.config.max_retries + 1):
            result = self._send(payload, attempt)
            if result.success:
                self._dispatch_count += 1
                return result
            last_error = result.error
            if attempt < self.config.max_retries:
                time.sleep(self.config.retry_delay * attempt)
        return DispatchResult(
            success=False,
            error=f"Failed after {self.config.max_retries} attempts: {last_error}",
            attempts=self.config.max_retries,
        )

    def dispatch_batch(self, events: List[OpenclawEvent]) -> List[DispatchResult]:
        """Dispatch multiple events, returning results for each."""
        results: List[DispatchResult] = []
        for event in events:
            results.append(self.dispatch(event))
        return results

    def retry(self, event: OpenclawEvent, max_attempts: Optional[int] = None) -> DispatchResult:
        """Retry dispatching an event with a custom attempt limit."""
        original_retries = self.config.max_retries
        if max_attempts is not None:
            self.config.max_retries = max_attempts
        try:
            return self.dispatch(event)
        finally:
            self.config.max_retries = original_retries

    def _send(self, payload: OpenclawPayload, attempt: int) -> DispatchResult:
        """Execute a single HTTP request to the gateway."""
        url = payload.full_url(self.config)
        headers = payload.merged_headers(self.config)
        body_bytes = json.dumps(payload.body).encode("utf-8")
        req = urllib.request.Request(
            url, data=body_bytes, headers=headers, method=payload.method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                response_body = resp.read().decode("utf-8")
                return DispatchResult(
                    success=True,
                    status_code=resp.status,
                    response_body=response_body,
                    attempts=attempt,
                )
        except urllib.error.HTTPError as e:
            return DispatchResult(
                success=False,
                status_code=e.code,
                error=f"HTTP {e.code}: {e.reason}",
                attempts=attempt,
            )
        except Exception as e:
            return DispatchResult(
                success=False, error=str(e), attempts=attempt
            )
