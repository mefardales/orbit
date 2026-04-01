"""
MCP Registry: discovers and manages external MCP server configurations.

Reads server definitions from .orbit/mcp-servers.json (project-local)
and ~/.orbit/mcp-servers.json (user-global), with project-local taking
precedence for servers with the same name.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orbit.mcp.registry")

_PROJECT_CONFIG = Path(".orbit") / "mcp-servers.json"
_USER_CONFIG = Path.home() / ".orbit" / "mcp-servers.json"


@dataclass
class MCPServerConfig:
    """Configuration for a single external MCP server."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServerConfig":
        if "name" not in data or "command" not in data:
            raise ValueError("MCPServerConfig requires 'name' and 'command' fields")
        return cls(
            name=str(data["name"]),
            command=str(data["command"]),
            args=[str(a) for a in data.get("args", [])],
            env={str(k): str(v) for k, v in data.get("env", {}).items()},
            enabled=bool(data.get("enabled", True)),
        )


def _load_config_file(path: Path) -> Dict[str, MCPServerConfig]:
    """Load server configs from a single JSON file.

    Returns a dict keyed by server name. Returns {} if the file does not exist
    or is malformed (error is logged but not raised).
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read MCP config %s: %s", path, exc)
        return {}

    servers_list: Any = raw.get("servers", raw) if isinstance(raw, dict) else raw
    if not isinstance(servers_list, list):
        logger.warning("MCP config %s: expected a list under 'servers' key", path)
        return {}

    result: Dict[str, MCPServerConfig] = {}
    for entry in servers_list:
        try:
            cfg = MCPServerConfig.from_dict(entry)
            result[cfg.name] = cfg
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping malformed server entry in %s: %s", path, exc)
    return result


class MCPRegistry:
    """Discovers and provides access to external MCP server configurations.

    Discovery order (later entries override earlier ones with the same name):
    1. User-global:  ~/.orbit/mcp-servers.json
    2. Project-local: .orbit/mcp-servers.json  (highest priority)
    """

    def __init__(
        self,
        project_config: Optional[Path] = None,
        user_config: Optional[Path] = None,
    ) -> None:
        self._project_config = project_config or _PROJECT_CONFIG
        self._user_config = user_config or _USER_CONFIG
        self._servers: Optional[Dict[str, MCPServerConfig]] = None

    # ── Discovery ────────────────────────────────────────────────────────────

    def discover_servers(self) -> List[MCPServerConfig]:
        """Return all discovered MCP server configs (enabled or disabled).

        Reads both config files on every call so that changes are reflected
        without restarting. Project-local entries win over user-global ones.
        """
        merged: Dict[str, MCPServerConfig] = {}
        merged.update(_load_config_file(self._user_config))
        merged.update(_load_config_file(self._project_config))
        self._servers = merged
        return list(merged.values())

    def _ensure_loaded(self) -> None:
        if self._servers is None:
            self.discover_servers()

    # ── Accessors ────────────────────────────────────────────────────────────

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """Return the config for a server by name, or None if not found."""
        self._ensure_loaded()
        assert self._servers is not None
        return self._servers.get(name)

    def list_servers(self) -> List[str]:
        """Return a sorted list of all discovered server names."""
        self._ensure_loaded()
        assert self._servers is not None
        return sorted(self._servers.keys())

    def list_enabled_servers(self) -> List[MCPServerConfig]:
        """Return configs for servers that have enabled=True."""
        return [s for s in self.discover_servers() if s.enabled]

    # ── Persistence helpers ──────────────────────────────────────────────────

    def save_server(self, config: MCPServerConfig, *, scope: str = "project") -> None:
        """Persist a server config to either the project or user config file.

        Args:
            config: The server config to save or update.
            scope: 'project' (default) or 'user'.
        """
        path = self._project_config if scope == "project" else self._user_config
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = _load_config_file(path)
        existing[config.name] = config

        payload = {"servers": [v.to_dict() for v in existing.values()]}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Invalidate cache
        self._servers = None
        logger.info("Saved MCP server %r to %s", config.name, path)

    def remove_server(self, name: str, *, scope: str = "project") -> bool:
        """Remove a server from the specified config file.

        Returns True if the server was found and removed.
        """
        path = self._project_config if scope == "project" else self._user_config
        existing = _load_config_file(path)
        if name not in existing:
            return False
        del existing[name]
        payload = {"servers": [v.to_dict() for v in existing.values()]}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._servers = None
        logger.info("Removed MCP server %r from %s", name, path)
        return True


# Module-level default registry
_default_registry = MCPRegistry()


def get_registry() -> MCPRegistry:
    """Return the module-level default MCPRegistry instance."""
    return _default_registry
