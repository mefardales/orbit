"""HTTP middleware: auth, logging, and CORS."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# (status, headers, body)
Response = Tuple[int, Dict[str, str], bytes]
NextFunc = Callable[[], Response]


class Middleware(ABC):
    """Abstract middleware base class."""

    @abstractmethod
    def process(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        next_handler: NextFunc,
    ) -> Response:
        """Process a request, optionally delegating to next_handler."""
        ...


class AuthMiddleware(Middleware):
    """Token-based authentication middleware."""

    def __init__(self, token: str, exclude_paths: Optional[List[str]] = None):
        self.token = token
        self.exclude_paths = set(exclude_paths or ["/health", "/status"])

    def process(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        next_handler: NextFunc,
    ) -> Response:
        if not self.token:
            return next_handler()

        if path in self.exclude_paths:
            return next_handler()

        auth = headers.get("authorization", headers.get("Authorization", ""))
        if auth == f"Bearer {self.token}":
            return next_handler()

        logger.warning("Unauthorized request to %s", path)
        return (
            401,
            {"Content-Type": "application/json", "WWW-Authenticate": "Bearer"},
            b'{"error": "unauthorized"}',
        )


class LoggingMiddleware(Middleware):
    """Request/response logging middleware."""

    def __init__(self, log_level: int = logging.INFO):
        self.log_level = log_level
        self._request_count = 0

    def process(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        next_handler: NextFunc,
    ) -> Response:
        self._request_count += 1
        start = time.monotonic()

        logger.log(self.log_level, "[%d] -> %s %s", self._request_count, method, path)

        status, resp_headers, resp_body = next_handler()

        elapsed = (time.monotonic() - start) * 1000
        logger.log(
            self.log_level,
            "[%d] <- %s %s %d (%.1fms, %d bytes)",
            self._request_count, method, path, status, elapsed, len(resp_body),
        )

        return status, resp_headers, resp_body

    @property
    def request_count(self) -> int:
        return self._request_count


class CorsMiddleware(Middleware):
    """Cross-Origin Resource Sharing middleware."""

    def __init__(
        self,
        allowed_origins: Optional[List[str]] = None,
        allowed_methods: Optional[List[str]] = None,
        allowed_headers: Optional[List[str]] = None,
        max_age: int = 86400,
    ):
        self.allowed_origins = allowed_origins or ["*"]
        self.allowed_methods = allowed_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allowed_headers = allowed_headers or ["Content-Type", "Authorization"]
        self.max_age = max_age

    def _origin_allowed(self, origin: str) -> bool:
        if "*" in self.allowed_origins:
            return True
        for pattern in self.allowed_origins:
            if pattern.endswith("*"):
                if origin.startswith(pattern[:-1]):
                    return True
            elif origin == pattern:
                return True
        return False

    def _cors_headers(self, origin: str) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": origin if self._origin_allowed(origin) else "",
            "Access-Control-Allow-Methods": ", ".join(self.allowed_methods),
            "Access-Control-Allow-Headers": ", ".join(self.allowed_headers),
            "Access-Control-Max-Age": str(self.max_age),
        }

    def process(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        next_handler: NextFunc,
    ) -> Response:
        origin = headers.get("origin", headers.get("Origin", ""))

        # Handle preflight
        if method.upper() == "OPTIONS":
            cors = self._cors_headers(origin)
            return 204, cors, b""

        status, resp_headers, resp_body = next_handler()

        if origin:
            cors = self._cors_headers(origin)
            resp_headers.update(cors)

        return status, resp_headers, resp_body


class MiddlewareChain:
    """Composes multiple middleware into an ordered processing chain."""

    def __init__(self) -> None:
        self._stack: List[Middleware] = []

    def use(self, middleware: Middleware) -> "MiddlewareChain":
        """Add middleware to the chain. First added = outermost."""
        self._stack.append(middleware)
        return self

    def execute(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        final_handler: NextFunc,
    ) -> Response:
        """Execute the full middleware chain, ending with final_handler."""

        def build_chain(index: int) -> NextFunc:
            if index >= len(self._stack):
                return final_handler

            mw = self._stack[index]

            def next_fn() -> Response:
                return mw.process(method, path, headers, body, build_chain(index + 1))

            return next_fn

        return build_chain(0)()
