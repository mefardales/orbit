"""File system operations: read, write, search, and glob."""

from __future__ import annotations

import fnmatch
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_ENCODING = "utf-8"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@dataclass
class SearchResult:
    """A single search match within a file."""
    path: Path
    line_number: int
    line_content: str
    match_start: int = 0
    match_end: int = 0


@dataclass
class FileInfo:
    """Metadata about a file."""
    path: Path
    size: int
    is_dir: bool
    extension: str
    modified_time: float


class FileServiceError(Exception):
    """Raised on file service failures."""
    pass


class FileService:
    """Service for file system operations scoped to a root directory."""

    def __init__(self, root: Optional[Path] = None, encoding: str = DEFAULT_ENCODING):
        self.root = Path(root) if root else Path.cwd()
        self.encoding = encoding
        if not self.root.is_dir():
            raise FileServiceError(f"Root is not a directory: {self.root}")

    def _resolve(self, path: str | Path) -> Path:
        """Resolve a path relative to root, ensuring it stays within bounds."""
        resolved = (self.root / path).resolve()
        if not str(resolved).startswith(str(self.root.resolve())):
            raise FileServiceError(f"Path escapes root directory: {path}")
        return resolved

    def read(
        self,
        path: str | Path,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> str:
        """Read file contents, optionally a slice of lines."""
        resolved = self._resolve(path)
        if not resolved.is_file():
            raise FileServiceError(f"Not a file: {resolved}")
        if resolved.stat().st_size > MAX_FILE_SIZE:
            raise FileServiceError(f"File too large: {resolved.stat().st_size} bytes")

        text = resolved.read_text(encoding=self.encoding)

        if offset or limit:
            lines = text.splitlines(keepends=True)
            end = offset + limit if limit else None
            lines = lines[offset:end]
            return "".join(lines)

        return text

    def write(
        self,
        path: str | Path,
        content: str,
        create_parents: bool = True,
        append: bool = False,
    ) -> Path:
        """Write content to a file. Creates parent directories if needed."""
        resolved = self._resolve(path)

        if create_parents:
            resolved.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with open(resolved, mode, encoding=self.encoding) as f:
            f.write(content)

        logger.debug("Wrote %d chars to %s", len(content), resolved)
        return resolved

    def search(
        self,
        pattern: str,
        path: str | Path = ".",
        file_glob: str = "*",
        max_results: int = 100,
        case_sensitive: bool = True,
    ) -> List[SearchResult]:
        """Search for a regex pattern across files under a directory."""
        search_root = self._resolve(path)
        if not search_root.is_dir():
            raise FileServiceError(f"Not a directory: {search_root}")

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error as e:
            raise FileServiceError(f"Invalid regex: {e}") from e

        results: List[SearchResult] = []

        for file_path in self.glob(file_glob, path):
            if len(results) >= max_results:
                break
            try:
                text = file_path.read_text(encoding=self.encoding, errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            for line_num, line in enumerate(text.splitlines(), start=1):
                if len(results) >= max_results:
                    break
                match = compiled.search(line)
                if match:
                    results.append(SearchResult(
                        path=file_path,
                        line_number=line_num,
                        line_content=line,
                        match_start=match.start(),
                        match_end=match.end(),
                    ))

        return results

    def glob(
        self,
        pattern: str,
        path: str | Path = ".",
        include_hidden: bool = False,
    ) -> List[Path]:
        """Find files matching a glob pattern under a directory."""
        search_root = self._resolve(path)
        if not search_root.is_dir():
            return []

        results: List[Path] = []
        for match in search_root.rglob(pattern):
            if not include_hidden:
                parts = match.relative_to(search_root).parts
                if any(p.startswith(".") for p in parts):
                    continue
            if match.is_file():
                results.append(match)

        results.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return results

    def info(self, path: str | Path) -> FileInfo:
        """Get metadata about a file or directory."""
        resolved = self._resolve(path)
        if not resolved.exists():
            raise FileServiceError(f"Path does not exist: {resolved}")
        stat = resolved.stat()
        return FileInfo(
            path=resolved,
            size=stat.st_size,
            is_dir=resolved.is_dir(),
            extension=resolved.suffix,
            modified_time=stat.st_mtime,
        )

    def exists(self, path: str | Path) -> bool:
        """Check if a path exists within the root."""
        try:
            return self._resolve(path).exists()
        except FileServiceError:
            return False

    def delete(self, path: str | Path) -> bool:
        """Delete a file (not directories). Returns True on success."""
        resolved = self._resolve(path)
        if not resolved.is_file():
            return False
        resolved.unlink()
        return True
