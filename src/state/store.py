"""Reactive state store with subscriptions and snapshots."""

from __future__ import annotations

import copy
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

Listener = Callable[[str, Any, Any], None]  # (key, old_value, new_value)


class StateStore:
    """Thread-safe key-value state store with change subscriptions.

    Supports nested key paths using dot notation (e.g., "ui.theme.name").
    """

    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        self._state: Dict[str, Any] = initial or {}
        self._listeners: Dict[str, List[Listener]] = {}
        self._global_listeners: List[Listener] = []
        self._lock = threading.RLock()
        self._history: List[Dict[str, Any]] = []
        self._max_history = 50

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key. Supports dot notation for nested access."""
        with self._lock:
            return self._deep_get(self._state, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value by key. Notifies subscribers if the value changed."""
        with self._lock:
            old = self._deep_get(self._state, key)
            self._deep_set(self._state, key, value)
            new = value

        if old != new:
            self._notify(key, old, new)

    def delete(self, key: str) -> bool:
        """Delete a key from state. Returns True if it existed."""
        with self._lock:
            old = self._deep_get(self._state, key)
            if old is None and key not in self._state:
                return False
            self._deep_delete(self._state, key)

        self._notify(key, old, None)
        return True

    def subscribe(self, key: str, listener: Listener) -> Callable[[], None]:
        """Subscribe to changes on a specific key. Returns unsubscribe function."""
        with self._lock:
            self._listeners.setdefault(key, []).append(listener)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._listeners[key].remove(listener)
                except (KeyError, ValueError):
                    pass

        return unsubscribe

    def subscribe_all(self, listener: Listener) -> Callable[[], None]:
        """Subscribe to all state changes. Returns unsubscribe function."""
        with self._lock:
            self._global_listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._global_listeners.remove(listener)
                except ValueError:
                    pass

        return unsubscribe

    def snapshot(self) -> Dict[str, Any]:
        """Return a deep copy of the current state."""
        with self._lock:
            return copy.deepcopy(self._state)

    def restore(self, snapshot: Dict[str, Any]) -> None:
        """Restore state from a snapshot."""
        with self._lock:
            self._push_history()
            self._state = copy.deepcopy(snapshot)

    def keys(self) -> List[str]:
        """Return top-level keys."""
        with self._lock:
            return list(self._state.keys())

    def _notify(self, key: str, old: Any, new: Any) -> None:
        with self._lock:
            specific = list(self._listeners.get(key, []))
            global_l = list(self._global_listeners)

        for listener in specific:
            try:
                listener(key, old, new)
            except Exception as e:
                logger.error("Listener error for key %s: %s", key, e)

        for listener in global_l:
            try:
                listener(key, old, new)
            except Exception as e:
                logger.error("Global listener error: %s", e)

    def _push_history(self) -> None:
        snap = copy.deepcopy(self._state)
        self._history.append(snap)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def undo(self) -> bool:
        """Revert to the previous state. Returns False if no history."""
        with self._lock:
            if not self._history:
                return False
            self._state = self._history.pop()
            return True

    @staticmethod
    def _deep_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
        parts = key.split(".")
        current: Any = d
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return default
            else:
                return default
        return current

    @staticmethod
    def _deep_set(d: Dict[str, Any], key: str, value: Any) -> None:
        parts = key.split(".")
        current = d
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    @staticmethod
    def _deep_delete(d: Dict[str, Any], key: str) -> None:
        parts = key.split(".")
        current = d
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                return
            current = current[part]
        current.pop(parts[-1], None)
