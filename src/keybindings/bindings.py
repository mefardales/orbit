"""KeyBinding dataclass and registry for managing keyboard shortcuts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class KeyBinding:
    """A keyboard shortcut binding."""

    key: str                     # e.g. "ctrl+c", "alt+h", "f1"
    action: str                  # action identifier e.g. "quit", "help"
    description: str = ""
    category: str = "general"
    enabled: bool = True

    @property
    def modifiers(self) -> list[str]:
        """Extract modifier keys (ctrl, alt, shift, meta)."""
        parts = self.key.lower().split("+")
        return [p for p in parts[:-1] if p in ("ctrl", "alt", "shift", "meta", "cmd")]

    @property
    def base_key(self) -> str:
        """Extract the base key without modifiers."""
        parts = self.key.lower().split("+")
        return parts[-1]

    def matches(self, key_event: str) -> bool:
        """Check if a key event string matches this binding."""
        return self._normalize(key_event) == self._normalize(self.key)

    @staticmethod
    def _normalize(key: str) -> str:
        """Normalize a key string for comparison."""
        parts = key.lower().strip().split("+")
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) > 1:
            mods = sorted(parts[:-1])
            return "+".join(mods) + "+" + parts[-1]
        return parts[0] if parts else ""


class KeyBindingRegistry:
    """Registry for keyboard shortcuts with lookup and persistence."""

    def __init__(self) -> None:
        self._bindings: dict[str, KeyBinding] = {}
        self._action_handlers: dict[str, Callable[[], Any]] = {}

    def register(self, binding: KeyBinding) -> None:
        """Register a keybinding. Overwrites if key already registered."""
        normalized = binding._normalize(binding.key)
        self._bindings[normalized] = binding

    def unregister(self, key: str) -> bool:
        """Remove a keybinding by key string. Returns True if removed."""
        normalized = KeyBinding._normalize(key)
        return self._bindings.pop(normalized, None) is not None

    def resolve(self, key_event: str) -> Optional[KeyBinding]:
        """Find the binding that matches a key event, or None."""
        normalized = KeyBinding._normalize(key_event)
        binding = self._bindings.get(normalized)
        if binding and binding.enabled:
            return binding
        return None

    def bind_handler(self, action: str, handler: Callable[[], Any]) -> None:
        """Associate an action with a callable handler."""
        self._action_handlers[action] = handler

    def execute(self, key_event: str) -> Optional[Any]:
        """Resolve a key event and execute the associated handler if any."""
        binding = self.resolve(key_event)
        if binding and binding.action in self._action_handlers:
            return self._action_handlers[binding.action]()
        return None

    def list_all(self, category: Optional[str] = None) -> list[KeyBinding]:
        """List all registered bindings, optionally filtered by category."""
        bindings = list(self._bindings.values())
        if category:
            bindings = [b for b in bindings if b.category == category]
        return sorted(bindings, key=lambda b: (b.category, b.key))

    def categories(self) -> list[str]:
        """List all unique categories."""
        return sorted({b.category for b in self._bindings.values()})

    def load_from_config(self, path: Path) -> int:
        """Load bindings from a JSON config file. Returns count loaded."""
        if not path.exists():
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for entry in data.get("keybindings", []):
            binding = KeyBinding(
                key=entry["key"],
                action=entry["action"],
                description=entry.get("description", ""),
                category=entry.get("category", "general"),
                enabled=entry.get("enabled", True),
            )
            self.register(binding)
            count += 1
        return count

    def save_to_config(self, path: Path) -> None:
        """Save all bindings to a JSON config file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        for binding in self.list_all():
            entries.append({
                "key": binding.key,
                "action": binding.action,
                "description": binding.description,
                "category": binding.category,
                "enabled": binding.enabled,
            })
        path.write_text(
            json.dumps({"keybindings": entries}, indent=2) + "\n",
            encoding="utf-8",
        )

    def __len__(self) -> int:
        return len(self._bindings)

    def __contains__(self, key: str) -> bool:
        return KeyBinding._normalize(key) in self._bindings


def default_bindings() -> KeyBindingRegistry:
    """Create a registry pre-loaded with default keybindings."""
    registry = KeyBindingRegistry()
    defaults = [
        KeyBinding("ctrl+c", "quit", "Exit pyclaude", "general"),
        KeyBinding("ctrl+d", "quit", "Exit pyclaude (EOF)", "general"),
        KeyBinding("ctrl+l", "clear", "Clear screen", "general"),
        KeyBinding("ctrl+?", "help", "Show help", "general"),
        KeyBinding("f1", "help", "Show help", "general"),
        KeyBinding("ctrl+r", "search_history", "Search command history", "navigation"),
        KeyBinding("ctrl+p", "prev_command", "Previous command", "navigation"),
        KeyBinding("ctrl+n", "next_command", "Next command", "navigation"),
        KeyBinding("ctrl+a", "line_start", "Move to line start", "editing"),
        KeyBinding("ctrl+e", "line_end", "Move to line end", "editing"),
        KeyBinding("ctrl+k", "kill_line", "Kill to end of line", "editing"),
        KeyBinding("ctrl+u", "kill_line_back", "Kill to start of line", "editing"),
        KeyBinding("ctrl+w", "kill_word", "Kill previous word", "editing"),
        KeyBinding("ctrl+t", "new_task", "Create new task", "tasks"),
        KeyBinding("ctrl+g", "cancel", "Cancel current operation", "general"),
        KeyBinding("alt+d", "dashboard", "Toggle dashboard", "views"),
        KeyBinding("alt+v", "voice_toggle", "Toggle voice input", "input"),
        KeyBinding("escape", "vim_normal", "Enter vim normal mode", "vim"),
    ]
    for b in defaults:
        registry.register(b)
    return registry
