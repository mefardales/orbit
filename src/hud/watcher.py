"""
HudWatcher — continuous polling loop for the orbit HUD.

Polls .orbit/state/ every interval_ms milliseconds and re-renders the
status line in place using cursor-home + clear-line ANSI sequences.
Handles SIGINT gracefully so the terminal is always left clean.
"""

from __future__ import annotations

import json
import signal
import sys
import time
from typing import Optional

from .renderer import CLEAR_LINE, CURSOR_HOME, HIDE_CURSOR, SHOW_CURSOR, HudRenderer, Preset
from .state_reader import read_all_state


class HudWatcher:
    """
    Continuous HUD polling loop.

    Args:
        cwd:         Project root to read state from.
        interval_ms: Poll interval in milliseconds.
        preset:      Render preset ("minimal", "focused", "full").
        json_output: If True, emit JSON to stdout once and exit.
    """

    def __init__(
        self,
        cwd: Optional[str] = None,
        interval_ms: int = 1000,
        preset: Preset = "focused",
        json_output: bool = False,
    ) -> None:
        self.cwd = cwd
        self.interval_ms = max(100, interval_ms)
        self.preset = preset
        self.json_output = json_output
        self._renderer = HudRenderer()
        self._running = False

    # ------------------------------------------------------------------
    # One-shot JSON mode
    # ------------------------------------------------------------------

    def print_json(self) -> None:
        """Read state once and emit JSON to stdout."""
        state = read_all_state(self.cwd)
        print(self._renderer.render_json(state))

    # ------------------------------------------------------------------
    # Watch loop
    # ------------------------------------------------------------------

    def run_watch(self, interval_ms: Optional[int] = None) -> None:
        """
        Start the continuous polling loop.

        Installs a SIGINT handler so Ctrl-C cleans up the terminal properly
        before exiting.  The loop overwrites the status line in place so the
        terminal does not scroll.
        """
        effective_interval = (interval_ms or self.interval_ms) / 1000.0
        self._running = True
        _orig_sigint = signal.getsignal(signal.SIGINT)

        def _stop(signum, frame):
            self._running = False

        signal.signal(signal.SIGINT, _stop)

        # Hide cursor for cleaner display.
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()

        try:
            while self._running:
                self._tick()
                # Sleep in small increments so SIGINT is processed promptly.
                deadline = time.monotonic() + effective_interval
                while self._running and time.monotonic() < deadline:
                    time.sleep(0.05)
        finally:
            # Restore terminal.
            sys.stdout.write(SHOW_CURSOR)
            # Move to a clean line.
            sys.stdout.write("\n")
            sys.stdout.flush()
            signal.signal(signal.SIGINT, _orig_sigint)

    def _tick(self) -> None:
        """Read state, render, and overwrite the current terminal line."""
        try:
            state = read_all_state(self.cwd)
            rendered = self._renderer.render(state, preset=self.preset)
        except Exception as exc:
            rendered = f"[HUD error: {exc}]"

        # For "full" preset the output spans multiple lines — we clear the
        # screen instead of just the current line.
        if self.preset == "full":
            sys.stdout.write("\033[2J" + CURSOR_HOME)  # clear screen
        else:
            sys.stdout.write(CURSOR_HOME + CLEAR_LINE)

        sys.stdout.write(rendered)
        sys.stdout.flush()
