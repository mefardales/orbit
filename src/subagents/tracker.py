"""Subagent lifecycle tracker."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class TrackedSubagent:
    agent_id: str
    role: str
    status: str = 'running'

@dataclass
class SubagentTracker:
    agents: list[TrackedSubagent] = field(default_factory=list)

    def register(self, agent_id: str, role: str) -> TrackedSubagent:
        agent = TrackedSubagent(agent_id=agent_id, role=role)
        self.agents.append(agent)
        return agent

    def active_count(self) -> int:
        return sum(1 for a in self.agents if a.status == 'running')
