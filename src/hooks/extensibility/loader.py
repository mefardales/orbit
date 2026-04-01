"""
Hook Plugin Loader.

Discovers, validates, and loads hook plugins from the .omx/hooks/ directory.
Plugins are Python .py files that export an `on_hook_event` function.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from .types import HookPluginDescriptor

HOOK_PLUGIN_ENABLE_ENV = "OMX_HOOK_PLUGINS"
HOOK_PLUGIN_TIMEOUT_ENV = "OMX_HOOK_PLUGIN_TIMEOUT_MS"

# Pattern to detect on_hook_event export in Python files
ON_HOOK_EVENT_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:async\s+)?def\s+on_hook_event\b"
    r"|(?:^|\n)\s*on_hook_event\s*=",
    re.MULTILINE,
)


def _sanitize_plugin_id(file_name: str) -> str:
    """Sanitize a filename into a valid plugin ID."""
    stem = Path(file_name).stem
    normalized = re.sub(r"[^a-z0-9_-]+", "-", stem.lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "plugin"


def _short_file_hash(file_name: str) -> str:
    """Generate a short hash for collision disambiguation."""
    return hashlib.sha256(file_name.encode()).hexdigest()[:8]


def _read_timeout(raw: Optional[str], fallback: int) -> int:
    """Parse and clamp a timeout value from an environment variable."""
    if not raw:
        return fallback
    try:
        parsed = int(float(raw))
    except (ValueError, TypeError):
        return fallback
    if parsed < 100:
        return 100
    if parsed > 60_000:
        return 60_000
    return parsed


def hooks_dir(cwd: str) -> Path:
    """Return the hooks plugin directory path."""
    return Path(cwd) / ".omx" / "hooks"


def is_hook_plugins_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    """
    Check if hook plugins are enabled.
    Plugins are ON by default -- only disable if explicitly opted out.
    """
    if env is None:
        env = dict(os.environ)
    raw = env.get(HOOK_PLUGIN_ENABLE_ENV, "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    return True


def resolve_hook_plugin_timeout_ms(
    env: Optional[Dict[str, str]] = None,
    fallback: int = 1500,
) -> int:
    """Resolve the plugin timeout from environment variable."""
    if env is None:
        env = dict(os.environ)
    return _read_timeout(env.get(HOOK_PLUGIN_TIMEOUT_ENV), fallback)


async def ensure_hooks_dir(cwd: str) -> Path:
    """Ensure the hooks directory exists and return its path."""
    d = hooks_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _validate_plugin_export(plugin_path: str) -> dict:
    """Validate that a plugin file exports on_hook_event."""
    try:
        source = Path(plugin_path).read_text()
        if not ON_HOOK_EVENT_PATTERN.search(source):
            return {"valid": False, "reason": "missing_on_hook_event_export"}
        return {"valid": True}
    except OSError as e:
        return {"valid": False, "reason": str(e)}


async def discover_hook_plugins(cwd: str) -> List[HookPluginDescriptor]:
    """
    Discover hook plugins in the .omx/hooks/ directory.
    Returns descriptors for all .py files found (without validation).
    """
    d = hooks_dir(cwd)
    if not d.exists():
        return []

    try:
        names = sorted(d.iterdir())
    except OSError:
        return []

    discovered: List[dict] = []
    for p in names:
        if not p.suffix == ".py" or not p.is_file():
            continue
        if p.name.startswith("__"):
            continue
        discovered.append({
            "id_base": _sanitize_plugin_id(p.name),
            "file": p.name,
            "path": str(p),
        })

    # Handle ID collisions
    id_counts: Dict[str, int] = {}
    for plugin in discovered:
        id_counts[plugin["id_base"]] = id_counts.get(plugin["id_base"], 0) + 1

    plugins: List[HookPluginDescriptor] = []
    for plugin in discovered:
        has_collision = id_counts.get(plugin["id_base"], 0) > 1
        plugin_id = (
            f"{plugin['id_base']}-{_short_file_hash(plugin['file'])}"
            if has_collision
            else plugin["id_base"]
        )
        plugins.append(HookPluginDescriptor(
            id=plugin_id,
            name=plugin_id,
            file=plugin["file"],
            path=plugin["path"],
            file_path=plugin["path"],
            file_name=plugin["file"],
            valid=True,
        ))

    plugins.sort(key=lambda p: p.file)
    return plugins


async def load_hook_plugin_descriptors(cwd: str) -> List[HookPluginDescriptor]:
    """Discover and validate all hook plugins."""
    discovered = await discover_hook_plugins(cwd)
    validated: List[HookPluginDescriptor] = []
    for plugin in discovered:
        validation = await _validate_plugin_export(plugin.path)
        validated.append(HookPluginDescriptor(
            id=plugin.id,
            name=plugin.name,
            file=plugin.file,
            path=plugin.path,
            file_path=plugin.file_path,
            file_name=plugin.file_name,
            valid=validation.get("valid", False),
            reason=validation.get("reason"),
        ))
    return validated
