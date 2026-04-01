from __future__ import annotations

from .query_engine import QueryEnginePort
from .runtime import OrbitRuntime


class QueryEngineRuntime(QueryEnginePort):
    def route(self, prompt: str, limit: int = 5) -> str:
        matches = OrbitRuntime().route_prompt(prompt, limit=limit)
        lines = ['# Query Engine Route', '', f'Prompt: {prompt}', '']
        if not matches:
            lines.append('No command/tool matches found.')
            return '\n'.join(lines)
        lines.append('Matches:')
        lines.extend(f'- [{match.kind}] {match.name} ({match.score}) — {match.source_hint}' for match in matches)
        return '\n'.join(lines)


__all__ = ['QueryEnginePort', 'QueryEngineRuntime']
