"""Global runtime context for CLI flags and configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RuntimeContext:
    """Mutable runtime context populated by global CLI flags."""

    autonomy: str = 'standard'          # standard | madmax
    reasoning_effort: str = 'medium'    # low | medium | high | xhigh
    model_tier: str = 'default'         # default | spark | frontier
    model_override: Optional[str] = None
    config_path: Optional[str] = None

    _instance: 'RuntimeContext | None' = field(default=None, init=False, repr=False)

    @classmethod
    def get(cls) -> 'RuntimeContext':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    @property
    def is_madmax(self) -> bool:
        return self.autonomy == 'madmax'

    @property
    def is_spark(self) -> bool:
        return self.model_tier == 'spark'

    @property
    def is_high_reasoning(self) -> bool:
        return self.reasoning_effort in ('high', 'xhigh')
