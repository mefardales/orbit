from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceTask:
    name: str
    description: str
