"""Configuration loading and validation for openclaw gateways."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import OpenclawConfig

DEFAULT_CONFIG_FILENAME = "openclaw.json"
KNOWN_GATEWAYS = {
    "default": "https://gateway.openclaw.io/v1",
    "staging": "https://staging.gateway.openclaw.io/v1",
    "local": "http://localhost:8090/v1",
}


def load_openclaw_config(
    path: Optional[Path] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> OpenclawConfig:
    """Load openclaw configuration from a JSON file with optional overrides."""
    data: Dict[str, Any] = {}
    if path is None:
        path = Path.cwd() / DEFAULT_CONFIG_FILENAME
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
    if overrides:
        data.update(overrides)
    gateway_url = resolve_gateway(data.get("gateway", data.get("gateway_url", "")))
    return OpenclawConfig(
        gateway_url=gateway_url,
        api_key=data.get("api_key"),
        timeout=float(data.get("timeout", 30.0)),
        max_retries=int(data.get("max_retries", 3)),
        retry_delay=float(data.get("retry_delay", 1.0)),
        headers=data.get("headers", {}),
        verify_ssl=data.get("verify_ssl", True),
        tags=data.get("tags", []),
    )


def validate_config(config: OpenclawConfig) -> List[str]:
    """Validate an openclaw config, returning a list of error messages (empty if valid)."""
    errors: List[str] = []
    if not config.gateway_url:
        errors.append("gateway_url is required")
    elif not config.gateway_url.startswith(("http://", "https://")):
        errors.append(f"gateway_url must be http or https, got: {config.gateway_url}")
    if config.timeout <= 0:
        errors.append(f"timeout must be positive, got: {config.timeout}")
    if config.max_retries < 0:
        errors.append(f"max_retries must be non-negative, got: {config.max_retries}")
    if config.retry_delay < 0:
        errors.append(f"retry_delay must be non-negative, got: {config.retry_delay}")
    return errors


def resolve_gateway(name_or_url: str) -> str:
    """Resolve a gateway name to a URL, or return the URL as-is."""
    if not name_or_url:
        return KNOWN_GATEWAYS["default"]
    if name_or_url in KNOWN_GATEWAYS:
        return KNOWN_GATEWAYS[name_or_url]
    return name_or_url
