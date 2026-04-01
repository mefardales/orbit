"""
Native agent config generation for Codex CLI.
Writes standalone TOML files under ~/.codex/agents/ or ./.codex/agents/.

Ported from pyclaude src/agents/native-config.ts.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .definitions import (
    AGENT_DEFINITIONS,
    AgentDefinition,
    ModelClass,
    Posture,
    ReasoningEffort,
    RoutingRole,
)

EXACT_GPT_5_4_MINI_MODEL = "gpt-5.4-mini"

# ---------------------------------------------------------------------------
# Posture overlays
# ---------------------------------------------------------------------------

POSTURE_OVERLAYS: Dict[Posture, str] = {
    "frontier-orchestrator": "\n".join([
        "<posture_overlay>",
        "",
        "You are operating in the frontier-orchestrator posture.",
        "- Prioritize intent classification before implementation.",
        "- Default to delegation and orchestration when specialists exist.",
        "- Treat the first decision as a routing problem: research vs planning vs implementation vs verification.",
        "- Challenge flawed user assumptions concisely before execution when the design is likely to cause avoidable problems.",
        "- Preserve explicit executor handoff boundaries: do not absorb deep implementation work when a specialized executor is more appropriate.",
        "",
        "</posture_overlay>",
    ]),
    "deep-worker": "\n".join([
        "<posture_overlay>",
        "",
        "You are operating in the deep-worker posture.",
        "- Once the task is clearly implementation-oriented, bias toward direct execution and end-to-end completion.",
        "- Explore first, then implement minimal changes that match existing patterns.",
        "- Keep verification strict: diagnostics, tests, and build evidence are mandatory before claiming completion.",
        "- Escalate only after materially different approaches fail or when architecture tradeoffs exceed local implementation scope.",
        "",
        "</posture_overlay>",
    ]),
    "fast-lane": "\n".join([
        "<posture_overlay>",
        "",
        "You are operating in the fast-lane posture.",
        "- Optimize for fast triage, search, lightweight synthesis, and narrow routing decisions.",
        "- Do not start deep implementation unless the task is tightly bounded and obvious.",
        "- If the task expands beyond quick classification or lightweight execution, escalate to a frontier-orchestrator or deep-worker role.",
        "- Keep responses concise, scope-aware, and conservative under ambiguity.",
        "",
        "</posture_overlay>",
    ]),
}

# ---------------------------------------------------------------------------
# Model-class overlays
# ---------------------------------------------------------------------------

MODEL_CLASS_OVERLAYS: Dict[ModelClass, str] = {
    "frontier": "\n".join([
        "<model_class_guidance>",
        "",
        "This role is tuned for frontier-class models.",
        "- Use the model's steerability for coordination, tradeoff reasoning, and precise delegation.",
        "- Favor clean routing decisions over impulsive implementation.",
        "",
        "</model_class_guidance>",
    ]),
    "standard": "\n".join([
        "<model_class_guidance>",
        "",
        "This role is tuned for standard-capability models.",
        "- Balance autonomy with clear boundaries.",
        "- Prefer explicit verification and narrow scope control over speculative reasoning.",
        "",
        "</model_class_guidance>",
    ]),
    "fast": "\n".join([
        "<model_class_guidance>",
        "",
        "This role is tuned for fast/low-latency models.",
        "- Prefer quick search, synthesis, and routing over prolonged reasoning.",
        "- Escalate rather than bluff when deeper work is required.",
        "",
        "</model_class_guidance>",
    ]),
}

# ---------------------------------------------------------------------------
# Exact mini-model overlay
# ---------------------------------------------------------------------------

EXACT_MINI_MODEL_OVERLAY = "\n".join([
    "<exact_model_guidance>",
    "",
    f"This role is executing under the exact {EXACT_GPT_5_4_MINI_MODEL} model.",
    "- Use a strict execution order: inspect -> plan -> act -> verify.",
    "- Treat completion criteria as explicit: only report done after the requested work is implemented and fresh verification passes.",
    "- If requirements are ambiguous or a blocker appears, state the blocker plainly and stop guessing until the missing decision is resolved.",
    "- Do not bluff, pad, or invent results; report missing evidence and incomplete work honestly.",
    "",
    "</exact_model_guidance>",
])

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GeneratedNativeAgentConfig:
    name: str
    description: str
    developer_instructions: Optional[str] = None
    model: Optional[str] = None
    reasoning_effort: Optional[ReasoningEffort] = None


@dataclass
class RoleInstructionMetadata:
    name: str
    posture: Posture
    model_class: ModelClass
    routing_role: RoutingRole


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

def _read_config_toml_content(
    codex_home_override: Optional[str] = None,
    provided: Optional[str] = None,
) -> str:
    """Read config.toml content, using provided string or reading from disk."""
    if provided is not None:
        return provided
    config_path = Path(codex_home_override or os.environ.get("CODEX_HOME", "")) / "config.toml"
    if codex_home_override and config_path.is_file():
        return config_path.read_text(encoding="utf-8")
    return ""


def _resolve_frontier_model(
    codex_home_override: Optional[str] = None,
    config_toml_content: Optional[str] = None,
) -> str:
    """Resolve the frontier-class model name.

    In the original TS this delegates to getRootModelName / getMainDefaultModel.
    Here we provide a simplified default; callers can override via config.
    """
    content = _read_config_toml_content(codex_home_override, config_toml_content)
    # Try to extract model from TOML content
    match = re.search(r'^model\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if match:
        return match.group(1)
    return os.environ.get("CODEX_DEFAULT_MODEL", "o3")


def _resolve_standard_model(
    codex_home_override: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """Resolve the standard-class model name."""
    environ = env if env is not None else dict(os.environ)
    explicit = environ.get("CODEX_STANDARD_MODEL")
    if explicit:
        return explicit
    return environ.get("CODEX_DEFAULT_MODEL", "o3-mini")


def _resolve_fast_model(codex_home_override: Optional[str] = None) -> str:
    """Resolve the fast/spark-class model name."""
    return os.environ.get("CODEX_SPARK_MODEL", "gpt-5.4-mini")


def resolve_agent_model(
    agent: AgentDefinition,
    codex_home_override: Optional[str] = None,
    config_toml_content: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """Determine which model an agent should use based on its model_class."""
    # executor always gets frontier model
    if agent.name == "executor":
        return _resolve_frontier_model(codex_home_override, config_toml_content)

    if agent.model_class == "frontier":
        return _resolve_frontier_model(codex_home_override, config_toml_content)
    elif agent.model_class == "fast":
        return _resolve_fast_model(codex_home_override)
    else:  # standard
        return _resolve_standard_model(codex_home_override, env)


def _is_exact_mini_model(resolved_model: Optional[str]) -> bool:
    return (resolved_model or "").strip() == EXACT_GPT_5_4_MINI_MODEL


# ---------------------------------------------------------------------------
# Frontmatter stripping
# ---------------------------------------------------------------------------

def strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter (between --- markers) from markdown content."""
    match = re.match(r"^---\r?\n[\s\S]*?\r?\n---\r?\n?", content)
    if match:
        return content[match.end():].strip()
    return content.strip()


