"""ANSI color support for the HUD."""

from __future__ import annotations

from typing import Dict

# ANSI escape codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
UNDERLINE = "\033[4m"

COLOR_MAP: Dict[str, str] = {
    "default": "\033[0m",
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
    "gray": "\033[90m",
}


def colorize(text: str, color: str = "default", bold: bool = False) -> str:
    """Apply ANSI color (and optional bold) to text."""
    code = COLOR_MAP.get(color, COLOR_MAP["default"])
    prefix = BOLD if bold else ""
    return f"{prefix}{code}{text}{RESET}"
