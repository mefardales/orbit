"""
Agent role definitions for orbit.
Each agent has a name, description, default reasoning effort, and tool access pattern.
Prompt content is loaded from the prompts/ directory at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

ReasoningEffort = Literal["low", "medium", "high"]
Posture = Literal["frontier-orchestrator", "deep-worker", "fast-lane"]
ModelClass = Literal["frontier", "standard", "fast"]
RoutingRole = Literal["leader", "specialist", "executor"]
ToolAccess = Literal["read-only", "analysis", "execution", "data"]
Category = Literal["build", "review", "domain", "product", "coordination"]


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    reasoning_effort: ReasoningEffort
    posture: Posture
    model_class: ModelClass
    routing_role: RoutingRole
    tools: ToolAccess
    category: Category


# Shared agent instances referenced by multiple keys
_EXECUTOR_AGENT = AgentDefinition(
    name="executor",
    description="Code implementation, refactoring, feature work",
    reasoning_effort="high",
    posture="deep-worker",
    model_class="standard",
    routing_role="executor",
    tools="execution",
    category="build",
)

_TEAM_EXECUTOR_AGENT = AgentDefinition(
    name="team-executor",
    description="Supervised team execution for conservative delivery lanes",
    reasoning_effort="medium",
    posture="deep-worker",
    model_class="frontier",
    routing_role="executor",
    tools="execution",
    category="build",
)

AGENT_DEFINITIONS: Dict[str, AgentDefinition] = {
    # ── Build/Analysis Lane ───────────────────────────────────────────
    "explore": AgentDefinition(
        name="explore",
        description="Fast codebase search and file/symbol mapping",
        reasoning_effort="low",
        posture="fast-lane",
        model_class="fast",
        routing_role="specialist",
        tools="read-only",
        category="build",
    ),
    "analyst": AgentDefinition(
        name="analyst",
        description="Requirements clarity, acceptance criteria, hidden constraints",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="frontier",
        routing_role="leader",
        tools="analysis",
        category="build",
    ),
    "planner": AgentDefinition(
        name="planner",
        description="Task sequencing, execution plans, risk flags",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="frontier",
        routing_role="leader",
        tools="analysis",
        category="build",
    ),
    "architect": AgentDefinition(
        name="architect",
        description="System design, boundaries, interfaces, long-horizon tradeoffs",
        reasoning_effort="high",
        posture="frontier-orchestrator",
        model_class="frontier",
        routing_role="leader",
        tools="read-only",
        category="build",
    ),
    "debugger": AgentDefinition(
        name="debugger",
        description="Root-cause analysis, regression isolation, failure diagnosis",
        reasoning_effort="high",
        posture="deep-worker",
        model_class="standard",
        routing_role="executor",
        tools="analysis",
        category="build",
    ),
    "executor": _EXECUTOR_AGENT,
    "team-executor": _TEAM_EXECUTOR_AGENT,
    "verifier": AgentDefinition(
        name="verifier",
        description="Completion evidence, claim validation, test adequacy",
        reasoning_effort="high",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="leader",
        tools="analysis",
        category="build",
    ),

    # ── Review Lane ───────────────────────────────────────────────────
    "style-reviewer": AgentDefinition(
        name="style-reviewer",
        description="Formatting, naming, idioms, lint conventions",
        reasoning_effort="low",
        posture="fast-lane",
        model_class="fast",
        routing_role="specialist",
        tools="read-only",
        category="review",
    ),
    "quality-reviewer": AgentDefinition(
        name="quality-reviewer",
        description="Logic defects, maintainability, anti-patterns",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="leader",
        tools="read-only",
        category="review",
    ),
    "api-reviewer": AgentDefinition(
        name="api-reviewer",
        description="API contracts, versioning, backward compatibility",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="leader",
        tools="read-only",
        category="review",
    ),
    "security-reviewer": AgentDefinition(
        name="security-reviewer",
        description="Vulnerabilities, trust boundaries, authn/authz",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="frontier",
        routing_role="leader",
        tools="read-only",
        category="review",
    ),
    "performance-reviewer": AgentDefinition(
        name="performance-reviewer",
        description="Hotspots, complexity, memory/latency optimization",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="leader",
        tools="read-only",
        category="review",
    ),
    "code-reviewer": AgentDefinition(
        name="code-reviewer",
        description="Comprehensive review across all concerns",
        reasoning_effort="high",
        posture="frontier-orchestrator",
        model_class="frontier",
        routing_role="leader",
        tools="read-only",
        category="review",
    ),

    # ── Domain Specialists ────────────────────────────────────────────
    "dependency-expert": AgentDefinition(
        name="dependency-expert",
        description="External SDK/API/package evaluation",
        reasoning_effort="high",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="specialist",
        tools="analysis",
        category="domain",
    ),
    "test-engineer": AgentDefinition(
        name="test-engineer",
        description="Test strategy, coverage, flaky-test hardening",
        reasoning_effort="medium",
        posture="deep-worker",
        model_class="frontier",
        routing_role="executor",
        tools="execution",
        category="domain",
    ),
    "quality-strategist": AgentDefinition(
        name="quality-strategist",
        description="Quality strategy, release readiness, risk assessment",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="leader",
        tools="analysis",
        category="domain",
    ),
    "build-fixer": AgentDefinition(
        name="build-fixer",
        description="Build/toolchain/type failures resolution",
        reasoning_effort="high",
        posture="deep-worker",
        model_class="standard",
        routing_role="executor",
        tools="execution",
        category="domain",
    ),
    "designer": AgentDefinition(
        name="designer",
        description="UX/UI architecture, interaction design",
        reasoning_effort="high",
        posture="deep-worker",
        model_class="standard",
        routing_role="executor",
        tools="execution",
        category="domain",
    ),
    "writer": AgentDefinition(
        name="writer",
        description="Documentation, migration notes, user guidance",
        reasoning_effort="high",
        posture="fast-lane",
        model_class="standard",
        routing_role="specialist",
        tools="execution",
        category="domain",
    ),
    "qa-tester": AgentDefinition(
        name="qa-tester",
        description="Interactive CLI/service runtime validation",
        reasoning_effort="low",
        posture="deep-worker",
        model_class="standard",
        routing_role="executor",
        tools="execution",
        category="domain",
    ),
    "git-master": AgentDefinition(
        name="git-master",
        description="Commit strategy, history hygiene, rebasing",
        reasoning_effort="high",
        posture="deep-worker",
        model_class="standard",
        routing_role="executor",
        tools="execution",
        category="domain",
    ),
    "code-simplifier": AgentDefinition(
        name="code-simplifier",
        description="Simplifies recently modified code for clarity and consistency without changing behavior",
        reasoning_effort="high",
        posture="deep-worker",
        model_class="frontier",
        routing_role="executor",
        tools="execution",
        category="domain",
    ),
    "researcher": AgentDefinition(
        name="researcher",
        description="External documentation and reference research",
        reasoning_effort="high",
        posture="fast-lane",
        model_class="standard",
        routing_role="specialist",
        tools="analysis",
        category="domain",
    ),

    # ── Product Lane ──────────────────────────────────────────────────
    "product-manager": AgentDefinition(
        name="product-manager",
        description="Problem framing, personas/JTBD, PRDs",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="leader",
        tools="analysis",
        category="product",
    ),
    "ux-researcher": AgentDefinition(
        name="ux-researcher",
        description="Heuristic audits, usability, accessibility",
        reasoning_effort="medium",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="specialist",
        tools="analysis",
        category="product",
    ),
    "information-architect": AgentDefinition(
        name="information-architect",
        description="Taxonomy, navigation, findability",
        reasoning_effort="low",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="specialist",
        tools="analysis",
        category="product",
    ),
    "product-analyst": AgentDefinition(
        name="product-analyst",
        description="Product metrics, funnel analysis, experiments",
        reasoning_effort="low",
        posture="frontier-orchestrator",
        model_class="standard",
        routing_role="specialist",
        tools="analysis",
        category="product",
    ),

    # ── Coordination ──────────────────────────────────────────────────
    "critic": AgentDefinition(
        name="critic",
        description="Plan/design critical challenge and review",
        reasoning_effort="high",
        posture="frontier-orchestrator",
        model_class="frontier",
        routing_role="leader",
        tools="read-only",
        category="coordination",
    ),
    "vision": AgentDefinition(
        name="vision",
        description="Image/screenshot/diagram analysis",
        reasoning_effort="low",
        posture="fast-lane",
        model_class="frontier",
        routing_role="specialist",
        tools="read-only",
        category="coordination",
    ),
}


def get_agent(name: str) -> Optional[AgentDefinition]:
    """Get agent definition by name."""
    return AGENT_DEFINITIONS.get(name)


def get_agents_by_category(category: Category) -> List[AgentDefinition]:
    """Get all agents in a category."""
    return [a for a in AGENT_DEFINITIONS.values() if a.category == category]


def get_agent_names() -> List[str]:
    """Get all agent names."""
    return list(AGENT_DEFINITIONS.keys())
