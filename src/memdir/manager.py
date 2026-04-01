"""MemdirManager - high level interface for .pyclaude memory directory."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from memdir.structure import ensure_structure, get_memdir_path


class MemdirManager:
    """Manage notes and data inside the .pyclaude memory directory."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.memdir = get_memdir_path(self.root)

    def init(self) -> list[Path]:
        """Initialize the memory directory structure. Returns created paths."""
        return ensure_structure(self.root)

    @property
    def notes_dir(self) -> Path:
        return self.memdir / "notes" / "persistent"

    @property
    def scratch_dir(self) -> Path:
        return self.memdir / "notes" / "scratch"

    def write_note(
        self,
        name: str,
        content: str,
        scratch: bool = False,
        metadata: Optional[dict] = None,
    ) -> Path:
        """Write a note to the memory directory.

        Args:
            name: Note filename (extension added if missing).
            content: Note body text.
            scratch: If True, write to scratch (ephemeral) dir.
            metadata: Optional metadata dict stored as JSON frontmatter.

        Returns:
            Path to the written note file.
        """
        if not name.endswith((".md", ".txt", ".json")):
            name += ".md"
        target_dir = self.scratch_dir if scratch else self.notes_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name

        parts: list[str] = []
        if metadata:
            header = {
                **metadata,
                "updated_at": datetime.now().isoformat(),
            }
            parts.append("---")
            parts.append(json.dumps(header, indent=2))
            parts.append("---\n")
        parts.append(content)

        path.write_text("\n".join(parts), encoding="utf-8")
        return path

    def read_note(self, name: str, scratch: bool = False) -> Optional[str]:
        """Read a note by name. Returns None if not found."""
        if not name.endswith((".md", ".txt", ".json")):
            name += ".md"
        target_dir = self.scratch_dir if scratch else self.notes_dir
        path = target_dir / name
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def delete_note(self, name: str, scratch: bool = False) -> bool:
        """Delete a note. Returns True if deleted."""
        if not name.endswith((".md", ".txt", ".json")):
            name += ".md"
        target_dir = self.scratch_dir if scratch else self.notes_dir
        path = target_dir / name
        if path.exists():
            path.unlink()
            return True
        return False

    def list_notes(self, scratch: bool = False) -> list[str]:
        """List all note filenames in the notes directory."""
        target_dir = self.scratch_dir if scratch else self.notes_dir
        if not target_dir.exists():
            return []
        return sorted(
            f.name for f in target_dir.iterdir()
            if f.is_file() and f.name != ".gitkeep"
        )

    def search_notes(self, query: str, scratch: bool = False) -> list[tuple[str, list[str]]]:
        """Search notes for a query string (case-insensitive).

        Returns:
            List of (filename, matching_lines) tuples.
        """
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results: list[tuple[str, list[str]]] = []
        target_dir = self.scratch_dir if scratch else self.notes_dir
        if not target_dir.exists():
            return results
        for fpath in sorted(target_dir.iterdir()):
            if not fpath.is_file() or fpath.name == ".gitkeep":
                continue
            try:
                text = fpath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            matches = [line for line in text.splitlines() if pattern.search(line)]
            if matches:
                results.append((fpath.name, matches))
        return results

    def cleanup(self, max_age_days: int = 7) -> int:
        """Remove scratch notes older than max_age_days.

        Returns:
            Number of files removed.
        """
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0
        if not self.scratch_dir.exists():
            return 0
        for fpath in self.scratch_dir.iterdir():
            if fpath.name == ".gitkeep" or not fpath.is_file():
                continue
            mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
            if mtime < cutoff:
                fpath.unlink()
                removed += 1
        return removed

    def clear_cache(self) -> int:
        """Remove all files from the cache directory. Returns files removed."""
        cache_dir = self.memdir / "cache"
        if not cache_dir.exists():
            return 0
        count = sum(1 for f in cache_dir.iterdir() if f.is_file())
        shutil.rmtree(cache_dir)
        cache_dir.mkdir()
        return count
