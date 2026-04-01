"""Plugin type definitions and dataclasses."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path


class PluginState(enum.Enum):
    """Lifecycle state of a plugin."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    VALIDATED = "validated"
    ACTIVE = "active"
    ERROR = "error"
    UNLOADED = "unloaded"


@dataclass
class PluginHook:
    """Represents a single hook point that a plugin can attach to."""

    name: str
    callback: Callable[..., Any]
    priority: int = 0
    description: str = ""
    is_async: bool = False

    def __lt__(self, other: PluginHook) -> bool:
        return self.priority < other.priority

    def __repr__(self) -> str:
        return f"PluginHook(name={self.name!r}, priority={self.priority})"


@dataclass
class PluginManifest:
    """Metadata describing a plugin package."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    entry_point: str = "plugin.py"
    min_pyclaude_version: str = "0.1.0"
    max_pyclaude_version: str = ""
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PluginManifest:
        """Create a manifest from a dictionary (e.g., parsed JSON)."""
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", ""),
            homepage=data.get("homepage", ""),
            entry_point=data.get("entry_point", "plugin.py"),
            min_pyclaude_version=data.get("min_pyclaude_version", "0.1.0"),
            max_pyclaude_version=data.get("max_pyclaude_version", ""),
            dependencies=data.get("dependencies", []),
            permissions=data.get("permissions", []),
            hooks=data.get("hooks", []),
            tags=data.get("tags", []),
            config_schema=data.get("config_schema", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize manifest to a dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "entry_point": self.entry_point,
            "min_pyclaude_version": self.min_pyclaude_version,
            "max_pyclaude_version": self.max_pyclaude_version,
            "dependencies": self.dependencies,
            "permissions": self.permissions,
            "hooks": self.hooks,
            "tags": self.tags,
            "config_schema": self.config_schema,
        }


@dataclass
class Plugin:
    """Represents a loaded plugin instance."""

    manifest: PluginManifest
    path: Path
    state: PluginState = PluginState.DISCOVERED
    hooks: List[PluginHook] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    module: Any = None
    error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def is_active(self) -> bool:
        return self.state == PluginState.ACTIVE

    def get_hooks_for(self, hook_name: str) -> List[PluginHook]:
        """Return all hooks matching the given name, sorted by priority."""
        return sorted(
            [h for h in self.hooks if h.name == hook_name],
            key=lambda h: h.priority,
        )
