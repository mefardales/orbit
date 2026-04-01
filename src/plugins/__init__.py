"""Plugin system for orbit."""

from .types import Plugin, PluginManifest, PluginHook, PluginState
from .loader import PluginLoader
from .registry import PluginRegistry

__all__ = [
    "Plugin",
    "PluginManifest",
    "PluginHook",
    "PluginState",
    "PluginLoader",
    "PluginRegistry",
]
