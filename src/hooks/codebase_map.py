"""
Codebase Map Generator.

Generates a lightweight snapshot of the project's source structure,
injected into agent context at session start. Uses `git ls-files`
for fast enumeration without filesystem walking.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

MAX_MAP_CHARS = 1000
MAX_FILES_PER_DIR = 10
MAX_DIRS = 14

SOURCE_EXTS = {".ts", ".tsx", ".js", ".mjs", ".py", ".go", ".rs", ".java"}

PRIORITY_DIRS = ["src", "scripts", "bin", "prompts", "agents", "skills", "templates"]


def _get_tracked_source_files(cwd: str) -> List[str]:
    """Return git-tracked source files relative to cwd."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=4,
        )
        if result.returncode != 0:
            return []
        return [
            f for f in result.stdout.strip().split("\n")
            if f and Path(f).suffix in SOURCE_EXTS
        ]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _group_by_top_dir(files: List[str]) -> Dict[str, List[str]]:
    """Group relative file paths by their top-level directory segment."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for f in files:
        sep = f.find("/")
        d = f[:sep] if sep >= 0 else "."
        groups[d].append(f)
    return dict(groups)


def _sort_dirs(dirs: List[str]) -> List[str]:
    """Sort directory entries: priority dirs first, dotfiles/root last."""
    def sort_key(d: str) -> tuple:
        if d in PRIORITY_DIRS:
            return (0, PRIORITY_DIRS.index(d), d)
        if d.startswith(".") or d == ".":
            return (2, 0, d)
        return (1, 0, d)

    return sorted(dirs, key=sort_key)


def _build_dir_line(directory: str, files: List[str]) -> str:
    """Build a single directory line."""
    names = []
    for f in files[:MAX_FILES_PER_DIR]:
        name = Path(f).stem
        names.append(name)

    # Keep 'index' only if it's the sole file
    if len(names) > 1:
        names = [n for n in names if n != "index"]

    if not names:
        return ""

    label = "(root)" if directory == "." else f"{directory}/"
    return f"  {label}: {', '.join(names)}"


async def generate_codebase_map(cwd: str) -> str:
    """
    Generate a compact codebase map for the project at cwd.

    Returns an empty string if no git-tracked source files exist
    or any error occurs (always safe to call).
    """
    try:
        files = _get_tracked_source_files(cwd)
        if not files:
            return ""

        grouped = _group_by_top_dir(files)
        sorted_dirs = _sort_dirs(list(grouped.keys()))

        lines: List[str] = []
        for d in sorted_dirs[:MAX_DIRS]:
            dir_files = grouped.get(d, [])

            if d == "src":
                # Sub-group src by its immediate subdirectory
                sub_grouped: Dict[str, List[str]] = defaultdict(list)
                for f in dir_files:
                    parts = f.split("/")
                    sub_dir = f"src/{parts[1]}" if len(parts) >= 3 else "src"
                    sub_grouped[sub_dir].append(f)

                sorted_subs = sorted(sub_grouped.keys())
                for sub in sorted_subs[:MAX_DIRS]:
                    sub_files = sub_grouped[sub]
                    line = _build_dir_line(sub, sub_files)
                    if line:
                        lines.append(line)
            else:
                line = _build_dir_line(d, dir_files)
                if line:
                    lines.append(line)

        if not lines:
            return ""

        body = "\n".join(lines)
        if len(body) > MAX_MAP_CHARS:
            return body[: MAX_MAP_CHARS - 3] + "..."
        return body

    except Exception:
        return ""
