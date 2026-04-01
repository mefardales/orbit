"""
Hook Event Dispatcher.

Dispatches events to registered in-process callbacks and to loaded plugin
modules.  Plugin execution is isolated: a failure in one plugin does not
affect others.  Each plugin call is bounded by a configurable timeout
enforced with a daemon thread (compatible with both sync and async contexts).
"""

from __future__ import annotations

import concurrent.futures
import inspect
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known event names
# ---------------------------------------------------------------------------

KNOWN_EVENTS = frozenset([
    "pre_launch",
    "post_launch",
    "pre_command",
    "post_command",
    "mode_change",
    "error",
    # extensibility framework names (kept for cross-compat)
    "session-start",
    "session-end",
    "session-idle",
    "turn-complete",
    "blocked",
    "finished",
    "failed",
    "retry-needed",
    "pr-created",
    "test-started",
    "test-finished",
    "test-failed",
    "handoff-needed",
    "needs-input",
    "pre-tool-use",
    "post-tool-use",
])

# Default per-plugin timeout in seconds.
DEFAULT_PLUGIN_TIMEOUT_S = 5.0


# ---------------------------------------------------------------------------
# In-process registry
# ---------------------------------------------------------------------------

_registry_lock = threading.Lock()
_registry: Dict[str, List[Callable[..., Any]]] = {}


def register_hook(event_name: str, callback: Callable[..., Any]) -> None:
    """Register a callback for event_name.  Duplicate registrations are ignored."""
    with _registry_lock:
        bucket = _registry.setdefault(event_name, [])
        if callback not in bucket:
            bucket.append(callback)


def unregister_hook(event_name: str, callback: Callable[..., Any]) -> None:
    """Remove a previously registered callback.  No-op if not found."""
    with _registry_lock:
        bucket = _registry.get(event_name, [])
        try:
            bucket.remove(callback)
        except ValueError:
            pass


def _get_callbacks(event_name: str) -> List[Callable[..., Any]]:
    with _registry_lock:
        return list(_registry.get(event_name, []))


def emit(event_name: str, **kwargs: Any) -> List[Any]:
    """
    Fire all in-process callbacks registered for event_name.

    Each callback receives (event_name, payload_dict).  Failures are logged
    and skipped so one bad callback never prevents others from running.

    Returns a list of non-None return values from callbacks.
    """
    payload: Dict[str, Any] = {"event": event_name, **kwargs}
    results: List[Any] = []
    for cb in _get_callbacks(event_name):
        try:
            ret = cb(event_name, payload)
            if ret is not None:
                results.append(ret)
        except Exception:
            logger.exception("hook callback %r raised for event %r", cb, event_name)
    return results


# ---------------------------------------------------------------------------
# Plugin dispatch result
# ---------------------------------------------------------------------------

@dataclass
class PluginDispatchResult:
    plugin_path: str
    ok: bool
    duration_ms: float
    response: Any = None
    error: Optional[str] = None
    timed_out: bool = False


@dataclass
class DispatchResult:
    event_name: str
    payload: Dict[str, Any]
    plugin_results: List[PluginDispatchResult] = field(default_factory=list)
    callback_responses: List[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plugin execution helpers
# ---------------------------------------------------------------------------

def _call_plugin(
    mod: Any,
    payload: Dict[str, Any],
    timeout_s: float,
) -> PluginDispatchResult:
    """
    Call mod.on_hook_event(payload) in a thread with timeout enforcement.

    The result dict or None that the plugin returns is captured as `response`.
    """
    path = getattr(mod, "__file__", repr(mod))
    started = time.monotonic()
    result_container: List[Any] = [None]
    exc_container: List[Optional[Exception]] = [None]

    def _target() -> None:
        try:
            handler = getattr(mod, "on_hook_event")
            ret = handler(payload)
            # Support async handlers by detecting coroutines.
            if inspect.iscoroutine(ret):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Can't block an already-running loop from a thread.
                        # Schedule and detach; we won't await it here.
                        result_container[0] = None
                    else:
                        result_container[0] = loop.run_until_complete(ret)
                except RuntimeError:
                    result_container[0] = None
            else:
                result_container[0] = ret
        except Exception as exc:
            exc_container[0] = exc

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_s)

    elapsed_ms = (time.monotonic() - started) * 1000.0

    if t.is_alive():
        # Thread is still blocked; mark as timed out and move on.
        return PluginDispatchResult(
            plugin_path=path,
            ok=False,
            duration_ms=elapsed_ms,
            timed_out=True,
            error=f"timed out after {timeout_s}s",
        )

    exc = exc_container[0]
    if exc is not None:
        return PluginDispatchResult(
            plugin_path=path,
            ok=False,
            duration_ms=elapsed_ms,
            error=str(exc),
        )

    return PluginDispatchResult(
        plugin_path=path,
        ok=True,
        duration_ms=elapsed_ms,
        response=result_container[0],
    )


# ---------------------------------------------------------------------------
# Public dispatch API
# ---------------------------------------------------------------------------

def dispatch(
    event_name: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    plugins: Optional[List[Any]] = None,
    cwd: Optional[str] = None,
    timeout_s: float = DEFAULT_PLUGIN_TIMEOUT_S,
) -> DispatchResult:
    """
    Dispatch event_name to:
      1. All in-process registered callbacks (via emit).
      2. All loaded plugin modules (parallel, timeout-bounded).

    Args:
        event_name: One of the KNOWN_EVENTS or any custom string.
        payload: Arbitrary dict merged into the event envelope.
        plugins: Pre-loaded plugin modules.  If None, load_plugins() is called.
        cwd: Working directory passed to load_plugins().
        timeout_s: Per-plugin wall-clock timeout in seconds.

    Returns:
        DispatchResult with per-plugin outcomes and in-process responses.
    """
    full_payload: Dict[str, Any] = {"event": event_name, **(payload or {})}

    # In-process callbacks first (fast path).
    callback_responses = emit(event_name, **(payload or {}))

    # Resolve plugin list.
    if plugins is None:
        from .plugin_loader import load_plugins
        plugins = load_plugins(cwd)

    plugin_results: List[PluginDispatchResult] = []

    if plugins:
        # Run plugins concurrently with ThreadPoolExecutor.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(plugins), 8),
            thread_name_prefix="orbit-hook-plugin",
        ) as pool:
            futures = {
                pool.submit(_call_plugin, mod, full_payload, timeout_s): mod
                for mod in plugins
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    plugin_results.append(future.result())
                except Exception as exc:
                    mod = futures[future]
                    path = getattr(mod, "__file__", repr(mod))
                    plugin_results.append(PluginDispatchResult(
                        plugin_path=path,
                        ok=False,
                        duration_ms=0.0,
                        error=f"executor error: {exc}",
                    ))

    return DispatchResult(
        event_name=event_name,
        payload=full_payload,
        plugin_results=plugin_results,
        callback_responses=callback_responses,
    )
