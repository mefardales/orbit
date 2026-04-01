from __future__ import annotations
from .types import HudState, HudEntry

_current_state = HudState()

def get_hud_state() -> HudState:
    return _current_state

def update_hud_entry(key: str, label: str, value: str, color: str = 'default') -> None:
    for entry in _current_state.entries:
        if entry.key == key:
            entry.value = value
            entry.color = color
            return
    _current_state.entries.append(HudEntry(key=key, label=label, value=value, color=color))
