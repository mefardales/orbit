"""hud - Heads-up display for pyclaude."""

from .types import HudEntry, HudState, HudConfig
from .colors import colorize, COLOR_MAP
from .render import render_hud, render_compact, render_full, format_entry
from .state import get_hud_state, update_hud, clear_hud, toggle_visibility

__all__ = [
    "HudEntry",
    "HudState",
    "HudConfig",
    "colorize",
    "COLOR_MAP",
    "render_hud",
    "render_compact",
    "render_full",
    "format_entry",
    "get_hud_state",
    "update_hud",
    "clear_hud",
    "toggle_visibility",
]
