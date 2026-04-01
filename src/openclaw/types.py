from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class OpenclawConfig:
    enabled: bool = False
    endpoint: str = ''
    token: str = ''

@dataclass(frozen=True)
class OpenclawEvent:
    event_type: str
    payload: str
    timestamp: str = ''
