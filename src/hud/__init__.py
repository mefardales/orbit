"""
hud - Heads-up display for orbit.

Provides:
  - In-process HudState management (entries, visibility, persistence).
  - HudRuntimeState reader that aggregates .orbit/state/ JSON files.
  - HudRenderer for minimal / focused / full / JSON output.
  - HudWatcher for continuous --watch polling.
"""

from .types import HudEntry, HudState, HudConfig
from .colors import colorize, COLOR_MAP
from .render import render_hud, render_compact, render_full, format_entry
from .state import get_hud_state, update_hud, clear_hud, toggle_visibility

# New subsystems
from .state_reader import (
    HudRuntimeState,
    ModeState,
    TokenUsage,
    read_all_state,
    KNOWN_MODES,
)
from .renderer import HudRenderer
from .watcher import HudWatcher

__all__ = [
    # Legacy in-process HUD
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
    # Runtime state reader
    "HudRuntimeState",
    "ModeState",
    "TokenUsage",
    "read_all_state",
    "KNOWN_MODES",
    # Renderer + watcher
    "HudRenderer",
    "HudWatcher",
]
