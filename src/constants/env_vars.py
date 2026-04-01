"""Environment variable names used throughout pyclaude.

All environment variables use the PYCLAUDE_ prefix to avoid collisions
with other applications.
"""

# Core configuration
ENV_API_KEY = "PYCLAUDE_API_KEY"
ENV_MODEL = "PYCLAUDE_MODEL"
ENV_MAX_TOKENS = "PYCLAUDE_MAX_TOKENS"
ENV_TEMPERATURE = "PYCLAUDE_TEMPERATURE"

# Directory overrides
ENV_CONFIG_DIR = "PYCLAUDE_CONFIG_DIR"
ENV_DATA_DIR = "PYCLAUDE_DATA_DIR"
ENV_CACHE_DIR = "PYCLAUDE_CACHE_DIR"
ENV_LOG_DIR = "PYCLAUDE_LOG_DIR"
ENV_PLUGIN_DIR = "PYCLAUDE_PLUGIN_DIR"

# Logging
ENV_LOG_LEVEL = "PYCLAUDE_LOG_LEVEL"
ENV_LOG_FILE = "PYCLAUDE_LOG_FILE"
ENV_LOG_FORMAT = "PYCLAUDE_LOG_FORMAT"
ENV_DEBUG = "PYCLAUDE_DEBUG"

# Server
ENV_SERVER_HOST = "PYCLAUDE_SERVER_HOST"
ENV_SERVER_PORT = "PYCLAUDE_SERVER_PORT"
ENV_SERVER_WORKERS = "PYCLAUDE_SERVER_WORKERS"

# Cache
ENV_CACHE_ENABLED = "PYCLAUDE_CACHE_ENABLED"
ENV_CACHE_TTL = "PYCLAUDE_CACHE_TTL"
ENV_CACHE_MAX_SIZE = "PYCLAUDE_CACHE_MAX_SIZE"

# Rate limiting
ENV_RATE_LIMIT = "PYCLAUDE_RATE_LIMIT"
ENV_RATE_LIMIT_WINDOW = "PYCLAUDE_RATE_LIMIT_WINDOW"

# Feature flags
ENV_PLUGINS_ENABLED = "PYCLAUDE_PLUGINS_ENABLED"
ENV_TELEMETRY_ENABLED = "PYCLAUDE_TELEMETRY_ENABLED"
ENV_AUTO_UPDATE = "PYCLAUDE_AUTO_UPDATE"

# Authentication
ENV_AUTH_TOKEN = "PYCLAUDE_AUTH_TOKEN"
ENV_ORG_ID = "PYCLAUDE_ORG_ID"

# Proxy
ENV_HTTP_PROXY = "PYCLAUDE_HTTP_PROXY"
ENV_HTTPS_PROXY = "PYCLAUDE_HTTPS_PROXY"
ENV_NO_PROXY = "PYCLAUDE_NO_PROXY"

import os
from typing import Optional


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get a pyclaude environment variable value."""
    return os.environ.get(name, default)


def get_env_bool(name: str, default: bool = False) -> bool:
    """Get a pyclaude environment variable as a boolean."""
    val = os.environ.get(name, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def get_env_int(name: str, default: int = 0) -> int:
    """Get a pyclaude environment variable as an integer."""
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


ALL_ENV_VARS = [
    v for k, v in globals().items()
    if k.startswith("ENV_") and isinstance(v, str)
]
