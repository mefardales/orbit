"""Environment variable names used throughout orbit.

All environment variables use the ORBIT_ prefix to avoid collisions
with other applications.
"""

# Core configuration
ENV_API_KEY = "ORBIT_API_KEY"
ENV_MODEL = "ORBIT_MODEL"
ENV_MAX_TOKENS = "ORBIT_MAX_TOKENS"
ENV_TEMPERATURE = "ORBIT_TEMPERATURE"

# Directory overrides
ENV_CONFIG_DIR = "ORBIT_CONFIG_DIR"
ENV_DATA_DIR = "ORBIT_DATA_DIR"
ENV_CACHE_DIR = "ORBIT_CACHE_DIR"
ENV_LOG_DIR = "ORBIT_LOG_DIR"
ENV_PLUGIN_DIR = "ORBIT_PLUGIN_DIR"

# Logging
ENV_LOG_LEVEL = "ORBIT_LOG_LEVEL"
ENV_LOG_FILE = "ORBIT_LOG_FILE"
ENV_LOG_FORMAT = "ORBIT_LOG_FORMAT"
ENV_DEBUG = "ORBIT_DEBUG"

# Server
ENV_SERVER_HOST = "ORBIT_SERVER_HOST"
ENV_SERVER_PORT = "ORBIT_SERVER_PORT"
ENV_SERVER_WORKERS = "ORBIT_SERVER_WORKERS"

# Cache
ENV_CACHE_ENABLED = "ORBIT_CACHE_ENABLED"
ENV_CACHE_TTL = "ORBIT_CACHE_TTL"
ENV_CACHE_MAX_SIZE = "ORBIT_CACHE_MAX_SIZE"

# Rate limiting
ENV_RATE_LIMIT = "ORBIT_RATE_LIMIT"
ENV_RATE_LIMIT_WINDOW = "ORBIT_RATE_LIMIT_WINDOW"

# Feature flags
ENV_PLUGINS_ENABLED = "ORBIT_PLUGINS_ENABLED"
ENV_TELEMETRY_ENABLED = "ORBIT_TELEMETRY_ENABLED"
ENV_AUTO_UPDATE = "ORBIT_AUTO_UPDATE"

# Authentication
ENV_AUTH_TOKEN = "ORBIT_AUTH_TOKEN"
ENV_ORG_ID = "ORBIT_ORG_ID"

# Proxy
ENV_HTTP_PROXY = "ORBIT_HTTP_PROXY"
ENV_HTTPS_PROXY = "ORBIT_HTTPS_PROXY"
ENV_NO_PROXY = "ORBIT_NO_PROXY"

import os
from typing import Optional


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get a orbit environment variable value."""
    return os.environ.get(name, default)


def get_env_bool(name: str, default: bool = False) -> bool:
    """Get a orbit environment variable as a boolean."""
    val = os.environ.get(name, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def get_env_int(name: str, default: int = 0) -> int:
    """Get a orbit environment variable as an integer."""
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
