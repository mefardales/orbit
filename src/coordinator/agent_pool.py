"""Agent pool management for multi-agent coordination."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Current state of an agent in the pool."""
    AVAILABLE = "available"
    BUSY = "busy"
    DRAINING = "draining"
    OFFLINE = "offline"


@dataclass
class AgentInfo:
    """Metadata and state for a registered agent."""
    agent_id: str
    capabilities: list[str] = field(default_factory=list)
    state: AgentState = AgentState.AVAILABLE
    max_concurrent: int = 1
    current_tasks: int = 0
    registered_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)
    total_completed: int = 0

    @property
    def has_capacity(self) -> bool:
        return self.state == AgentState.AVAILABLE and self.current_tasks < self.max_concurrent

    @property
    def utilization(self) -> float:
        if self.max_concurrent == 0:
            return 0.0
        return self.current_tasks / self.max_concurrent

    def heartbeat(self) -> None:
        self.last_heartbeat = time.monotonic()

    def can_handle(self, required_capabilities: list[str]) -> bool:
        return all(cap in self.capabilities for cap in required_capabilities)


class AgentPool:
    """Manages a pool of agents for task assignment."""

    def __init__(self, heartbeat_timeout: float = 60.0) -> None:
        self._agents: dict[str, AgentInfo] = {}
        self.heartbeat_timeout = heartbeat_timeout

    def register(
        self,
        agent_id: str,
        capabilities: list[str] | None = None,
        max_concurrent: int = 1,
        **metadata: Any,
    ) -> AgentInfo:
        """Register a new agent in the pool."""
        if agent_id in self._agents:
            raise ValueError(f"Agent already registered: {agent_id}")
        agent = AgentInfo(
            agent_id=agent_id,
            capabilities=capabilities or [],
            max_concurrent=max_concurrent,
            metadata=metadata,
        )
        self._agents[agent_id] = agent
        logger.info("Registered agent %s with capabilities %s", agent_id, capabilities)
        return agent

    def unregister(self, agent_id: str) -> None:
        """Remove an agent from the pool."""
        agent = self._agents.pop(agent_id, None)
        if agent and agent.current_tasks > 0:
            logger.warning("Unregistered agent %s with %d active tasks", agent_id, agent.current_tasks)

    def acquire(self, required_capabilities: list[str] | None = None) -> AgentInfo | None:
        """Acquire the best available agent matching required capabilities."""
        self._check_heartbeats()
        candidates = [
            a for a in self._agents.values()
            if a.has_capacity and a.can_handle(required_capabilities or [])
        ]
        if not candidates:
            return None
        # Pick least utilized agent
        best = min(candidates, key=lambda a: a.utilization)
        best.current_tasks += 1
        if best.current_tasks >= best.max_concurrent:
            best.state = AgentState.BUSY
        logger.debug("Acquired agent %s (utilization: %.0f%%)", best.agent_id, best.utilization * 100)
        return best

    def release(self, agent_id: str) -> None:
        """Release an agent back to the pool after task completion."""
        agent = self._agents.get(agent_id)
        if agent is None:
            return
        agent.current_tasks = max(0, agent.current_tasks - 1)
        agent.total_completed += 1
        if agent.state == AgentState.BUSY and agent.current_tasks < agent.max_concurrent:
            agent.state = AgentState.AVAILABLE
        logger.debug("Released agent %s", agent_id)

    def list_available(self, capabilities: list[str] | None = None) -> list[AgentInfo]:
        """List all agents that have capacity and match capabilities."""
        self._check_heartbeats()
        return [
            a for a in self._agents.values()
            if a.has_capacity and a.can_handle(capabilities or [])
        ]

    def get(self, agent_id: str) -> AgentInfo | None:
        return self._agents.get(agent_id)

    def _check_heartbeats(self) -> None:
        """Mark agents offline if heartbeat has expired."""
        now = time.monotonic()
        for agent in self._agents.values():
            if agent.state != AgentState.OFFLINE and (now - agent.last_heartbeat) > self.heartbeat_timeout:
                agent.state = AgentState.OFFLINE
                logger.warning("Agent %s marked offline (heartbeat timeout)", agent.agent_id)

    @property
    def size(self) -> int:
        return len(self._agents)

    @property
    def available_count(self) -> int:
        return sum(1 for a in self._agents.values() if a.has_capacity)

    def stats(self) -> dict[str, Any]:
        return {
            "total": self.size,
            "available": self.available_count,
            "busy": sum(1 for a in self._agents.values() if a.state == AgentState.BUSY),
            "offline": sum(1 for a in self._agents.values() if a.state == AgentState.OFFLINE),
        }
