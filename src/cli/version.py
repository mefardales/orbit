"""Version reporting, mirrors src/cli/version.ts."""

from __future__ import annotations

import json
from pathlib import Path

from .constants import CLI_NAME


def _read_package_version() -> str:
    """Read version from the nearest package.json, falling back to '0.0.0-dev'."""
    candidates = [
        Path(__file__).resolve().parents[2] / 'package.json',
        Path.cwd() / 'package.json',
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                return data.get('version', '0.0.0-dev')
            except (json.JSONDecodeError, OSError):
                continue
    return '0.0.0-dev'


def get_version() -> str:
    """Return the current CLI version string."""
    return _read_package_version()


def print_version() -> None:
    """Print version info to stdout."""
    ver = get_version()
    print(f'{CLI_NAME} {ver}')