# ---------------------------------------------------------------------------
# Instruction composition
# ---------------------------------------------------------------------------

def compose_role_instructions(
    prompt_content: str,
    metadata: Optional[RoleInstructionMetadata] = None,
    resolved_model: Optional[str] = None,
) -> str:
    """Assemble full agent instructions from prompt content, posture/model overlays, and metadata."""
    instructions = strip_frontmatter(prompt_content)
    parts: List[str] = [instructions]

    if metadata:
        parts.append("")
        parts.append(POSTURE_OVERLAYS[metadata.posture])
        parts.append("")
        parts.append(MODEL_CLASS_OVERLAYS[metadata.model_class])

    if _is_exact_mini_model(resolved_model):
        parts.append("")
        parts.append(EXACT_MINI_MODEL_OVERLAY)

    metadata_lines: List[str] = []
    if metadata:
        metadata_lines.extend([
            "## Pyclaude Agent Metadata",
            f"- role: {metadata.name}",
            f"- posture: {metadata.posture}",
            f"- model_class: {metadata.model_class}",
            f"- routing_role: {metadata.routing_role}",
        ])
    if resolved_model:
        if not metadata_lines:
            metadata_lines.append("## Pyclaude Agent Metadata")
        metadata_lines.append(f"- resolved_model: {resolved_model}")
    if metadata_lines:
        parts.append("")
        parts.extend(metadata_lines)

    return "\n".join(parts)


