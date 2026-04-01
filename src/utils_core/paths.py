"""Path utilities for pyclaude."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def get_pyclaude_home(override: Optional[str] = None) -> Path:
    """Return the pyclaude home directory, creating it if necessary.

    Checks PYCLAUDE_HOME env var first, then falls back to ~/.pyclaude.
    """
    if override:
        home = Path(override)
    else:
        home = Path(os.environ.get("PYCLAUDE_HOME", str(Path.home() / ".pyclaude")))
    home.mkdir(parents=True, exist_ok=True)
    return home


def get_state_dir(subdir: Optional[str] = None) -> Path:
    """Return the state directory under pyclaude home.

    Optionally creates and returns a named subdirectory.
    """
    state = get_pyclaude_home() / "state"
    if subdir:
        state = state / subdir
    state.mkdir(parents=True, exist_ok=True)
    return state


def get_package_root() -> Path:
    """Return the root directory of the pyclaude package."""
    return Path(__file__).resolve().parent.parent


def codex_agents_dir(base: Optional[Path] = None) -> Path:
    """Return the codex agents directory, creating it if necessary."""
    root = base or get_pyclaude_home()
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
