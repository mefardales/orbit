"""Configuration for the upstream API proxy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProxyConfig:
    """Holds all tunables for an :class:`UpstreamProxy` instance."""

    endpoint: str = "https://api.anthropic.com"
    timeout: float = 60.0
    max_retries: int = 3
    headers: dict[str, str] = field(default_factory=dict)
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    retry_jitter: float = 0.25
    verify_ssl: bool = True
    proxy_url: Optional[str] = None

    # Status codes that should trigger an automatic retry.
    retryable_status_codes: frozenset[int] = frozenset({429, 500, 502, 503, 504})

    def merged_headers(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        """Return *self.headers* merged with *extra* (extra wins)."""
        merged = dict(self.headers)
        if extra:
            merged.update(extra)
        return merged

    def effective_endpoint(self, path: str) -> str:
        """Join *endpoint* and *path*, normalising slashes."""
        base = self.endpoint.rstrip("/")
        path = path.lstrip("/")
        return f"{base}/{path}"

    def validate(self) -> list[str]:
        """Return a list of validation error strings (empty == valid)."""
        errors: list[str] = []
        if not self.endpoint:
            errors.append("endpoint must not be empty")
        if self.timeout <= 0:
            errors.append("timeout must be positive")
        if self.max_retries < 0:
            errors.append("max_retries must be >= 0")
        if self.retry_base_delay <= 0:
            errors.append("retry_base_delay must be positive")
        return errors
