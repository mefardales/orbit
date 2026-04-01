from __future__ import annotations
from dataclasses import dataclass
from .types import OpenclawConfig, OpenclawEvent

@dataclass
class OpenclawDispatcher:
    config: OpenclawConfig
    sent_count: int = 0

    def dispatch(self, event: OpenclawEvent) -> bool:
        if not self.config.enabled:
            return False
        self.sent_count += 1
        return True
