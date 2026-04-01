"""Session history search for pyclaude."""

from .search import search_sessions, SessionSearchResult, index_session, build_search_index

__all__ = [
    "search_sessions",
    "SessionSearchResult",
    "index_session",
    "build_search_index",
]
