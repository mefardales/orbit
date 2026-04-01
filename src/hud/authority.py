from __future__ import annotations
from dataclasses import dataclass

@dataclass
class HudAuthority:
    enabled: bool = True
    auto_refresh: bool = True

    def should_render(self) -> bool:
        return self.enabled
