"""Session history search and indexing."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence


@dataclass
class SessionRecord:
    """A single stored session."""

    session_id: str
    started_at: float
    ended_at: Optional[float] = None
    title: str = ""
    commands: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    token_count: int = 0
    text_blob: str = ""  # pre-joined searchable text


@dataclass
class SessionSearchResult:
    """A session that matched a search query."""

    session: SessionRecord
    score: float
    matched_fields: list[str] = field(default_factory=list)
    snippet: str = ""


class SearchIndex:
    """Simple in-memory inverted index over session records."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._term_index: dict[str, set[str]] = {}  # term -> session_ids

    @property
    def size(self) -> int:
        return len(self._sessions)

    def add(self, record: SessionRecord) -> None:
        self._sessions[record.session_id] = record
        tokens = self._tokenize(record.text_blob)
        for token in tokens:
            self._term_index.setdefault(token, set()).add(record.session_id)

    def remove(self, session_id: str) -> None:
        rec = self._sessions.pop(session_id, None)
        if rec is None:
            return
        tokens = self._tokenize(rec.text_blob)
        for token in tokens:
            ids = self._term_index.get(token)
            if ids:
                ids.discard(session_id)

    def search(self, query: str, *, limit: int = 20) -> list[tuple[str, float]]:
        """Return ``(session_id, score)`` pairs ranked by relevance."""
        terms = self._tokenize(query)
        if not terms:
            return []
        scores: dict[str, float] = {}
        for term in terms:
            for sid in self._term_index.get(term, ()):
                scores[sid] = scores.get(sid, 0.0) + 1.0
        # Normalise by query length so score is in 0..1
        for sid in scores:
            scores[sid] /= len(terms)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-z0-9_]+", text.lower())


# Module-level default index
_default_index = SearchIndex()


def build_search_index(
    sessions_dir: str | Path,
    *,
    index: Optional[SearchIndex] = None,
) -> SearchIndex:
    """Scan *sessions_dir* for session JSON files and build a search index."""
    idx = index or _default_index
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return idx

    for fp in sessions_path.glob("*.json"):
        try:
            data = json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        record = _record_from_dict(data)
        idx.add(record)
    return idx


def index_session(data: dict[str, Any], *, index: Optional[SearchIndex] = None) -> SessionRecord:
    """Index a single session dict and return its record."""
    idx = index or _default_index
    record = _record_from_dict(data)
    idx.add(record)
    return record


def search_sessions(
    query: str,
    *,
    index: Optional[SearchIndex] = None,
    limit: int = 20,
    min_score: float = 0.0,
) -> list[SessionSearchResult]:
    """Search indexed sessions for *query*, returning ranked results."""
    idx = index or _default_index
    hits = idx.search(query, limit=limit)
    results: list[SessionSearchResult] = []
    for sid, score in hits:
        if score < min_score:
            continue
        session = idx._sessions.get(sid)
        if session is None:
            continue
        snippet = _make_snippet(session.text_blob, query)
        matched = _matched_fields(session, query)
        results.append(
            SessionSearchResult(
                session=session,
                score=round(score, 4),
                matched_fields=matched,
                snippet=snippet,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _record_from_dict(data: dict[str, Any]) -> SessionRecord:
    commands = data.get("commands", [])
    tool_names = data.get("tool_names", [])
    tags = data.get("tags", [])
    title = data.get("title", "")
    blob_parts = [title] + commands + tool_names + tags
    blob_parts.append(data.get("summary", ""))
    return SessionRecord(
        session_id=data.get("session_id", data.get("id", "")),
        started_at=data.get("started_at", 0.0),
        ended_at=data.get("ended_at"),
        title=title,
        commands=commands,
        tool_names=tool_names,
        tags=tags,
        token_count=data.get("token_count", 0),
        text_blob=" ".join(str(p) for p in blob_parts),
    )


def _make_snippet(text: str, query: str, max_len: int = 120) -> str:
    lower = text.lower()
    q_lower = query.lower()
    pos = lower.find(q_lower)
    if pos == -1:
        return text[:max_len]
    start = max(0, pos - 30)
    end = min(len(text), pos + len(query) + 90)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _matched_fields(session: SessionRecord, query: str) -> list[str]:
    q = query.lower()
    fields: list[str] = []
    if q in session.title.lower():
        fields.append("title")
    if any(q in c.lower() for c in session.commands):
        fields.append("commands")
    if any(q in t.lower() for t in session.tool_names):
        fields.append("tool_names")
    if any(q in t.lower() for t in session.tags):
        fields.append("tags")
    return fields
