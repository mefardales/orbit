"""Subagent lifecycle tracker."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .types import SubagentStatus, TrackedSubagent

logger = logging.getLogger(__name__)


class SubagentTracker:
    """Track subagent registration, status transitions, and session summaries."""

    def __init__(self) -> None:
        self._agents: dict[str, TrackedSubagent] = {}

    # -- registration ----------------------------------------------------------

    def register(
        self,
        agent_id: str,
        *,
        role: str = "executor",
        parent_id: Optional[str] = None,
        task_description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> TrackedSubagent:
        """Register a new subagent and begin tracking it."""
        if agent_id in self._agents:
            raise ValueError(f"Agent {agent_id!r} is already registered")
        agent = TrackedSubagent(
            agent_id=agent_id,
            role=role,
            parent_id=parent_id,
            task_description=task_description,
            metadata=metadata or {},
        )
        self._agents[agent_id] = agent
        logger.info("Registered subagent %s (role=%s)", agent_id, role)
        return agent

    def deregister(self, agent_id: str) -> Optional[TrackedSubagent]:
        """Remove and return a subagent, marking it cancelled if still active."""
        agent = self._agents.pop(agent_id, None)
        if agent is None:
            return None
        if agent.is_active:
            agent.status = SubagentStatus.CANCELLED
            agent.finished_at = time.time()
            logger.info("Deregistered (cancelled) subagent %s", agent_id)
        else:
            logger.info("Deregistered subagent %s (was %s)", agent_id, agent.status.value)
        return agent

    # -- status transitions ----------------------------------------------------

    def start(self, agent_id: str) -> None:
        agent = self._get(agent_id)
        agent.status = SubagentStatus.RUNNING
        agent.started_at = time.time()

    def pause(self, agent_id: str) -> None:
        agent = self._get(agent_id)
        agent.status = SubagentStatus.PAUSED

    def resume(self, agent_id: str) -> None:
        agent = self._get(agent_id)
        agent.status = SubagentStatus.RUNNING

    def complete(self, agent_id: str) -> None:
        agent = self._get(agent_id)
        agent.status = SubagentStatus.COMPLETED
        agent.finished_at = time.time()

    def fail(self, agent_id: str, error: str = "") -> None:
        agent = self._get(agent_id)
        agent.status = SubagentStatus.FAILED
        agent.finished_at = time.time()
        agent.error = error

    def record_tool_call(self, agent_id: str, tokens: int = 0) -> None:
        agent = self._get(agent_id)
        agent.tool_calls += 1
        agent.tokens_used += tokens

    # -- queries ---------------------------------------------------------------

    def get_status(self, agent_id: str) -> SubagentStatus:
        return self._get(agent_id).status

    def list_active(self) -> list[TrackedSubagent]:
        return [a for a in self._agents.values() if a.is_active]

    def list_all(self) -> list[TrackedSubagent]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> Optional[TrackedSubagent]:
        return self._agents.get(agent_id)

    # -- summary ---------------------------------------------------------------

    def summarize_session(self) -> dict[str, Any]:
        """Return an aggregate summary of all tracked subagents."""
        all_agents = list(self._agents.values())
        active = [a for a in all_agents if a.is_active]
        completed = [a for a in all_agents if a.status == SubagentStatus.COMPLETED]
        failed = [a for a in all_agents if a.status == SubagentStatus.FAILED]
        cancelled = [a for a in all_agents if a.status == SubagentStatus.CANCELLED]

        total_tools = sum(a.tool_calls for a in all_agents)
        total_tokens = sum(a.tokens_used for a in all_agents)
        total_elapsed = sum(
            (a.elapsed_seconds or 0.0) for a in all_agents if a.started_at is not None
        )

        return {
            "total_agents": len(all_agents),
            "active": len(active),
            "completed": len(completed),
            "failed": len(failed),
            "cancelled": len(cancelled),
            "total_tool_calls": total_tools,
            "total_tokens_used": total_tokens,
            "total_elapsed_seconds": round(total_elapsed, 3),
            "agents": [a.to_dict() for a in all_agents],
        }

    # -- internal --------------------------------------------------------------

    def _get(self, agent_id: str) -> TrackedSubagent:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"No tracked subagent with id {agent_id!r}")
        return agent
