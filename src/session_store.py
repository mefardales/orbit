"""
Session lifecycle management for orbit.

Provides SessionManager for creating, saving, loading, resuming, searching,
exporting, and deleting conversation sessions stored as JSON files in
~/.orbit/sessions/.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

# ── Kept for backward compat: the original minimal StoredSession ─────────────

SessionStatus = Literal["active", "completed", "interrupted"]

_DEFAULT_SESSIONS_DIR = Path.home() / ".orbit" / "sessions"


@dataclass
class StoredSession:
    """Minimal session record (original interface, kept for callers in main.py)."""

    session_id: str
    messages: tuple[str, ...]
    input_tokens: int
    output_tokens: int


# ── Full session data model ───────────────────────────────────────────────────


@dataclass
class SessionMessage:
    """A single turn in the conversation."""

    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMessage":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class SessionState:
    """Full state for a single orbit session."""

    session_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: List[SessionMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: SessionStatus = "active"
    tags: List[str] = field(default_factory=list)

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def provider(self) -> str:
        return self.metadata.get("provider", "")

    @property
    def model(self) -> str:
        return self.metadata.get("model", "")

    @property
    def total_tokens(self) -> int:
        return self.metadata.get("total_tokens", 0)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
            "metadata": self.metadata,
            "status": self.status,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        msgs = [SessionMessage.from_dict(m) for m in data.get("messages", [])]
        return cls(
            session_id=data["session_id"],
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            messages=msgs,
            metadata=data.get("metadata", {}),
            status=data.get("status", "active"),  # type: ignore[arg-type]
            tags=data.get("tags", []),
        )

    # ── Export helpers ────────────────────────────────────────────────────────

    def as_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def as_markdown(self) -> str:
        lines = [
            f"# Session {self.session_id}",
            "",
            f"- **Status**: {self.status}",
            f"- **Provider**: {self.provider or '—'}",
            f"- **Model**: {self.model or '—'}",
            f"- **Created**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.created_at))}",
            f"- **Messages**: {self.message_count}",
            f"- **Tags**: {', '.join(self.tags) if self.tags else '—'}",
            "",
            "---",
            "",
        ]
        for msg in self.messages:
            ts = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
            lines.append(f"**[{ts}] {msg.role.upper()}**")
            lines.append("")
            lines.append(msg.content)
            lines.append("")
        return "\n".join(lines)


# ── Summary record (lightweight, for listings) ────────────────────────────────


@dataclass
class SessionSummary:
    """Lightweight listing record for a session."""

    session_id: str
    created_at: float
    updated_at: float
    status: SessionStatus
    message_count: int
    tags: List[str]
    provider: str
    model: str

    @classmethod
    def from_state(cls, state: SessionState) -> "SessionSummary":
        return cls(
            session_id=state.session_id,
            created_at=state.created_at,
            updated_at=state.updated_at,
            status=state.status,
            message_count=state.message_count,
            tags=state.tags,
            provider=state.provider,
            model=state.model,
        )


# ── Session Manager ───────────────────────────────────────────────────────────


class SessionManager:
    """Manages orbit session lifecycle on disk.

    Sessions are stored as JSON files at:
        {sessions_dir}/{session_id}.json

    The default sessions_dir is ~/.orbit/sessions/.
    """

    def __init__(self, sessions_dir: Optional[Path] = None) -> None:
        self._dir = sessions_dir or _DEFAULT_SESSIONS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _write(self, state: SessionState) -> None:
        self._path(state.session_id).write_text(state.as_json(), encoding="utf-8")

    def _read(self, session_id: str) -> SessionState:
        path = self._path(session_id)
        if not path.exists():
            raise KeyError(f"Session not found: {session_id!r}")
        try:
            data = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt session file for {session_id!r}: {exc}") from exc
        return SessionState.from_dict(data)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_session(
        self,
        prompt: str,
        *,
        provider: str = "",
        model: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new session seeded with an initial user prompt.

        Returns the new session_id (UUID4 hex string).
        """
        session_id = uuid.uuid4().hex
        now = time.time()
        state = SessionState(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            messages=[SessionMessage(role="user", content=prompt, timestamp=now)],
            metadata={"provider": provider, "model": model, "total_tokens": 0},
            status="active",
            tags=tags or [],
        )
        self._write(state)
        return session_id

    def save_checkpoint(self, session_id: str, state: SessionState) -> None:
        """Persist the current state of a session (periodic checkpoint).

        Updates the updated_at timestamp before saving.
        """
        state.updated_at = time.time()
        self._write(state)

    def load_session(self, session_id: str) -> SessionState:
        """Load a session by ID.

        Raises:
            KeyError: if the session does not exist.
            ValueError: if the session file is corrupt.
        """
        return self._read(session_id)

    def resume_session(self, session_id: str) -> SessionState:
        """Load a session and set its status back to 'active'.

        Use this when a previously interrupted or completed session is being
        continued. The restored state is persisted immediately.
        """
        state = self._read(session_id)
        state.status = "active"
        state.updated_at = time.time()
        self._write(state)
        return state

    def delete_session(self, session_id: str) -> bool:
        """Remove all data for a session.

        Returns True if deleted, False if the session did not exist.
        """
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    # ── Listing ───────────────────────────────────────────────────────────────

    def list_sessions(self, limit: int = 20) -> List[SessionSummary]:
        """Return the most-recently-updated sessions, newest first.

        Args:
            limit: Maximum number of sessions to return.
        """
        summaries: List[SessionSummary] = []
        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text("utf-8"))
                state = SessionState.from_dict(data)
                summaries.append(SessionSummary.from_state(state))
            except (json.JSONDecodeError, KeyError, OSError):
                continue

        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries[:limit]

    # ── Search ────────────────────────────────────────────────────────────────

    def search_sessions(self, query: str, *, limit: int = 20) -> List[SessionSummary]:
        """Return sessions whose messages contain the query string.

        Case-insensitive substring match against all message content.
        Results are sorted by updated_at descending.

        Args:
            query: The search string.
            limit: Maximum number of results.
        """
        q_lower = query.lower()
        matched: List[SessionSummary] = []

        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text("utf-8"))
                state = SessionState.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError):
                continue

            # Check tags, metadata, and message content
            hit = (
                any(q_lower in t.lower() for t in state.tags)
                or q_lower in state.provider.lower()
                or q_lower in state.model.lower()
                or any(q_lower in m.content.lower() for m in state.messages)
            )
            if hit:
                matched.append(SessionSummary.from_state(state))

        matched.sort(key=lambda s: s.updated_at, reverse=True)
        return matched[:limit]

    # ── Export ────────────────────────────────────────────────────────────────

    def export_session(
        self,
        session_id: str,
        format: Literal["json", "markdown"] = "json",  # noqa: A002
    ) -> str:
        """Return the session as a formatted string.

        Args:
            session_id: The session to export.
            format: 'json' or 'markdown'.

        Returns:
            The formatted transcript string.

        Raises:
            KeyError: if the session does not exist.
            ValueError: if format is unknown.
        """
        state = self._read(session_id)
        if format == "json":
            return state.as_json()
        if format == "markdown":
            return state.as_markdown()
        raise ValueError(f"Unknown export format: {format!r}. Expected 'json' or 'markdown'.")

    # ── Message helpers ───────────────────────────────────────────────────────

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        token_delta: int = 0,
    ) -> SessionState:
        """Append a message to an existing session and save.

        Args:
            session_id:  Target session.
            role:        'user', 'assistant', or 'system'.
            content:     Message text.
            token_delta: Optional token count to add to the session total.

        Returns:
            The updated SessionState.
        """
        state = self._read(session_id)
        state.messages.append(SessionMessage(role=role, content=content))
        if token_delta:
            state.metadata["total_tokens"] = state.metadata.get("total_tokens", 0) + token_delta
        state.updated_at = time.time()
        self._write(state)
        return state

    def mark_complete(self, session_id: str) -> SessionState:
        """Mark a session as completed and save."""
        state = self._read(session_id)
        state.status = "completed"
        state.updated_at = time.time()
        self._write(state)
        return state

    def mark_interrupted(self, session_id: str) -> SessionState:
        """Mark a session as interrupted and save."""
        state = self._read(session_id)
        state.status = "interrupted"
        state.updated_at = time.time()
        self._write(state)
        return state

    def add_tag(self, session_id: str, tag: str) -> SessionState:
        """Add a tag to a session (idempotent)."""
        state = self._read(session_id)
        if tag not in state.tags:
            state.tags.append(tag)
            state.updated_at = time.time()
            self._write(state)
        return state


