"""
Plugin Loader for orbit hooks.

Discovers plugins in ~/.orbit/plugins/ and .orbit/plugins/ directories.
Each plugin is a Python file with an on_hook_event(event) function.
Validates plugin signatures and caches loaded modules.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Re-use the ORBIT_HOOK_PLUGINS env var (mirrors the extensibility loader's
# OMX_HOOK_PLUGINS but for the outer plugin system).
ORBIT_HOOK_PLUGINS_ENV = "ORBIT_HOOK_PLUGINS"

ON_HOOK_EVENT_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:async\s+)?def\s+on_hook_event\b"
    r"|(?:^|\n)\s*on_hook_event\s*=",
    re.MULTILINE,
)

# Module-level cache: path -> loaded module
_plugin_cache: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _global_plugin_dir() -> Path:
    return Path.home() / ".orbit" / "plugins"


def _local_plugin_dir(cwd: Optional[str] = None) -> Path:
    root = Path(cwd) if cwd else Path.cwd()
    return root / ".orbit" / "plugins"


def _candidate_dirs(cwd: Optional[str] = None) -> List[Path]:
    """Return plugin search directories in priority order (local first)."""
    return [_local_plugin_dir(cwd), _global_plugin_dir()]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_plugin(path: str) -> Tuple[bool, str]:
    """
    Validate that a plugin file is loadable and exports on_hook_event.

    Returns:
        (True, "") on success.
        (False, reason) on failure.
    """
    p = Path(path)
    if not p.exists():
        return False, f"file not found: {path}"
    if not p.is_file():
        return False, f"not a file: {path}"
    if p.suffix != ".py":
        return False, f"not a .py file: {path}"

    try:
        source = p.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"cannot read file: {exc}"

    if not ON_HOOK_EVENT_PATTERN.search(source):
        return False, "missing on_hook_event function or assignment"

    # Try to load the module in a temporary namespace to catch syntax errors.
    spec = importlib.util.spec_from_file_location("_orbit_validate_tmp", path)
    if spec is None or spec.loader is None:
        return False, "importlib could not create module spec"
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    except SyntaxError as exc:
        return False, f"syntax error: {exc}"
    except Exception as exc:
        return False, f"import error: {exc}"

    handler = getattr(mod, "on_hook_event", None)
    if handler is None:
        return False, "on_hook_event not found after import"
    if not callable(handler):
        return False, "on_hook_event is not callable"

    # Signature check: must accept at least one positional parameter (event).
    try:
        sig = inspect.signature(handler)
        params = [
            p for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        ]
        if len(params) < 1:
            return False, "on_hook_event must accept at least one positional argument (event)"
    except (ValueError, TypeError):
        pass  # can't inspect; allow it through

    return True, ""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _discover_in_dir(directory: Path) -> List[Path]:
    """Yield sorted .py plugin files from a directory (non-recursive)."""
    if not directory.exists() or not directory.is_dir():
        return []
    try:
        return sorted(
            p for p in directory.iterdir()
            if p.is_file()
            and p.suffix == ".py"
            and not p.name.startswith("__")
        )
    except OSError:
        return []


def _plugins_enabled() -> bool:
    """
    Check if the ORBIT_HOOK_PLUGINS env var enables plugins.
    Default: disabled (require explicit opt-in).
    """
    import os
    raw = os.environ.get(ORBIT_HOOK_PLUGINS_ENV, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_module(path: Path) -> Any:
    """Load a plugin module, using the cache when possible."""
    key = str(path.resolve())
    if key in _plugin_cache:
        return _plugin_cache[key]

    module_name = f"_orbit_plugin_{path.stem}"
    # Avoid name collisions in sys.modules
    i = 0
    candidate = module_name
    while candidate in sys.modules:
        i += 1
        candidate = f"{module_name}_{i}"
    module_name = candidate

    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create module spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    _plugin_cache[key] = mod
    return mod


def load_plugins(cwd: Optional[str] = None) -> List[Any]:
    """
    Discover and load all valid plugins.

    Searches ~/.orbit/plugins/ and .orbit/plugins/ (local first).
    Plugins that fail validation are silently skipped.

    Returns:
        List of loaded plugin modules (each has an on_hook_event callable).
    """
    import os
    # Config gating: respect ORBIT_HOOK_PLUGINS env var.
    if not _plugins_enabled():
        return []

    seen: Dict[str, bool] = {}
    modules: List[Any] = []

    for directory in _candidate_dirs(cwd):
        for plugin_path in _discover_in_dir(directory):
            key = str(plugin_path.resolve())
            if key in seen:
                continue
            seen[key] = True
            ok, _reason = validate_plugin(str(plugin_path))
            if not ok:
                continue
            try:
                mod = _load_module(plugin_path)
                modules.append(mod)
            except Exception:
                pass

    return modules


def clear_plugin_cache() -> None:
    """Invalidate the loaded-plugin cache (useful in tests)."""
    _plugin_cache.clear()
