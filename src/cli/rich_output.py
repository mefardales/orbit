"""Shared Rich console for all CLI output.

Centralizes console creation with UTF-8 support and consistent theming.
All CLI commands should use `console` from this module instead of print().
"""
from __future__ import annotations

import io
import random
import sys
import threading

from rich.console import Console
from rich.theme import Theme

ORBIT_THEME = Theme({
    "pass": "bold green",
    "fail": "bold red",
    "warn": "bold yellow",
    "info": "bold cyan",
    "dim": "dim",
    "header": "bold",
    "accent": "bold cyan",
    "category.build": "green",
    "category.review": "cyan",
    "category.domain": "yellow",
    "category.product": "magenta",
    "category.coordination": "red",
    "status.active": "green",
    "status.alias": "dim",
    "status.merged": "dim italic",
    "status.internal": "yellow",
})

# ── Orbit-themed spinner messages ──────────────────────────────────────────
# Rotate while waiting for AI response

ORBIT_SPINNER_MESSAGES = [
    "Thinking\u2026",
    "Working\u2026",
    "Writing\u2026",
    "Reading\u2026",
    "Exploring\u2026",
    "Learning\u2026",
    "Planning\u2026",
    "Building\u2026",
    "Creating\u2026",
    "Reviewing\u2026",
    "Preparing\u2026",
    "Searching\u2026",
    "Connecting\u2026",
    "Loading\u2026",
    "Almost\u2026",
]


def get_console() -> Console:
    """Create a Rich console with UTF-8 support on Windows."""
    file = None
    if sys.platform == 'win32':
        try:
            file = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass
    return Console(theme=ORBIT_THEME, file=file, force_terminal=True)


# Singleton console for the CLI
console = get_console()


class OrbitSpinner:
    """Context manager that shows a spinner with rotating Orbit-themed messages.

    Usage::

        with OrbitSpinner(console):
            result = slow_operation()
    """

    def __init__(self, con: Console | None = None, interval: float = 1.8):
        self._console = con or console
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = None

    def __enter__(self):
        messages = list(ORBIT_SPINNER_MESSAGES)
        random.shuffle(messages)
        self._messages = messages
        self._idx = 0

        self._status = self._console.status(
            f"[#ACE1AF]{self._messages[0]}[/]",
            spinner="dots",
        )
        self._status.__enter__()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._rotate, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._status:
            self._status.__exit__(*exc)

    def _rotate(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                break
            self._idx = (self._idx + 1) % len(self._messages)
            if self._status:
                try:
                    self._status.update(f"[#ACE1AF]{self._messages[self._idx]}[/]")
                except Exception:
                    break
