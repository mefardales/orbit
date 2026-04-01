"""
HudRenderer — converts HudRuntimeState into formatted terminal output.

Presets:
  minimal  — active mode names only.
  focused  — modes + token display.
  full     — bordered box with all details.

Color coding:
  green  — token usage < 70 %.
  yellow — 70 % ≤ usage < 90 %.
  red    — usage ≥ 90 %.

Token abbreviation: 45000 → "45k", 1200000 → "1.2M".
JSON output: machine-readable dict.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .colors import BOLD, DIM, RESET, colorize
from .state_reader import HudRuntimeState, ModeState, TokenUsage

# ---------------------------------------------------------------------------
# ANSI cursor helpers
# ---------------------------------------------------------------------------

CURSOR_HOME = "\033[H"
CLEAR_LINE = "\033[2K"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


# ---------------------------------------------------------------------------
# Color thresholds
# ---------------------------------------------------------------------------

def _token_color(fraction: float) -> str:
    if fraction >= 0.90:
        return "red"
    if fraction >= 0.70:
        return "yellow"
    return "green"


def _mode_color(mode: ModeState) -> str:
    return "bright_green" if mode.active else "gray"


# ---------------------------------------------------------------------------
# Preset rendering
# ---------------------------------------------------------------------------

Preset = str   # "minimal" | "focused" | "full"


class HudRenderer:
    """
    Render HudRuntimeState to a string in various formats and presets.
    """

    # ------------------------------------------------------------------ #
    # Compact status line (single line, ANSI)
    # ------------------------------------------------------------------ #

    def render_compact(self, state: HudRuntimeState) -> str:
        """
        Single-line status bar.

        Format:  ORBIT  [ralph team]  45k / 200k  12m34s
        """
        parts: List[str] = []

        # Prefix badge.
        parts.append(colorize("ORBIT", "bright_cyan", bold=True))

        # Active modes.
        active = state.active_modes
        if active:
            mode_str = " ".join(
                colorize(m.name, _mode_color(m), bold=m.active)
                for m in state.modes
            )
            parts.append(f"[{mode_str}]")
        else:
            parts.append(colorize("[idle]", "gray"))

        # Tokens.
        tok = state.tokens
        if tok.used > 0:
            color = _token_color(tok.fraction)
            parts.append(colorize(tok.display, color))

        # Session duration.
        dur = state.session_duration_display
        if dur != "—":
            parts.append(colorize(dur, "gray"))

        return "  ".join(parts)

    # ------------------------------------------------------------------ #
    # Full bordered box
    # ------------------------------------------------------------------ #

    def render_full(self, state: HudRuntimeState) -> str:
        """
        Multi-line bordered box with all available details.
        """
        w = 60
        border = colorize("+" + "─" * (w - 2) + "+", "gray")
        title = colorize("  ORBIT HUD", "bright_white", bold=True)
        title_line = colorize("|", "gray") + title + " " * (w - 13) + colorize("|", "gray")

        lines: List[str] = [border, title_line, border]

        # Modes section.
        lines.append(colorize("|  MODES", "cyan", bold=True) + " " * (w - 9) + colorize("|", "gray"))
        if state.modes:
            for mode in state.modes:
                status = "active" if mode.active else "idle"
                phase_str = f" [{mode.phase}]" if mode.phase else ""
                label = colorize(f"  {mode.name}", _mode_color(mode), bold=mode.active)
                detail = colorize(f"{status}{phase_str}", "gray")
                content = f"{label}: {detail}"
                # Pad to fill the box width.
                visible_len = len(f"  {mode.name}: {status}{phase_str}") + 2
                padding = max(1, w - visible_len - 2)
                lines.append(
                    colorize("|", "gray") + content + " " * padding + colorize("|", "gray")
                )
        else:
            lines.append(colorize("|  ", "gray") + colorize("no modes detected", "gray") + " " * (w - 20) + colorize("|", "gray"))

        lines.append(border)

        # Tokens section.
        tok = state.tokens
        if tok.used > 0:
            lines.append(colorize("|  TOKENS", "cyan", bold=True) + " " * (w - 10) + colorize("|", "gray"))
            color = _token_color(tok.fraction)
            pct = f"{tok.fraction * 100:.0f}%"
            tok_line = f"  {colorize(tok.display, color)}  {colorize(pct, color)}"
            bar = _render_progress_bar(tok.fraction, width=20, color=color)
            content = f"{tok_line}  {bar}"
            visible_len = len(f"  {tok.display}  {pct}  ")
            padding = max(1, w - visible_len - 22)
            lines.append(
                colorize("|", "gray") + content + " " * padding + colorize("|", "gray")
            )
            lines.append(border)

        # Session duration.
        dur = state.session_duration_display
        if dur != "—":
            dur_line = f"  Session: {dur}"
            padding = max(1, w - len(dur_line) - 2)
            lines.append(
                colorize("|", "gray")
                + colorize(dur_line, "gray")
                + " " * padding
                + colorize("|", "gray")
            )
            lines.append(border)

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # JSON output
    # ------------------------------------------------------------------ #

    def render_json(self, state: HudRuntimeState) -> str:
        """Machine-readable JSON snapshot."""
        d: Dict[str, Any] = {
            "modes": [
                {
                    "name": m.name,
                    "active": m.active,
                    "phase": m.phase,
                    "started_at": m.started_at,
                    "tokens_used": m.tokens_used,
                    "tokens_limit": m.tokens_limit,
                }
                for m in state.modes
            ],
            "tokens": {
                "used": state.tokens.used,
                "limit": state.tokens.limit,
                "fraction": round(state.tokens.fraction, 4),
                "display": state.tokens.display,
            },
            "session_duration_s": state.session_duration_s,
            "session_duration_display": state.session_duration_display,
            "cwd": state.cwd,
        }
        return json.dumps(d, indent=2)

    # ------------------------------------------------------------------ #
    # Preset dispatch
    # ------------------------------------------------------------------ #

    def render(self, state: HudRuntimeState, preset: Preset = "focused") -> str:
        """
        Render state using a named preset.

        Presets:
          minimal  — mode names only (compact line).
          focused  — modes + tokens (compact line).
          full     — bordered box with all details.
        """
        if preset == "full":
            return self.render_full(state)
        if preset == "minimal":
            return self._render_minimal(state)
        # "focused" is the default compact line.
        return self.render_compact(state)

    def _render_minimal(self, state: HudRuntimeState) -> str:
        """Only show active mode names."""
        active = state.active_modes
        if not active:
            return colorize("ORBIT  [idle]", "gray")
        mode_str = " ".join(colorize(m.name, "bright_green", bold=True) for m in active)
        return colorize("ORBIT", "bright_cyan", bold=True) + f"  [{mode_str}]"


# ---------------------------------------------------------------------------
# Progress bar helper
# ---------------------------------------------------------------------------

def _render_progress_bar(fraction: float, width: int = 20, color: str = "green") -> str:
    filled = int(fraction * width)
    empty = width - filled
    bar = colorize("█" * filled, color) + colorize("░" * empty, "gray")
    return f"[{bar}]"
