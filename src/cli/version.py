"""Version reporting for Orbit."""
from __future__ import annotations

from .constants import CLI_NAME

__version__ = '0.1.0'


def get_version() -> str:
    return __version__


def print_version() -> None:
    print(f'{CLI_NAME} {get_version()}')
