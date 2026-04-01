"""BuddyContext - manages context for AI pair programming sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class FileContext:
    """Context about a file being worked on."""

    path: Path
    language: str = ""
    content_hash: str = ""
    last_read: Optional[datetime] = None
    line_count: int = 0
    relevant_lines: tuple[int, int] = (0, 0)

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix

    def detect_language(self) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".rs": "rust", ".go": "go", ".java": "java", ".c": "c",
            ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".rb": "ruby",
            ".sh": "bash", ".zsh": "zsh", ".fish": "fish",
            ".html": "html", ".css": "css", ".json": "json",
            ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
            ".md": "markdown", ".sql": "sql", ".r": "r",
            ".swift": "swift", ".kt": "kotlin", ".ex": "elixir",
            ".zig": "zig", ".lua": "lua", ".vim": "vim",
        }
        self.language = ext_map.get(self.extension.lower(), "text")
        return self.language


@dataclass
class ConversationEntry:
    """A single entry in the conversation history."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    context_files: list[str] = field(default_factory=list)


@dataclass
class BuddyPreferences:
    """User preferences for the buddy."""

    verbosity: str = "normal"  # "brief", "normal", "detailed"
    style: str = "friendly"    # "friendly", "formal", "concise"
    auto_suggest: bool = True
    max_context_files: int = 5
    max_history_entries: int = 50
    preferred_language: str = "python"


class BuddyContext:
    """Manages the full context for an AI buddy session."""

    def __init__(self, preferences: Optional[BuddyPreferences] = None) -> None:
        self.preferences = preferences or BuddyPreferences()
        self._files: dict[str, FileContext] = {}
        self._history: list[ConversationEntry] = []

    @property
    def file_context(self) -> dict[str, FileContext]:
        """Current file contexts keyed by path string."""
        return dict(self._files)

    @property
    def conversation_history(self) -> list[ConversationEntry]:
        """Full conversation history."""
        return list(self._history)

    def add_file(self, path: Path, relevant_lines: tuple[int, int] = (0, 0)) -> FileContext:
        """Add a file to the context."""
        ctx = FileContext(path=path, relevant_lines=relevant_lines)
        ctx.detect_language()
        if path.exists():
            ctx.line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            ctx.last_read = datetime.now()
        key = str(path)
        self._files[key] = ctx
        # Enforce max context files
        while len(self._files) > self.preferences.max_context_files:
            oldest_key = next(iter(self._files))
            del self._files[oldest_key]
        return ctx

    def remove_file(self, path: Path) -> bool:
        """Remove a file from context. Returns True if removed."""
        return self._files.pop(str(path), None) is not None

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        files = list(self._files.keys())
        entry = ConversationEntry(role=role, content=content, context_files=files)
        self._history.append(entry)
        # Trim old entries
        if len(self._history) > self.preferences.max_history_entries:
            self._history = self._history[-self.preferences.max_history_entries:]

    def get_recent_messages(self, count: int = 10) -> list[ConversationEntry]:
        """Get the most recent N messages."""
        return self._history[-count:]

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()

    def clear_files(self) -> None:
        """Clear all file contexts."""
        self._files.clear()

    def build_prompt_context(self) -> str:
        """Build a context string suitable for including in an AI prompt."""
        parts: list[str] = []
        if self._files:
            parts.append("## Active Files")
            for key, fc in self._files.items():
                parts.append(f"- {fc.filename} ({fc.language}, {fc.line_count} lines)")

        if self._history:
            recent = self.get_recent_messages(5)
            parts.append("\n## Recent Conversation")
            for entry in recent:
                role_label = "User" if entry.role == "user" else "Buddy"
                snippet = entry.content[:100]
                parts.append(f"- [{role_label}] {snippet}")

        return "\n".join(parts)

    def to_dict(self) -> dict:
        """Serialize context for persistence."""
        return {
            "files": {k: {"path": str(v.path), "language": v.language} for k, v in self._files.items()},
            "history_length": len(self._history),
            "preferences": {
                "verbosity": self.preferences.verbosity,
                "style": self.preferences.style,
                "auto_suggest": self.preferences.auto_suggest,
            },
        }
