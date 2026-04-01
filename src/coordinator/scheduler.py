"""Task scheduler for multi-agent coordination."""

from __future__ import annotations

import heapq
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .agent_pool import AgentPool

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Priority levels for scheduled tasks."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class TaskState(Enum):
    """Lifecycle state of a task."""
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(order=True)
class ScheduledTask:
    """A task managed by the scheduler."""
    priority_value: int = field(compare=True)
    queued_at: float = field(compare=True)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10], compare=False)
    name: str = field(default="", compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)
    required_capabilities: list[str] = field(default_factory=list, compare=False)
    state: TaskState = field(default=TaskState.QUEUED, compare=False)
    assigned_agent: str | None = field(default=None, compare=False)
    result: Any = field(default=None, compare=False)
    error: str | None = field(default=None, compare=False)
    created_at: float = field(default_factory=time.monotonic, compare=False)
    started_at: float | None = field(default=None, compare=False)
    completed_at: float | None = field(default=None, compare=False)

    @property
    def duration_ms(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None


class TaskScheduler:
    """Priority-based task scheduler with agent pool integration."""

    def __init__(self, agent_pool: AgentPool | None = None) -> None:
        self._agent_pool = agent_pool or AgentPool()
        self._queue: list[ScheduledTask] = []
        self._tasks: dict[str, ScheduledTask] = {}
        self._completed: list[ScheduledTask] = []

    def queue(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        required_capabilities: list[str] | None = None,
    ) -> ScheduledTask:
        """Add a task to the priority queue."""
        task = ScheduledTask(
            priority_value=priority.value,
            queued_at=time.monotonic(),
            name=name,
            payload=payload or {},
            required_capabilities=required_capabilities or [],
        )
        heapq.heappush(self._queue, task)
        self._tasks[task.task_id] = task
        logger.info("Queued task %s (%s) with priority %s", task.task_id, name, priority.name)
        return task

    def assign(self) -> ScheduledTask | None:
        """Assign the highest-priority task to an available agent."""
        # Try tasks in priority order
        temp: list[ScheduledTask] = []
        assigned_task: ScheduledTask | None = None

        while self._queue:
            task = heapq.heappop(self._queue)
            if task.state != TaskState.QUEUED:
                continue
            agent = self._agent_pool.acquire(task.required_capabilities)
            if agent is not None:
                task.state = TaskState.ASSIGNED
                task.assigned_agent = agent.agent_id
                task.started_at = time.monotonic()
                assigned_task = task
                # Push back remaining
                for t in temp:
                    heapq.heappush(self._queue, t)
                logger.info("Assigned task %s to agent %s", task.task_id, agent.agent_id)
                return assigned_task
            temp.append(task)

        # Restore unassigned tasks
        for t in temp:
            heapq.heappush(self._queue, t)
        return None

    def complete(self, task_id: str, result: Any = None) -> ScheduledTask:
        """Mark a task as completed."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        task.state = TaskState.COMPLETED
        task.result = result
        task.completed_at = time.monotonic()
        if task.assigned_agent:
            self._agent_pool.release(task.assigned_agent)
        self._completed.append(task)
        logger.info("Task %s completed in %.1fms", task_id, task.duration_ms or 0)
        return task

    def fail(self, task_id: str, error: str) -> ScheduledTask:
        """Mark a task as failed."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        task.state = TaskState.FAILED
        task.error = error
        task.completed_at = time.monotonic()
        if task.assigned_agent:
            self._agent_pool.release(task.assigned_agent)
        logger.error("Task %s failed: %s", task_id, error)
        return task

    def cancel(self, task_id: str) -> ScheduledTask:
        """Cancel a queued or assigned task."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        if task.state in (TaskState.COMPLETED, TaskState.FAILED):
            raise ValueError(f"Cannot cancel task in state {task.state.value}")
        task.state = TaskState.CANCELLED
        if task.assigned_agent:
            self._agent_pool.release(task.assigned_agent)
        return task

    def rebalance(self) -> int:
        """Try to assign all queued tasks. Returns number newly assigned."""
        assigned_count = 0
        while True:
            task = self.assign()
            if task is None:
                break
            assigned_count += 1
        return assigned_count

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self._queue if t.state == TaskState.QUEUED)

    def get_task(self, task_id: str) -> ScheduledTask | None:
        return self._tasks.get(task_id)

    def stats(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        for t in self._tasks.values():
            states[t.state.value] = states.get(t.state.value, 0) + 1
        return {
            "total": len(self._tasks),
            "by_state": states,
            "agent_pool": self._agent_pool.stats(),
        }
