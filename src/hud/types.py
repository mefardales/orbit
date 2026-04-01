from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class HudEntry:
    key: str
    label: str
    value: str
    color: str = 'default'

@dataclass
class HudState:
    entries: list[HudEntry] = field(default_factory=list)
    visible: bool = True
    last_updated: str = ''
