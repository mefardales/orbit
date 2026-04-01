"""Type definitions for openclaw gateway integration."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OpenclawConfig:
    """Configuration for an openclaw gateway connection."""

    gateway_url: str
    api_key: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    headers: Dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    tags: List[str] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        return self.gateway_url.rstrip("/")

    def auth_header(self) -> Dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}


@dataclass
class OpenclawEvent:
    """An event to be dispatched through the gateway."""

    event_type: str
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
        }


@dataclass
class OpenclawPayload:
    """A formatted payload ready for gateway dispatch."""

    endpoint: str
    method: str = "POST"
    body: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, str] = field(default_factory=dict)

    def merged_headers(self, config: OpenclawConfig) -> Dict[str, str]:
        merged = dict(config.headers)
        merged.update(config.auth_header())
        merged.update(self.headers)
        merged.setdefault("Content-Type", "application/json")
        return merged

    def full_url(self, config: OpenclawConfig) -> str:
        url = f"{config.base_url}/{self.endpoint.lstrip('/')}"
        if self.query_params:
            qs = "&".join(f"{k}={v}" for k, v in self.query_params.items())
            url = f"{url}?{qs}"
        return url
