"""Type definitions for the heads-up display."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HudEntry:
    """A single entry displayed in the HUD."""

    key: str
    value: str
    color: str = "default"
    icon: str = ""
    priority: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age(self) -> float:
        return time.time() - self.timestamp


@dataclass
class HudConfig:
    """Configuration for the HUD display."""

    max_entries: int = 20
    compact: bool = False
    visible: bool = True
    refresh_interval: float = 1.0
    default_color: str = "default"
    width: int = 60


@dataclass
class HudState:
    """Current state of the HUD."""

    entries: List[HudEntry] = field(default_factory=list)
    config: HudConfig = field(default_factory=HudConfig)
    last_render: Optional[float] = None
    visible: bool = True

    def sorted_entries(self) -> List[HudEntry]:
        return sorted(self.entries, key=lambda e: (-e.priority, e.timestamp))
