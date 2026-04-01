"""Common literal and enum types shared across pyclaude."""

from __future__ import annotations

from typing import Literal

# The role an agent plays in a multi-agent session.
AgentRole = Literal[
    "orchestrator",
    "coder",
    "reviewer",
    "planner",
    "researcher",
    "executor",
    "debugger",
]

# The level of tool access granted to a session or sub-agent.
ToolAccess = Literal[
    "none",
    "read_only",
    "write_local",
    "write_all",
    "full",
]

# How much reasoning effort the model should apply.
ReasoningEffort = Literal[
    "low",
    "medium",
    "high",
    "max",
]

# Broad model class selector.
ModelClass = Literal[
    "haiku",
    "sonnet",
    "opus",
    "custom",
]


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

_TOOL_ACCESS_RANK: dict[str, int] = {
    "none": 0,
    "read_only": 1,
    "write_local": 2,
    "write_all": 3,
    "full": 4,
}


def tool_access_allows(current: ToolAccess, required: ToolAccess) -> bool:
    """Return ``True`` if *current* access level is >= *required*."""
    return _TOOL_ACCESS_RANK.get(current, 0) >= _TOOL_ACCESS_RANK.get(required, 0)


_EFFORT_RANK: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "max": 4,
}


def effort_at_least(current: ReasoningEffort, minimum: ReasoningEffort) -> bool:
    """Return ``True`` if *current* reasoning effort meets *minimum*."""
    return _EFFORT_RANK.get(current, 0) >= _EFFORT_RANK.get(minimum, 0)
