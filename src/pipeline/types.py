from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

PipelineStageKind = Literal['ralplan', 'team-exec', 'ralph-verify']

@dataclass(frozen=True)
class PipelineStage:
    kind: PipelineStageKind
    name: str
    timeout_ms: int = 300_000

@dataclass
class PipelineConfig:
    stages: list[PipelineStage] = field(default_factory=list)
    max_iterations: int = 5
    stop_on_failure: bool = True
