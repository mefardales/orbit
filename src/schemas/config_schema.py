"""Configuration schema with all config fields and their defaults."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ServerConfig:
    """Server-specific configuration."""
    host: str = "127.0.0.1"
    port: int = 7429
    workers: int = 1
    cors_origins: List[str] = field(default_factory=lambda: ["http://localhost:*"])
    auth_enabled: bool = False
    auth_token: str = ""


@dataclass
class CacheConfig:
    """Cache-specific configuration."""
    enabled: bool = True
    ttl: float = 3600.0
    max_size: int = 1000
    strategy: str = "lru"
    persist_to_disk: bool = False


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: Optional[str] = None
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    max_size: int = 5 * 1024 * 1024
    backup_count: int = 3


@dataclass
class PluginsConfig:
    """Plugin system configuration."""
    enabled: bool = True
    directories: List[str] = field(default_factory=list)
    auto_load: bool = True
    max_plugins: int = 50


@dataclass
class ConfigSchema:
    """Complete orbit configuration schema with all fields and defaults.

    This is the canonical source of truth for all configuration options.
    """

    # Core model settings
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    max_tokens: int = 8192
    temperature: float = 0.7
    top_p: float = 1.0
    timeout: float = 120.0
    max_retries: int = 3

    # Directories
    config_dir: str = str(Path.home() / ".config" / "orbit")
    data_dir: str = str(Path.home() / ".local" / "share" / "orbit")
    cache_dir: str = str(Path.home() / ".cache" / "orbit")

    # Feature flags
    telemetry_enabled: bool = False
    auto_update: bool = False
    debug: bool = False

    # Nested configs
    server: ServerConfig = field(default_factory=ServerConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)

    # Conversation
    history_limit: int = 100
    max_conversation_turns: int = 50
    auto_summarize: bool = True
    summary_threshold: int = 20

    # Rate limiting
    rate_limit_requests: int = 60
    rate_limit_window: int = 60

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full config to a flat-friendly dictionary."""
        result: Dict[str, Any] = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if hasattr(val, "__dataclass_fields__"):
                result[f.name] = asdict(val)
            else:
                result[f.name] = val
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConfigSchema:
        """Create a ConfigSchema from a dictionary, using defaults for missing keys."""
        nested_types = {
            "server": ServerConfig,
            "cache": CacheConfig,
            "logging": LoggingConfig,
            "plugins": PluginsConfig,
        }
        kwargs: Dict[str, Any] = {}
        valid_fields = {f.name for f in fields(cls)}

        for key, value in data.items():
            if key not in valid_fields:
                continue
            if key in nested_types and isinstance(value, dict):
                kwargs[key] = nested_types[key](**value)
            else:
                kwargs[key] = value

        return cls(**kwargs)

    def merge(self, overrides: Dict[str, Any]) -> ConfigSchema:
        """Return a new ConfigSchema with overrides applied."""
        base = self.to_dict()
        for key, value in overrides.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key].update(value)
            else:
                base[key] = value
        return ConfigSchema.from_dict(base)

    def validate(self) -> List[str]:
        """Run basic validation, returning a list of error messages."""
        from schemas.validators import validate_config
        result = validate_config(self.to_dict())
        return result.error_messages

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dotted key path."""
        parts = key.split(".")
        current: Any = self
        for part in parts:
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict):
                current = current.get(part, default)
            else:
                return default
        return current
