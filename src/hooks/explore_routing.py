"""
Explore Routing - routes simple exploration prompts to the explore agent.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

OMX_EXPLORE_CMD_ENV = "USE_OMX_EXPLORE_CMD"

_DISABLED_VALUES = {"0", "false", "no", "off"}

SIMPLE_EXPLORATION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\b(where|find|locate|search|grep|ripgrep)\b", re.IGNORECASE),
    re.compile(r"\b(file|files|path|paths|symbol|symbols|usage|usages|reference|references)\b", re.IGNORECASE),
    re.compile(r"\b(pattern|patterns|match|matches|matching)\b", re.IGNORECASE),
    re.compile(r"\bhow does\b", re.IGNORECASE),
    re.compile(r"\bwhich\b.*\b(contain|contains|define|defines|use|uses)\b", re.IGNORECASE),
    re.compile(r"\b(read[- ]only|explor(?:e|ation)|inspect|lookup|look up|map)\b", re.IGNORECASE),
]

NON_EXPLORATION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\b(implement|write|edit|modify|change|refactor|fix|patch|add|remove|delete)\b", re.IGNORECASE),
    re.compile(r"\b(build|create)\b.*\b(feature|system|workflow|integration|module)\b", re.IGNORECASE),
    re.compile(r"\b(migrate|rewrite|overhaul|redesign)\b", re.IGNORECASE),
    re.compile(r"\b(test|lint|typecheck|compile|deploy)\b", re.IGNORECASE),
]


def is_explore_command_routing_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    """Check if explore command routing is enabled via environment variable."""
    if env is None:
        env = dict(os.environ)
    raw = env.get(OMX_EXPLORE_CMD_ENV)
    if raw is None:
        return True  # Default on
    return raw.strip().lower() not in _DISABLED_VALUES


def is_simple_exploration_prompt(text: str) -> bool:
    """
    Check if a prompt is a simple exploration query.
    Returns False if the prompt contains non-exploration intent (edit, implement, etc.).
    Returns True if exploration patterns are detected.
    """
    trimmed = text.strip()
    if not trimmed:
        return False
    if any(p.search(trimmed) for p in NON_EXPLORATION_PATTERNS):
        return False
    return any(p.search(trimmed) for p in SIMPLE_EXPLORATION_PATTERNS)


def build_explore_routing_guidance(env: Optional[Dict[str, str]] = None) -> str:
    """Build explore routing guidance text for injection into AGENTS.md."""
    if not is_explore_command_routing_enabled(env):
        return ""
    return "\n".join([
        f"**Explore Command Preference:** enabled via `{OMX_EXPLORE_CMD_ENV}` (default-on; opt out with `0`, `false`, `no`, or `off`)",
        "- Advisory steering only: agents SHOULD treat `omx explore` as the default first stop for direct inspection and SHOULD reserve `omx sparkshell` for qualifying read-only shell-native tasks.",
        "- For simple file/symbol lookups, use `omx explore` FIRST before attempting full code analysis.",
        "- When the user asks for a simple read-only exploration task (file/symbol/pattern/relationship lookup), strongly prefer `omx explore` as the default surface.",
        '- Explore examples: `omx explore --prompt "which files define TeamPolicy"`, `omx explore --prompt "find usages of buildExploreRoutingGuidance"`.',
        "- SparkShell examples: use `omx sparkshell -- rg -n \"TeamPolicy\" src`, `omx sparkshell -- npm test`, or `omx sparkshell --tmux-pane %12` for noisy verification, bounded shell output, or tmux-pane summaries.",
        "- Keep `omx explore` prompts narrow and concrete; prefer a single lookup goal or a small related cluster, using `--prompt` for quick asks and `--prompt-file` for longer reusable briefs.",
        "- Treat `omx explore` as a shell-only allowlisted read-only path; keep edits, tests, diagnostics, MCP/web needs, and complex shell composition on the richer normal path.",
        "- Keep implementation, refactor, test, or ambiguous broad requests on the normal Codex path.",
        "- If `omx explore` is unavailable, stalls, or fails, retry with a narrower prompt or gracefully fall back to the normal path.",
    ])
