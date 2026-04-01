"""Agents module -- agent definitions and native config generation."""

from .definitions import (
    AgentDefinition,
    AGENT_DEFINITIONS,
    Category,
    ModelClass,
    Posture,
    ReasoningEffort,
    RoutingRole,
    ToolAccess,
    get_agent,
    get_agent_names,
    get_agents_by_category,
)
from .native_config import (
    GeneratedNativeAgentConfig,
    RoleInstructionMetadata,
    compose_role_instructions,
    compose_role_instructions_for_role,
    generate_agent_toml,
    generate_standalone_agent_toml,
    install_native_agent_configs,
    resolve_agent_model,
    strip_frontmatter,
)

__all__ = [
    # definitions
    "AgentDefinition",
    "AGENT_DEFINITIONS",
    "Category",
    "ModelClass",
    "Posture",
    "ReasoningEffort",
    "RoutingRole",
    "ToolAccess",
    "get_agent",
    "get_agent_names",
    "get_agents_by_category",
    # native_config
    "GeneratedNativeAgentConfig",
    "RoleInstructionMetadata",
    "compose_role_instructions",
    "compose_role_instructions_for_role",
    "generate_agent_toml",
    "generate_standalone_agent_toml",
    "install_native_agent_configs",
    "resolve_agent_model",
    "strip_frontmatter",
]
