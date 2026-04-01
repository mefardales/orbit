"""Temporary file cleanup, mirrors src/cli/cleanup.ts."""

from __future__ import annotations

import shutil

from .constants import DEFAULT_CACHE_DIR, EXIT_OK


def run_cleanup() -> int:
    """Remove transient caches and temp files."""
    if DEFAULT_CACHE_DIR.is_dir():
        shutil.rmtree(DEFAULT_CACHE_DIR)
        print(f'Removed {DEFAULT_CACHE_DIR}')
    else:
        print('Nothing to clean.')
    return EXIT_OK
