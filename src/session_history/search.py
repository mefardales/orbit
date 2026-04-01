"""Session history search."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SessionSearchResult:
    session_id: str
    match_text: str
    score: float

def search_sessions(query: str, sessions_dir: Path | None = None) -> list[SessionSearchResult]:
    root = sessions_dir or Path('.omx/sessions')
    if not root.exists():
        return []
    results = []
    needle = query.lower()
    for f in root.glob('*.json'):
        try:
            data = json.loads(f.read_text())
            text = json.dumps(data).lower()
            if needle in text:
                results.append(SessionSearchResult(session_id=f.stem, match_text=query, score=1.0))
        except (json.JSONDecodeError, OSError):
            continue
    return results
