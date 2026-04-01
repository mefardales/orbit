"""Utilities for finding and reading AGENTS.md files."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

AGENTS_FILENAME = "AGENTS.md"
SEARCH_PARENTS_LIMIT = 10


def find_agents_md(start: Optional[Path] = None) -> Optional[Path]:
    """Search upward from start directory for an AGENTS.md file.

    Walks up to SEARCH_PARENTS_LIMIT parent directories looking for
    the file. Returns the path if found, or None.
    """
    current = (start or Path.cwd()).resolve()
    for _ in range(SEARCH_PARENTS_LIMIT):
        candidate = current / AGENTS_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def read_agents_md(start: Optional[Path] = None) -> Optional[str]:
    """Find and read the nearest AGENTS.md file.

    Returns the file contents as a string, or None if not found.
    """
    path = find_agents_md(start)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def has_agents_md(start: Optional[Path] = None) -> bool:
    """Check whether an AGENTS.md file exists in the directory tree."""
    return find_agents_md(start) is not None
