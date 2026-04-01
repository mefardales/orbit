"""Welcome screen with logo, version info, and stats."""

from __future__ import annotations

import shutil
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

LOGO = r"""
                      _                 _
  _ __  _   _  ___| | __ _ _   _  __| | ___
 | '_ \| | | |/ __| |/ _` | | | |/ _` |/ _ \
 | |_) | |_| | (__| | (_| | |_| | (_| |  __/
 | .__/ \__, |\___|_|\__,_|\__,_|\__,_|\___|
 |_|    |___/
"""

COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "magenta": "\033[35m",
    "blue": "\033[34m",
    "white": "\033[37m",
}


@dataclass
class WelcomeStats:
    """Statistics displayed on the welcome screen."""

    sessions_total: int = 0
    tasks_completed: int = 0
    uptime_seconds: float = 0.0
    version: str = "0.1.0"
    last_session: Optional[datetime] = None
    agents_available: int = 0
    plugins_loaded: int = 0


def _center(text: str, width: int) -> str:
    """Center text within a given width."""
    lines = text.split("\n")
    return "\n".join(line.center(width) for line in lines)


def _format_uptime(seconds: float) -> str:
    """Format seconds into a human-readable uptime string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h"
    days = hours / 24
    return f"{days:.1f}d"


def _build_stats_block(stats: WelcomeStats) -> str:
    """Build the stats display block."""
    c = COLORS
    lines = [
        f"  {c['cyan']}Version:{c['reset']}  {c['bold']}{stats.version}{c['reset']}",
        f"  {c['cyan']}Sessions:{c['reset']} {stats.sessions_total}",
        f"  {c['cyan']}Tasks:{c['reset']}    {stats.tasks_completed} completed",
        f"  {c['cyan']}Agents:{c['reset']}   {stats.agents_available} available",
        f"  {c['cyan']}Plugins:{c['reset']}  {stats.plugins_loaded} loaded",
        f"  {c['cyan']}Uptime:{c['reset']}   {_format_uptime(stats.uptime_seconds)}",
    ]
    if stats.last_session:
        ts = stats.last_session.strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {c['cyan']}Last session:{c['reset']} {ts}")
    return "\n".join(lines)


def _horizontal_rule(width: int) -> str:
    """Draw a horizontal rule."""
    return COLORS["dim"] + "\u2500" * width + COLORS["reset"]


def render_welcome_screen(
    stats: Optional[WelcomeStats] = None,
    use_color: bool = True,
    width: Optional[int] = None,
) -> str:
    """Render the full welcome screen.

    Args:
        stats: Optional statistics to display. Defaults to empty stats.
        use_color: Whether to include ANSI color codes.
        width: Terminal width override. Defaults to detected terminal width.

    Returns:
        The rendered welcome screen as a string.
    """
    if stats is None:
        stats = WelcomeStats()
    if width is None:
        width = shutil.get_terminal_size((80, 24)).columns

    c = COLORS if use_color else {k: "" for k in COLORS}

    parts: list[str] = [
        "",
        c["magenta"] + _center(LOGO.strip(), width) + c["reset"],
        "",
        _horizontal_rule(width),
        "",
        _build_stats_block(stats) if use_color else _build_stats_block(stats),
        "",
        _horizontal_rule(width),
        "",
        _center(
            f"{c['dim']}Type {c['green']}help{c['dim']} to get started "
            f"or {c['green']}Ctrl+?{c['dim']} for keybindings{c['reset']}",
            width + 30,  # account for escape codes
        ),
        "",
    ]
    output = "\n".join(parts)
    if not use_color:
        # strip any lingering escape codes
        import re
        output = re.sub(r"\033\[[0-9;]*m", "", output)
    return output
