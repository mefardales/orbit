"""Path utilities for orbit."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def get_orbit_home(override: Optional[str] = None) -> Path:
    """Return the orbit home directory, creating it if necessary.

    Checks ORBIT_HOME env var first, then falls back to ~/.orbit.
    """
    if override:
        home = Path(override)
    else:
        home = Path(os.environ.get("ORBIT_HOME", str(Path.home() / ".orbit")))
    home.mkdir(parents=True, exist_ok=True)
    return home


def get_state_dir(subdir: Optional[str] = None) -> Path:
    """Return the state directory under orbit home.

    Optionally creates and returns a named subdirectory.
    """
    state = get_orbit_home() / "state"
    if subdir:
        state = state / subdir
    state.mkdir(parents=True, exist_ok=True)
    return state


def get_package_root() -> Path:
    """Return the root directory of the orbit package."""
    return Path(__file__).resolve().parent.parent


def codex_agents_dir(base: Optional[Path] = None) -> Path:
    """Return the codex agents directory, creating it if necessary."""
    root = base or get_orbit_home()
    agents = root / "codex_agents"
    agents.mkdir(parents=True, exist_ok=True)
    return agents


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists and return it.

    Works for both files (ensures parent) and directories.
    """
    if path.suffix:
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True)
    return path
