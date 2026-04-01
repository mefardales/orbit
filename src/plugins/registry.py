"""Plugin registry for tracking and querying active plugins and hooks."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .types import Plugin, PluginHook, PluginState

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry that tracks all plugins and dispatches hook calls."""

    def __init__(self) -> None:
        self._plugins: Dict[str, Plugin] = {}
        self._hooks: Dict[str, List[PluginHook]] = {}

    def register(self, plugin: Plugin) -> None:
        """Register a plugin and index its hooks."""
        if plugin.name in self._plugins:
            logger.warning("Plugin already registered: %s (replacing)", plugin.name)
            self.unregister(plugin.name)

        self._plugins[plugin.name] = plugin

        for hook in plugin.hooks:
            self._hooks.setdefault(hook.name, []).append(hook)
            self._hooks[hook.name].sort(key=lambda h: h.priority)

        logger.info("Registered plugin: %s with %d hooks", plugin.name, len(plugin.hooks))

    def unregister(self, name: str) -> Optional[Plugin]:
        """Remove a plugin and its hooks from the registry."""
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return None

        hook_names = {h.name for h in plugin.hooks}
        for hname in hook_names:
            if hname in self._hooks:
                self._hooks[hname] = [
                    h for h in self._hooks[hname]
                    if h not in plugin.hooks
                ]
                if not self._hooks[hname]:
                    del self._hooks[hname]

        logger.info("Unregistered plugin: %s", name)
        return plugin

    def get(self, name: str) -> Optional[Plugin]:
        """Get a registered plugin by name."""
        return self._plugins.get(name)

    def list_all(self) -> List[Plugin]:
        """Return all registered plugins."""
        return list(self._plugins.values())

    def list_active(self) -> List[Plugin]:
        """Return only active plugins."""
        return [p for p in self._plugins.values() if p.is_active]

    def get_hooks(self, hook_name: str) -> List[PluginHook]:
        """Get all hooks for a given hook name, sorted by priority."""
        return list(self._hooks.get(hook_name, []))

    def invoke_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> List[Any]:
        """Invoke all hooks with the given name. Returns list of results."""
        results: List[Any] = []
        hooks = self.get_hooks(hook_name)

        for hook in hooks:
            try:
                result = hook.callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(
                    "Hook %s from callback raised error: %s",
                    hook.name, e,
                )
                results.append(None)

        return results

    async def invoke_hook_async(self, hook_name: str, *args: Any, **kwargs: Any) -> List[Any]:
        """Invoke all async hooks with the given name."""
        import asyncio
        results: List[Any] = []
        hooks = self.get_hooks(hook_name)

        for hook in hooks:
            try:
                if hook.is_async:
                    result = await hook.callback(*args, **kwargs)
                else:
                    result = hook.callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error("Async hook %s raised error: %s", hook.name, e)
                results.append(None)

        return results

    def has_hook(self, hook_name: str) -> bool:
        """Check if any plugin provides a given hook."""
        return bool(self._hooks.get(hook_name))

    def hook_names(self) -> List[str]:
        """Return all registered hook names."""
        return list(self._hooks.keys())

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    @property
    def hook_count(self) -> int:
        return sum(len(hooks) for hooks in self._hooks.values())
