"""Pipeline orchestrator for running multi-stage execution flows."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .types import PipelineConfig, PipelineResult, PipelineStage, StageStatus

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, Dict[str, Any]], None]


@dataclass
class PipelineOrchestrator:
    """Orchestrates multi-stage pipeline execution."""

    config: PipelineConfig
    stages: List[PipelineStage] = field(default_factory=list)
    results: Dict[str, PipelineResult] = field(default_factory=dict)
    _event_listeners: List[EventCallback] = field(default_factory=list, repr=False)
    _started: bool = field(default=False, repr=False)

    def add_stage(self, stage: PipelineStage) -> None:
        """Add a stage to the pipeline."""
        self.stages.append(stage)

    def on_event(self, callback: EventCallback) -> None:
        """Register a listener for pipeline events."""
        self._event_listeners.append(callback)

    def emit_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to all registered listeners."""
        payload = data or {}
        payload["pipeline"] = self.config.name
        payload["timestamp"] = time.time()
        for listener in self._event_listeners:
            try:
                listener(event_type, payload)
            except Exception as exc:
                logger.warning("Event listener error: %s", exc)

    def run(self) -> Dict[str, PipelineResult]:
        """Run all stages in dependency order."""
        self._started = True
        self.results.clear()
        self.emit_event("pipeline.started", {"stage_count": len(self.stages)})
        execution_order = self._resolve_order()
        start_time = time.time()

        for stage in execution_order:
            elapsed = time.time() - start_time
            if elapsed >= self.config.global_timeout:
                self.emit_event("pipeline.timeout")
                self._skip_remaining(execution_order, stage)
                break

            if not self._dependencies_met(stage):
                result = PipelineResult(stage_name=stage.name, status=StageStatus.SKIPPED)
                result.finalize(StageStatus.SKIPPED, error="Unmet dependencies")
                self.results[stage.name] = result
                self.emit_event("stage.skipped", {"stage": stage.name})
                continue

            result = self.run_stage(stage)
            self.results[stage.name] = result

            if self.config.on_stage_complete:
                self.config.on_stage_complete(result)

            if not result.succeeded and not stage.allow_failure and self.config.fail_fast:
                self.emit_event("pipeline.failed", {"failed_stage": stage.name})
                self._skip_remaining(execution_order, stage)
                break

        self.emit_event("pipeline.completed", {"results": len(self.results)})
        return self.results

    def run_stage(self, stage: PipelineStage) -> PipelineResult:
        """Execute a single stage with retry support."""
        result = PipelineResult(stage_name=stage.name, status=StageStatus.RUNNING)
        self.emit_event("stage.started", {"stage": stage.name})

        for attempt in range(1, stage.max_retries + 1):
            result.attempts = attempt
            try:
                context = self._build_context(stage)
                output = stage.handler(context)
                result.finalize(StageStatus.SUCCESS, output=output)
                self.emit_event("stage.succeeded", {"stage": stage.name, "attempt": attempt})
                return result
            except Exception as exc:
                logger.warning("Stage %s attempt %d failed: %s", stage.name, attempt, exc)
                if attempt < stage.max_retries:
                    self.emit_event("stage.retrying", {"stage": stage.name, "attempt": attempt})
                    time.sleep(stage.retry_delay * attempt)

        result.finalize(StageStatus.FAILED, error=f"Failed after {stage.max_retries} attempts")
        self.emit_event("stage.failed", {"stage": stage.name})
        return result

    def handle_failure(self, stage_name: str) -> Optional[PipelineResult]:
        """Get the failure result for a stage, if any."""
        result = self.results.get(stage_name)
        if result and result.status == StageStatus.FAILED:
            return result
        return None

    def retry_stage(self, stage_name: str, max_attempts: Optional[int] = None) -> PipelineResult:
        """Retry a specific stage by name."""
        stage = next((s for s in self.stages if s.name == stage_name), None)
        if stage is None:
            raise ValueError(f"Unknown stage: {stage_name}")
        if max_attempts is not None:
            original = stage.max_retries
            stage.max_retries = max_attempts
            result = self.run_stage(stage)
            stage.max_retries = original
        else:
            result = self.run_stage(stage)
        self.results[stage_name] = result
        return result

    def get_results(self) -> Dict[str, PipelineResult]:
        """Return all collected results."""
        return dict(self.results)

    def _resolve_order(self) -> List[PipelineStage]:
        """Topological sort of stages by dependencies."""
        stage_map = {s.name: s for s in self.stages}
        visited: set[str] = set()
        order: List[PipelineStage] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            stage = stage_map.get(name)
            if stage is None:
                return
            for dep in stage.depends_on:
                visit(dep)
            order.append(stage)

        for s in self.stages:
            visit(s.name)
        return order

    def _dependencies_met(self, stage: PipelineStage) -> bool:
        for dep in stage.depends_on:
            dep_result = self.results.get(dep)
            if dep_result is None or not dep_result.succeeded:
                return False
        return True

    def _build_context(self, stage: PipelineStage) -> Dict[str, Any]:
        ctx: Dict[str, Any] = dict(self.config.context)
        ctx["stage_name"] = stage.name
        ctx["stage_metadata"] = stage.metadata
        ctx["upstream_results"] = {
            name: r.output for name, r in self.results.items() if r.succeeded
        }
        return ctx

    def _skip_remaining(self, order: List[PipelineStage], after: PipelineStage) -> None:
        found = False
        for s in order:
            if s.name == after.name:
                found = True
                continue
            if found and s.name not in self.results:
                r = PipelineResult(stage_name=s.name, status=StageStatus.SKIPPED)
                r.finalize(StageStatus.SKIPPED, error="Pipeline aborted")
                self.results[s.name] = r