# ── Backward-compatible helpers used by main.py ──────────────────────────────

_DEFAULT_SESSION_DIR = Path(".port_sessions")


def save_session(session: StoredSession, directory: Optional[Path] = None) -> Path:
    """Save a minimal StoredSession to disk (original interface)."""
    target_dir = directory or _DEFAULT_SESSION_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{session.session_id}.json"
    path.write_text(json.dumps(asdict(session), indent=2))
    return path


def load_session(session_id: str, directory: Optional[Path] = None) -> StoredSession:
    """Load a minimal StoredSession by ID (original interface).

    Also tries the full-featured SessionManager store so callers that used
    'orbit load-session <id>' can load sessions created by SessionManager.
    """
    # Try legacy location first
    target_dir = directory or _DEFAULT_SESSION_DIR
    legacy_path = target_dir / f"{session_id}.json"
    if legacy_path.exists():
        data = json.loads(legacy_path.read_text())
        return StoredSession(
            session_id=data["session_id"],
            messages=tuple(data["messages"]),
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
        )

    # Try the full SessionManager store
    mgr = SessionManager()
    try:
        state = mgr.load_session(session_id)
    except KeyError:
        raise FileNotFoundError(f"Session not found: {session_id!r}")

    return StoredSession(
        session_id=state.session_id,
        messages=tuple(m.content for m in state.messages),
        input_tokens=state.metadata.get("input_tokens", 0),
        output_tokens=state.metadata.get("output_tokens", 0),
    )


# Module-level default manager
_default_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Return the module-level default SessionManager."""
    return _default_manager
