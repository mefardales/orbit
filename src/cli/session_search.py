"""Session history search, mirrors src/cli/session-search.ts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    session_id: str
    snippet: str
    score: float


def search_sessions(query: str, *, limit: int = 20) -> list[SearchResult]:
    """Search persisted session transcripts for *query*.

    Returns up to *limit* results sorted by relevance.  Currently a stub
    that returns an empty list; a real implementation would index the
    session-history store.
    """
    # TODO: implement full-text search over session history files
    return []
