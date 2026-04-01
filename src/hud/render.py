"""Rendering functions for the heads-up display."""

from __future__ import annotations

import time
from typing import List

from .colors import colorize, BOLD, DIM, RESET
from .types import HudEntry, HudState


def format_entry(entry: HudEntry, width: int = 60) -> str:
    """Format a single HUD entry as a display string."""
    icon_part = f"{entry.icon} " if entry.icon else ""
    key_part = colorize(entry.key, "cyan", bold=True)
    val_part = colorize(entry.value, entry.color)
    line = f"  {icon_part}{key_part}: {val_part}"
    age = entry.age
    if age < 60:
        age_str = f"{age:.0f}s"
    elif age < 3600:
        age_str = f"{age / 60:.0f}m"
    else:
        age_str = f"{age / 3600:.1f}h"
    age_display = f"{DIM}({age_str} ago){RESET}"
    return f"{line}  {age_display}"


def render_compact(state: HudState) -> str:
    """Render HUD in compact single-line-per-entry mode."""
    if not state.visible or not state.entries:
        return ""
    entries = state.sorted_entries()[: state.config.max_entries]
    lines = [format_entry(e, state.config.width) for e in entries]
    state.last_render = time.time()
    return "\n".join(lines)


def render_full(state: HudState) -> str:
    """Render HUD with a bordered box."""
    if not state.visible or not state.entries:
        return ""
    w = state.config.width
    border = colorize("+" + "-" * (w - 2) + "+", "gray")
    title = colorize("| HUD", "bright_white", bold=True)
    padding = " " * (w - 7) + colorize("|", "gray")
    header = f"{title}{padding}"
    entries = state.sorted_entries()[: state.config.max_entries]
    body_lines: List[str] = []
    for entry in entries:
        line = format_entry(entry, w - 4)
        body_lines.append(line)
    state.last_render = time.time()
    parts = [border, header, border]
    parts.extend(body_lines)
    parts.append(border)
    return "\n".join(parts)


def render_hud(state: HudState) -> str:
    """Render the HUD using the configured display mode."""
    if not state.visible:
        return ""
    if state.config.compact:
        return render_compact(state)
    return render_full(state)
