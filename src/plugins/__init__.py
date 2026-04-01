"""Plugin system for orbit."""

from plugins.types import Plugin, PluginManifest, PluginHook, PluginState
from plugins.loader import PluginLoader
from plugins.registry import PluginRegistry

__all__ = [
    "Plugin",
    "PluginManifest",
    "PluginHook",
    "PluginState",
    "PluginLoader",
    "PluginRegistry",
]