def compose_role_instructions_for_role(
    role_name: str,
    prompt_content: str,
    resolved_model: Optional[str] = None,
) -> str:
    """Compose instructions for a named role, looking up its definition automatically."""
    agent = AGENT_DEFINITIONS.get(role_name)
    metadata: Optional[RoleInstructionMetadata] = None
    if agent:
        metadata = RoleInstructionMetadata(
            name=agent.name,
            posture=agent.posture,
            model_class=agent.model_class,
            routing_role=agent.routing_role,
        )
    return compose_role_instructions(prompt_content, metadata, resolved_model)


# ---------------------------------------------------------------------------
# TOML generation
# ---------------------------------------------------------------------------

def _escape_toml_multiline(s: str) -> str:
    """Escape content for TOML triple-quoted strings.

    TOML triple-quoted strings only need to escape sequences of 3+ consecutive quotes.
    """
    return re.sub(
        r'"{3,}',
        lambda m: '\\"\\"'.join('' for _ in range(len(m.group(0)))) + '\\"' * (len(m.group(0)) % 2 == 0),
        s,
    ) if '"""' in s else s


def _escape_toml_basic_string(s: str) -> str:
    """Escape content for TOML basic (double-quoted) strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def generate_standalone_agent_toml(config: GeneratedNativeAgentConfig) -> str:
    """Generate a standalone TOML config string from a GeneratedNativeAgentConfig."""
    lines = [
        f"# pyclaude agent: {config.name}",
        f'name = "{_escape_toml_basic_string(config.name)}"',
        f'description = "{_escape_toml_basic_string(config.description)}"',
    ]

    if config.model:
        lines.append(f'model = "{_escape_toml_basic_string(config.model)}"')
    if config.reasoning_effort:
        lines.append(f'model_reasoning_effort = "{config.reasoning_effort}"')
    if config.developer_instructions and config.developer_instructions.strip():
        escaped = _escape_toml_multiline(config.developer_instructions)
        lines.append('developer_instructions = """')
        lines.append(escaped)
        lines.append('"""')

    lines.append("")
    return "\n".join(lines)


def generate_agent_toml(
    agent: AgentDefinition,
    prompt_content: str,
    codex_home_override: Optional[str] = None,
    config_toml_content: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """Generate TOML content for a prompt-backed Pyclaude role agent."""
    resolved_model = resolve_agent_model(agent, codex_home_override, config_toml_content, env)
    metadata = RoleInstructionMetadata(
        name=agent.name,
        posture=agent.posture,
        model_class=agent.model_class,
        routing_role=agent.routing_role,
    )
    return generate_standalone_agent_toml(GeneratedNativeAgentConfig(
        name=agent.name,
        description=agent.description,
        developer_instructions=compose_role_instructions(prompt_content, metadata, resolved_model),
        model=resolved_model,
        reasoning_effort=agent.reasoning_effort,
    ))


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def codex_agents_dir() -> Path:
    """Default agents directory: ~/.codex/agents/"""
    return Path.home() / ".codex" / "agents"


def install_native_agent_configs(
    pkg_root: str,
    *,
    force: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    agents_dir: Optional[Path] = None,
) -> int:
    """Install prompt-backed native agent config .toml files.

    Reads prompt markdown from ``{pkg_root}/prompts/{name}.md`` and writes
    TOML configs to ``agents_dir`` (defaults to ``~/.codex/agents/``).

    Returns the number of agent files written.
    """
    if agents_dir is None:
        agents_dir = codex_agents_dir()

    codex_home_override = str(agents_dir.parent)

    if not dry_run:
        agents_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for name, agent in AGENT_DEFINITIONS.items():
        prompt_path = Path(pkg_root) / "prompts" / f"{name}.md"
        if not prompt_path.is_file():
            if verbose:
                print(f"  skip {name} (no prompt file)")
            continue

        dst = agents_dir / f"{name}.toml"
        if not force and dst.is_file():
            if verbose:
                print(f"  skip {name} (already exists)")
            continue

        prompt_content = prompt_path.read_text(encoding="utf-8")
        toml = generate_agent_toml(agent, prompt_content, codex_home_override=codex_home_override)

        if not dry_run:
            dst.write_text(toml, encoding="utf-8")
        if verbose:
            print(f"  {name}.toml")
        count += 1

    return count
