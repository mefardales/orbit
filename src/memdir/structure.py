"""Memory directory structure definitions and utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

MEMDIR_NAME = ".pyclaude"

MEMDIR_LAYOUT: dict[str, dict | None] = {
    "notes": {
        "scratch": None,
        "persistent": None,
    },
    "sessions": None,
    "config": None,
    "cache": None,
    "logs": None,
    "agents": None,
    "tasks": None,
    "plugins": None,
    "templates": None,
    "history": None,
}


def get_memdir_path(root: Optional[Path] = None) -> Path:
    """Get the path to the .pyclaude memory directory.

    Args:
        root: Project root. Defaults to cwd.

    Returns:
        Path to the .pyclaude directory.
    """
    if root is None:
        root = Path.cwd()
    return root / MEMDIR_NAME


def _create_tree(base: Path, tree: dict[str, dict | None]) -> list[Path]:
    """Recursively create directory tree, returning all created paths."""
    created: list[Path] = []
    for name, children in tree.items():
        dir_path = base / name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            created.append(dir_path)
        # place a .gitkeep so empty dirs are tracked
        gitkeep = dir_path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        if children is not None:
            created.extend(_create_tree(dir_path, children))
    return created


def ensure_structure(root: Optional[Path] = None) -> list[Path]:
    """Ensure the full .pyclaude directory structure exists.

    Args:
        root: Project root. Defaults to cwd.

    Returns:
        List of paths that were newly created.
    """
    memdir = get_memdir_path(root)
    if not memdir.exists():
        memdir.mkdir(parents=True, exist_ok=True)

    # Write a default .gitignore for the memdir
    gitignore = memdir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# pyclaude memory directory\ncache/\nlogs/\nsessions/\n",
            encoding="utf-8",
        )

    created = _create_tree(memdir, MEMDIR_LAYOUT)
    return created


def list_structure(root: Optional[Path] = None) -> dict[str, list[str]]:
    """List existing memdir contents as a dict of dir -> files."""
    memdir = get_memdir_path(root)
    if not memdir.exists():
        return {}
    result: dict[str, list[str]] = {}
    for p in sorted(memdir.rglob("*")):
        if p.is_file() and p.name != ".gitkeep":
            rel_dir = str(p.parent.relative_to(memdir))
            result.setdefault(rel_dir, []).append(p.name)
    return result
