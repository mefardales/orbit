"""
Keyword Registry - definitions of all trigger keywords and their skill mappings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class KeywordTriggerDefinition:
    """A keyword trigger mapping a phrase to a skill with priority and guidance."""

    keyword: str
    skill: str
    priority: int
    guidance: str


KEYWORD_TRIGGER_DEFINITIONS: List[KeywordTriggerDefinition] = [
    KeywordTriggerDefinition("ralph", "ralph", 9, "Activate ralph persistence loop with verification"),
    KeywordTriggerDefinition("don't stop", "ralph", 9, "Activate ralph persistence loop with verification"),
    KeywordTriggerDefinition("must complete", "ralph", 9, "Activate ralph persistence loop with verification"),
    KeywordTriggerDefinition("keep going", "ralph", 9, "Activate ralph persistence loop with verification"),

    KeywordTriggerDefinition("autopilot", "autopilot", 10, "Activate autopilot skill for autonomous execution"),
    KeywordTriggerDefinition("build me", "autopilot", 10, "Activate autopilot skill for autonomous execution"),
    KeywordTriggerDefinition("I want a", "autopilot", 10, "Activate autopilot skill for autonomous execution"),

    KeywordTriggerDefinition("ultrawork", "ultrawork", 10, "Activate ultrawork parallel execution mode"),
    KeywordTriggerDefinition("ulw", "ultrawork", 10, "Activate ultrawork parallel execution mode"),
    KeywordTriggerDefinition("parallel", "ultrawork", 10, "Activate ultrawork parallel execution mode"),
    KeywordTriggerDefinition("ultraqa", "ultraqa", 8, "Activate UltraQA cycling workflow"),
    KeywordTriggerDefinition("analyze", "analyze", 7, "Activate deep analysis workflow"),
    KeywordTriggerDefinition("investigate", "analyze", 7, "Activate deep analysis workflow"),

    KeywordTriggerDefinition("deep interview", "deep-interview", 8, "Activate Ouroboros-inspired Socratic ambiguity-gated interview workflow"),
    KeywordTriggerDefinition("gather requirements", "deep-interview", 8, "Activate Ouroboros-inspired Socratic ambiguity-gated interview workflow"),
    KeywordTriggerDefinition("interview me", "deep-interview", 8, "Activate Ouroboros-inspired Socratic ambiguity-gated interview workflow"),
    KeywordTriggerDefinition("don't assume", "deep-interview", 8, "Activate Ouroboros-inspired Socratic ambiguity-gated interview workflow"),
    KeywordTriggerDefinition("ouroboros", "deep-interview", 8, "Activate Ouroboros-inspired Socratic ambiguity-gated interview workflow"),
    KeywordTriggerDefinition("interview", "deep-interview", 8, "Activate Ouroboros-inspired Socratic ambiguity-gated interview workflow"),

    KeywordTriggerDefinition("plan this", "plan", 8, "Activate planning skill"),
    KeywordTriggerDefinition("plan the", "plan", 8, "Activate planning skill"),
    KeywordTriggerDefinition("let's plan", "plan", 8, "Activate planning skill"),

    KeywordTriggerDefinition("ralplan", "ralplan", 11, "Activate consensus planning (planner + architect + critic)"),
    KeywordTriggerDefinition("consensus plan", "ralplan", 11, "Activate consensus planning (planner + architect + critic)"),

    KeywordTriggerDefinition("team", "team", 8, "Activate coordinated team mode"),
    KeywordTriggerDefinition("swarm", "team", 8, "Activate coordinated team mode (swarm is a compatibility alias for team)"),
    KeywordTriggerDefinition("coordinated team", "team", 8, "Activate coordinated team mode"),
    KeywordTriggerDefinition("coordinated swarm", "team", 8, "Activate coordinated team mode (swarm is a compatibility alias for team)"),

    KeywordTriggerDefinition("cancel", "cancel", 5, "Cancel active execution modes"),
    KeywordTriggerDefinition("stop", "cancel", 5, "Cancel active execution modes"),
    KeywordTriggerDefinition("abort", "cancel", 5, "Cancel active execution modes"),

    KeywordTriggerDefinition("tdd", "tdd", 6, "Activate test-driven workflow"),
    KeywordTriggerDefinition("test first", "tdd", 6, "Activate test-driven workflow"),

    KeywordTriggerDefinition("fix build", "build-fix", 6, "Activate build-fix workflow"),
    KeywordTriggerDefinition("type errors", "build-fix", 6, "Activate build-fix workflow"),

    KeywordTriggerDefinition("code review", "code-review", 6, "Activate code-review workflow"),
    KeywordTriggerDefinition("code-review", "code-review", 6, "Activate code-review workflow"),
    KeywordTriggerDefinition("review code", "code-review", 6, "Activate code-review workflow"),
    KeywordTriggerDefinition("security review", "security-review", 6, "Activate security-review workflow"),
]


def compare_keyword_matches(
    a: dict[str, object],
    b: dict[str, object],
) -> int:
    """
    Compare two keyword matches for sorting.
    Higher priority first, then longer keyword first, then alphabetical.
    Returns negative if a should come first, positive if b should come first.
    """
    a_pri = int(a.get("priority", 0))  # type: ignore[arg-type]
    b_pri = int(b.get("priority", 0))  # type: ignore[arg-type]
    if b_pri != a_pri:
        return b_pri - a_pri

    a_kw = str(a.get("keyword", ""))
    b_kw = str(b.get("keyword", ""))
    if len(b_kw) != len(a_kw):
        return len(b_kw) - len(a_kw)

    if a_kw < b_kw:
        return -1
    if a_kw > b_kw:
        return 1
    return 0
