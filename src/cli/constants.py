"""CLI constants mirroring src/cli/constants.ts."""

from __future__ import annotations

from pathlib import Path

CLI_NAME = 'omx'
CLI_VERSION_FILE = 'package.json'

DEFAULT_CONFIG_DIR = Path.home() / '.config' / CLI_NAME
DEFAULT_DATA_DIR = Path.home() / '.local' / 'share' / CLI_NAME
DEFAULT_CACHE_DIR = Path.home() / '.cache' / CLI_NAME

# Exit codes
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

# Colour palette used by the HUD / spinner (ANSI 256-colour indices).
COLOR_PRIMARY = 33    # blue
COLOR_SUCCESS = 34    # green
COLOR_WARNING = 214   # orange
COLOR_ERROR = 196     # red
COLOR_MUTED = 245     # grey
