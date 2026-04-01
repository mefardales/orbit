"""Plugin discovery, loading, validation, and lifecycle management."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import Plugin, PluginHook, PluginManifest, PluginState

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""
    pass


class PluginValidationError(Exception):
    """Raised when a plugin fails validation."""
    pass


class PluginLoader:
    """Discovers, loads, validates, and unloads plugins from a directory."""

    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        self.plugin_dirs: List[Path] = plugin_dirs or []
        self._loaded: Dict[str, Plugin] = {}

    def discover(self, directory: Optional[Path] = None) -> List[PluginManifest]:
        """Scan directories for plugin manifests and return them."""
        dirs = [directory] if directory else self.plugin_dirs
        manifests: List[PluginManifest] = []

        for d in dirs:
            if not d.is_dir():
                logger.warning("Plugin directory does not exist: %s", d)
                continue

            for child in d.iterdir():
                if not child.is_dir():
                    continue
                manifest_path = child / MANIFEST_FILENAME
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r") as f:
                            data = json.load(f)
                        manifest = PluginManifest.from_dict(data)
                        manifests.append(manifest)
                        logger.debug("Discovered plugin: %s v%s", manifest.name, manifest.version)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error("Invalid manifest at %s: %s", manifest_path, e)

        return manifests

    def load(self, plugin_path: Path) -> Plugin:
        """Load a plugin from a directory containing a manifest."""
        manifest_path = plugin_path / MANIFEST_FILENAME
        if not manifest_path.exists():
            raise PluginLoadError(f"No manifest found at {manifest_path}")

        with open(manifest_path, "r") as f:
            manifest = PluginManifest.from_dict(json.load(f))

        if manifest.name in self._loaded:
            return self._loaded[manifest.name]

        plugin = Plugin(manifest=manifest, path=plugin_path, state=PluginState.LOADED)

        entry = plugin_path / manifest.entry_point
        if not entry.exists():
            plugin.state = PluginState.ERROR
            plugin.error = f"Entry point not found: {entry}"
            raise PluginLoadError(plugin.error)

        try:
            spec = importlib.util.spec_from_file_location(
                f"orbit_plugin_{manifest.name}", str(entry)
            )
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Cannot create module spec for {entry}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            plugin.module = module
            plugin.state = PluginState.LOADED

            # Collect hooks from the module
            if hasattr(module, "register_hooks"):
                hooks = module.register_hooks()
                if isinstance(hooks, list):
                    plugin.hooks = hooks

        except Exception as e:
            plugin.state = PluginState.ERROR
            plugin.error = str(e)
            raise PluginLoadError(f"Failed to load {manifest.name}: {e}") from e

        self._loaded[manifest.name] = plugin
        logger.info("Loaded plugin: %s v%s", manifest.name, manifest.version)
        return plugin

    def validate(self, plugin: Plugin) -> bool:
        """Validate a loaded plugin meets requirements."""
        errors: List[str] = []

        if not plugin.manifest.name:
            errors.append("Plugin name is required")
        if not plugin.manifest.version:
            errors.append("Plugin version is required")
        if plugin.module is None and plugin.state != PluginState.ERROR:
            errors.append("Plugin module not loaded")

        # Check required hooks are actually provided
        declared = set(plugin.manifest.hooks)
        provided = {h.name for h in plugin.hooks}
        missing = declared - provided
        if missing:
            errors.append(f"Declared hooks not provided: {missing}")

        if errors:
            plugin.state = PluginState.ERROR
            plugin.error = "; ".join(errors)
            logger.error("Validation failed for %s: %s", plugin.name, plugin.error)
            return False

        plugin.state = PluginState.VALIDATED
        return True

    def activate(self, plugin: Plugin) -> bool:
        """Activate a validated plugin."""
        if plugin.state not in (PluginState.VALIDATED, PluginState.ACTIVE):
            logger.error("Cannot activate plugin in state: %s", plugin.state)
            return False
        if plugin.module and hasattr(plugin.module, "activate"):
            try:
                plugin.module.activate(plugin.config)
            except Exception as e:
                plugin.state = PluginState.ERROR
                plugin.error = f"Activation failed: {e}"
                return False
        plugin.state = PluginState.ACTIVE
        return True

    def unload(self, name: str) -> bool:
        """Unload a plugin by name, calling its cleanup if available."""
        plugin = self._loaded.get(name)
        if plugin is None:
            return False

        if plugin.module and hasattr(plugin.module, "deactivate"):
            try:
                plugin.module.deactivate()
            except Exception as e:
                logger.warning("Error during deactivation of %s: %s", name, e)

        mod_name = f"orbit_plugin_{name}"
        sys.modules.pop(mod_name, None)
        plugin.module = None
        plugin.state = PluginState.UNLOADED
        del self._loaded[name]
        logger.info("Unloaded plugin: %s", name)
        return True

    @property
    def loaded_plugins(self) -> Dict[str, Plugin]:
        """Return a copy of the loaded plugins dictionary."""
        return dict(self._loaded)
