from __future__ import annotations
from dataclasses import dataclass, field
from .types import PipelineConfig, PipelineStage

@dataclass
class PipelineResult:
    stage: str
    success: bool
    output: str = ''

@dataclass
class PipelineOrchestrator:
    config: PipelineConfig = field(default_factory=PipelineConfig)
    results: list[PipelineResult] = field(default_factory=list)
    status: str = 'idle'

    def run(self) -> list[PipelineResult]:
        self.status = 'running'
        for stage in self.config.stages:
            result = PipelineResult(stage=stage.name, success=True, output=f'{stage.kind} completed')
            self.results.append(result)
            if not result.success and self.config.stop_on_failure:
                self.status = 'failed'
                return self.results
        self.status = 'completed'
        return self.results
