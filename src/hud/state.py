"""State management for the heads-up display."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .types import HudConfig, HudEntry, HudState

_current_state: Optional[HudState] = None
DEFAULT_HUD_PATH = Path.home() / ".orbit" / "hud_state.json"


def get_hud_state(path: Optional[Path] = None) -> HudState:
    """Get the current HUD state, loading from disk if needed."""
    global _current_state
    if _current_state is not None:
        return _current_state
    state_path = path or DEFAULT_HUD_PATH
    if state_path.exists():
        try:
            with open(state_path, "r") as f:
                data = json.load(f)
            entries = [
                HudEntry(**e) for e in data.get("entries", [])
            ]
            config_data = data.get("config", {})
            config = HudConfig(**config_data)
            _current_state = HudState(
                entries=entries,
                config=config,
                visible=data.get("visible", True),
            )
        except (json.JSONDecodeError, TypeError, KeyError):
            _current_state = HudState()
    else:
        _current_state = HudState()
    return _current_state


def _save_state(state: HudState, path: Optional[Path] = None) -> None:
    state_path = path or DEFAULT_HUD_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = {
        "entries": [
            {
                "key": e.key,
                "value": e.value,
                "color": e.color,
                "icon": e.icon,
                "priority": e.priority,
                "timestamp": e.timestamp,
                "metadata": e.metadata,
            }
            for e in state.entries
        ],
        "config": {
            "max_entries": state.config.max_entries,
            "compact": state.config.compact,
            "visible": state.config.visible,
            "refresh_interval": state.config.refresh_interval,
            "default_color": state.config.default_color,
            "width": state.config.width,
        },
        "visible": state.visible,
    }
    with open(state_path, "w") as f:
        json.dump(data, f, indent=2)


def update_hud(
    key: str,
    value: str,
    color: str = "default",
    icon: str = "",
    priority: int = 0,
    path: Optional[Path] = None,
) -> HudState:
    """Add or update an entry in the HUD."""
    state = get_hud_state(path)
    for entry in state.entries:
        if entry.key == key:
            entry.value = value
            entry.color = color
            entry.icon = icon
            entry.priority = priority
            _save_state(state, path)
            return state
    state.entries.append(HudEntry(key=key, value=value, color=color, icon=icon, priority=priority))
    if len(state.entries) > state.config.max_entries:
        state.entries = state.sorted_entries()[: state.config.max_entries]
    _save_state(state, path)
    return state


def clear_hud(path: Optional[Path] = None) -> HudState:
    """Clear all HUD entries."""
    global _current_state
    state = get_hud_state(path)
    state.entries.clear()
    state.last_render = None
    _save_state(state, path)
    return state


def toggle_visibility(path: Optional[Path] = None) -> bool:
    """Toggle HUD visibility. Returns the new visibility state."""
    state = get_hud_state(path)
    state.visible = not state.visible
    state.config.visible = state.visible
    _save_state(state, path)
    return state.visible
