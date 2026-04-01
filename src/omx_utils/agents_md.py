"""AGENTS.md file utilities."""
from __future__ import annotations
from pathlib import Path

def find_agents_md(start: Path | None = None) -> Path | None:
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / 'AGENTS.md'
        if candidate.exists():
            return candidate
    return None

def read_agents_md(path: Path) -> str:
    return path.read_text(encoding='utf-8')
