"""
Config.toml generator/merger for pyclaude.

Merges Pyclaude MCP server entries and feature flags into existing config.toml.

TOML structure reminder: bare key=value pairs after a [table] header belong
to that table. Top-level (root-table) keys MUST appear before the first
[table] header. This generator therefore splits its output into:
  1. Top-level keys  (notify, model_reasoning_effort, developer_instructions)
  2. [features] flags
  3. [table] sections (env, mcp_servers, tui)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import DEFAULT_FRONTIER_MODEL
from .mcp_registry import UnifiedMcpRegistryServer


@dataclass
class MergeOptions:
    include_tui: bool = True
    model_override: Optional[str] = None
    shared_mcp_servers: list[UnifiedMcpRegistryServer] = field(default_factory=list)
    shared_mcp_registry_source: Optional[str] = None
    verbose: bool = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PYCLAUDE_TOP_LEVEL_KEYS = [
    "notify",
    "model_reasoning_effort",
    "developer_instructions",
]

DEFAULT_SETUP_MODEL = DEFAULT_FRONTIER_MODEL
DEFAULT_SETUP_MODEL_CONTEXT_WINDOW = 1_000_000
DEFAULT_SETUP_MODEL_AUTO_COMPACT_TOKEN_LIMIT = 900_000
SHARED_MCP_REGISTRY_MARKER = "pyclaude Pyclaude Shared MCP Registry Sync"
SHARED_MCP_REGISTRY_END_MARKER = "# End pyclaude shared MCP registry sync"
PYCLAUDE_AGENTS_MAX_THREADS = 6
PYCLAUDE_AGENTS_MAX_DEPTH = 2
PYCLAUDE_EXPLORE_ROUTING_DEFAULT = "1"
PYCLAUDE_EXPLORE_CMD_ENV = "USE_PYCLAUDE_EXPLORE_CMD"
PYCLAUDE_TUI_STATUS_LINE = (
    'status_line = ["model-with-reasoning", "git-branch", "context-remaining",'
    ' "total-input-tokens", "total-output-tokens", "five-hour-limit", "weekly-limit"]'
)


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _unwrap_toml_string(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    m = re.match(r'^"(.*)"$', value)
    return m.group(1) if m else None


def _parse_root_key_values(config: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in config.split("\n"):
        if re.match(r"^\s*\[", line):
            break
        m = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.+?)\s*$", line)
        if m:
            values[m.group(1)] = m.group(2)
    return values


def get_root_model_name(config: str) -> Optional[str]:
    return _unwrap_toml_string(_parse_root_key_values(config).get("model"))


def _get_omx_top_level_lines(
    pkg_root: str,
    existing_config: str = "",
    model_override: Optional[str] = None,
) -> list[str]:
    notify_hook_path = str(Path(pkg_root) / "dist" / "scripts" / "notify-hook.js")
    escaped_path = _escape_toml_string(notify_hook_path)
    root_values = _parse_root_key_values(existing_config)

    lines = [
        "# pyclaude top-level settings (must be before any [table])",
        f'notify = ["node", "{escaped_path}"]',
        'model_reasoning_effort = "high"',
        (
            'developer_instructions = "You have pyclaude installed. AGENTS.md is your '
            "orchestration brain and the main orchestration surface. Use skill/keyword routing "
            "like $name plus spawned role-specialized subagents for specialized work. Codex "
            "native subagents are available via .codex/agents and may be used for independent "
            "parallel subtasks within a single session or team pane. Skills are loaded from "
            "installed SKILL.md files under .codex/skills, not from native agent TOMLs. Use "
            "workflow skills via $name when explicitly invoked or clearly routed by AGENTS.md. "
            "Treat installed prompts as narrower internal execution surfaces under AGENTS.md "
            'authority, even when user-facing docs prefer $name keywords."'
        ),
    ]

    existing_model = root_values.get("model")
    existing_context_window = root_values.get("model_context_window")
    existing_auto_compact = root_values.get("model_auto_compact_token_limit")
    selected_model = (
        model_override
        or _unwrap_toml_string(existing_model)
        or DEFAULT_SETUP_MODEL
    )

    if model_override or not existing_model:
        lines.append(f'model = "{selected_model}"')

    if (
        selected_model == DEFAULT_SETUP_MODEL
        and not existing_context_window
        and not existing_auto_compact
    ):
        lines.append(f"model_context_window = {DEFAULT_SETUP_MODEL_CONTEXT_WINDOW}")
        lines.append(
            f"model_auto_compact_token_limit = {DEFAULT_SETUP_MODEL_AUTO_COMPACT_TOKEN_LIMIT}"
        )

    return lines


def _strip_root_level_keys(config: str, keys: list[str]) -> str:
    lines = config.split("\n")

    if any(k in PYCLAUDE_TOP_LEVEL_KEYS for k in keys):
        lines = [
            l
            for l in lines
            if l.strip()
            != "# pyclaude top-level settings (must be before any [table])"
        ]

    first_table = -1
    for i, l in enumerate(lines):
        if re.match(r"^\s*\[", l):
            first_table = i
            break
    boundary = first_table if first_table >= 0 else len(lines)

    result: list[str] = []
    for i, line in enumerate(lines):
        if i < boundary:
            is_managed = any(
                re.match(rf"^\s*{re.escape(key)}\s*=", line) for key in keys
            )
            if is_managed:
                continue
        result.append(line)

    return "\n".join(result)


def _strip_orphaned_managed_notify(config: str) -> str:
    config = re.sub(
        r'^\s*notify\s*=\s*\["node",\s*".*notify-hook\.js"\]\s*$\n?',
        "",
        config,
        flags=re.MULTILINE,
    )
    config = re.sub(
        r'\n?\s*"node",\s*\n\s*".*notify-hook\.js",\s*\n\s*\]\s*(?=\n|$)',
        "",
        config,
    )
    return config


def strip_omx_top_level_keys(config: str) -> str:
    """Remove any existing Pyclaude-managed top-level keys so we can re-insert them cleanly."""
    return _strip_root_level_keys(config, list(PYCLAUDE_TOP_LEVEL_KEYS))


def _upsert_feature_flags(config: str) -> str:
    lines = config.split("\n")
    features_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^\s*\[features\]\s*$", line):
            features_start = i
            break

    if features_start < 0:
        base = config.rstrip()
        feature_block = "[features]\nmulti_agent = true\nchild_agents_md = true\n"
        if not base:
            return feature_block
        return f"{base}\n{feature_block}"

    section_end = len(lines)
    for i in range(features_start + 1, len(lines)):
        if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", lines[i]):
            section_end = i
            break

    # Remove deprecated 'collab' key
    i = section_end - 1
    while i > features_start:
        if re.match(r"^\s*collab\s*=", lines[i]):
            lines.pop(i)
            section_end -= 1
        i -= 1

    multi_agent_idx = -1
    child_agents_idx = -1
    for i in range(features_start + 1, section_end):
        if re.match(r"^\s*multi_agent\s*=", lines[i]):
            multi_agent_idx = i
        elif re.match(r"^\s*child_agents_md\s*=", lines[i]):
            child_agents_idx = i

    if multi_agent_idx >= 0:
        lines[multi_agent_idx] = "multi_agent = true"
    else:
        lines.insert(section_end, "multi_agent = true")
        section_end += 1

    if child_agents_idx >= 0:
        lines[child_agents_idx] = "child_agents_md = true"
    else:
        lines.insert(section_end, "child_agents_md = true")

    return "\n".join(lines)


def _upsert_env_settings(config: str) -> str:
    lines = config.split("\n")
    env_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^\s*\[env\]\s*$", line):
            env_start = i
            break

    if env_start < 0:
        base = config.rstrip()
        env_block = f'[env]\n{PYCLAUDE_EXPLORE_CMD_ENV} = "{PYCLAUDE_EXPLORE_ROUTING_DEFAULT}"\n'
        if not base:
            return env_block
        return f"{base}\n\n{env_block}"

    section_end = len(lines)
    for i in range(env_start + 1, len(lines)):
        if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", lines[i]):
            section_end = i
            break

    explore_idx = -1
    for i in range(env_start + 1, section_end):
        if re.match(rf"^\s*{PYCLAUDE_EXPLORE_CMD_ENV}\s*=", lines[i]):
            explore_idx = i
            break

    if explore_idx < 0:
        lines.insert(
            section_end,
            f'{PYCLAUDE_EXPLORE_CMD_ENV} = "{PYCLAUDE_EXPLORE_ROUTING_DEFAULT}"',
        )

    return "\n".join(lines)


def _upsert_agents_settings(config: str) -> str:
    lines = config.split("\n")
    agents_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^\s*\[agents\]\s*$", line):
            agents_start = i
            break

    if agents_start < 0:
        base = config.rstrip()
        agents_block = (
            f"[agents]\nmax_threads = {PYCLAUDE_AGENTS_MAX_THREADS}\n"
            f"max_depth = {PYCLAUDE_AGENTS_MAX_DEPTH}\n"
        )
        if not base:
            return agents_block
        return f"{base}\n\n{agents_block}"

    section_end = len(lines)
    for i in range(agents_start + 1, len(lines)):
        if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", lines[i]):
            section_end = i
            break

    max_threads_idx = -1
    max_depth_idx = -1
    for i in range(agents_start + 1, section_end):
        if re.match(r"^\s*max_threads\s*=", lines[i]):
            max_threads_idx = i
        elif re.match(r"^\s*max_depth\s*=", lines[i]):
            max_depth_idx = i

    if max_threads_idx < 0:
        lines.insert(section_end, f"max_threads = {PYCLAUDE_AGENTS_MAX_THREADS}")
        section_end += 1
    if max_depth_idx < 0:
        lines.insert(section_end, f"max_depth = {PYCLAUDE_AGENTS_MAX_DEPTH}")

    return "\n".join(lines)


def strip_omx_feature_flags(config: str) -> str:
    """Remove Pyclaude-managed feature flags from the [features] section."""
    lines = config.split("\n")
    features_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^\s*\[features\]\s*$", line):
            features_start = i
            break

    if features_start < 0:
        return config

    section_end = len(lines)
    for i in range(features_start + 1, len(lines)):
        if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", lines[i]):
            section_end = i
            break

    omx_flags = ["multi_agent", "child_agents_md", "collab"]
    filtered: list[str] = []
    for i, line in enumerate(lines):
        if features_start < i < section_end:
            if any(re.match(rf"^\s*{f}\s*=", line) for f in omx_flags):
                continue
        filtered.append(line)

    # If [features] section is now empty, remove the header too
    new_features_start = -1
    for i, l in enumerate(filtered):
        if re.match(r"^\s*\[features\]\s*$", l):
            new_features_start = i
            break
    if new_features_start >= 0:
        new_section_end = len(filtered)
        for i in range(new_features_start + 1, len(filtered)):
            if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", filtered[i]):
                new_section_end = i
                break
        section_content = filtered[new_features_start + 1 : new_section_end]
        if all(l.strip() == "" for l in section_content):
            del filtered[new_features_start:new_section_end]

    return "\n".join(filtered)


def strip_omx_env_settings(config: str) -> str:
    lines = config.split("\n")
    env_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^\s*\[env\]\s*$", line):
            env_start = i
            break

    if env_start < 0:
        return config

    section_end = len(lines)
    for i in range(env_start + 1, len(lines)):
        if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", lines[i]):
            section_end = i
            break

    filtered: list[str] = []
    for i, line in enumerate(lines):
        if env_start < i < section_end:
            if re.match(rf"^\s*{PYCLAUDE_EXPLORE_CMD_ENV}\s*=", line):
                continue
        filtered.append(line)

    new_env_start = -1
    for i, line in enumerate(filtered):
        if re.match(r"^\s*\[env\]\s*$", line):
            new_env_start = i
            break
    if new_env_start >= 0:
        new_section_end = len(filtered)
        for i in range(new_env_start + 1, len(filtered)):
            if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", filtered[i]):
                new_section_end = i
                break
        env_content = filtered[new_env_start + 1 : new_section_end]
        if all(l.strip() == "" for l in env_content):
            del filtered[new_env_start:new_section_end]

    return "\n".join(filtered)


def _strip_orphaned_omx_sections(config: str) -> str:
    """Strip Pyclaude-managed table sections that exist outside the marker block."""
    lines = config.split("\n")
    result: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        table_match = re.match(r"^\s*\[([^\]]+)\]\s*$", line)

        if table_match:
            table_name = table_match.group(1)
            is_omx_section = bool(re.match(r"^mcp_servers\.omx_", table_name))
            # Note: agent section detection omitted (requires AGENT_DEFINITIONS)

            if is_omx_section:
                while result and (
                    result[-1].strip() == ""
                    or re.match(r"^#\s*(Pyclaude|pyclaude)", result[-1], re.IGNORECASE)
                ):
                    result.pop()
                i += 1
                while i < len(lines) and not re.match(r"^\s*\[", lines[i]):
                    i += 1
                continue

        result.append(line)
        i += 1

    return "\n".join(result)


def _upsert_tui_status_line(config: str) -> tuple[str, bool]:
    lines = config.split("\n")
    sections: list[tuple[int, int]] = []

    i = 0
    while i < len(lines):
        if re.match(r"^\s*\[tui\]\s*$", lines[i]):
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if re.match(r"^\s*\[\[?[^\]]+\]?\]\s*$", lines[j]):
                    end = j
                    break
            sections.append((i, end))
            i = end
        else:
            i += 1

    if not sections:
        return config, False

    preserved_key_lines: list[str] = []
    seen_keys: set[str] = set()

    for start, end in sections:
        for idx in range(start + 1, end):
            trimmed = lines[idx].strip()
            if not trimmed or trimmed.startswith("#"):
                continue
            key_match = re.match(r"^([A-Za-z0-9_-]+)\s*=", trimmed)
            if not key_match:
                continue
            key = key_match.group(1)
            if key == "status_line" or key in seen_keys:
                continue
            seen_keys.add(key)
            preserved_key_lines.append(trimmed)

    merged_section = ["[tui]"] + preserved_key_lines + [PYCLAUDE_TUI_STATUS_LINE]
    first_start = sections[0][0]
    rebuilt: list[str] = []

    i = 0
    while i < len(lines):
        section = next((s for s in sections if s[0] == i), None)
        if section:
            if i == first_start:
                if rebuilt and rebuilt[-1].strip() != "":
                    rebuilt.append("")
                rebuilt.extend(merged_section)
                rebuilt.append("")
            i = section[1]
            continue
        rebuilt.append(lines[i])
        i += 1

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(rebuilt))
    return cleaned, True


def strip_existing_pyclaude_blocks(config: str) -> tuple[str, int]:
    """Strip Pyclaude configuration blocks. Returns (cleaned, removed_count)."""
    marker = "pyclaude Pyclaude Configuration"
    end_marker = "# End pyclaude"
    cleaned = config
    removed = 0

    while True:
        marker_idx = cleaned.find(marker)
        if marker_idx < 0:
            break

        block_start = cleaned.rfind("\n", 0, marker_idx)
        block_start = block_start + 1 if block_start >= 0 else 0

        prev_line_end = block_start - 1
        if prev_line_end >= 0:
            prev_line_start = cleaned.rfind("\n", 0, prev_line_end - 1)
            prev_line = cleaned[prev_line_start + 1 : prev_line_end]
            if re.match(r"^# =+$", prev_line.strip()):
                block_start = prev_line_start + 1 if prev_line_start >= 0 else 0

        block_end = len(cleaned)
        end_idx = cleaned.find(end_marker, marker_idx)
        if end_idx >= 0:
            end_line_break = cleaned.find("\n", end_idx)
            block_end = end_line_break + 1 if end_line_break >= 0 else len(cleaned)

        before = cleaned[:block_start].rstrip()
        after = cleaned[block_end:].lstrip()
        parts = [p for p in (before, after) if p]
        cleaned = "\n\n".join(parts)
        removed += 1

    return cleaned, removed


def strip_existing_shared_mcp_registry_block(config: str) -> tuple[str, int]:
    cleaned = config
    removed = 0

    while True:
        marker_idx = cleaned.find(SHARED_MCP_REGISTRY_MARKER)
        if marker_idx < 0:
            break

        block_start = cleaned.rfind("\n", 0, marker_idx)
        block_start = block_start + 1 if block_start >= 0 else 0

        prev_line_end = block_start - 1
        if prev_line_end >= 0:
            prev_line_start = cleaned.rfind("\n", 0, prev_line_end - 1)
            prev_line = cleaned[prev_line_start + 1 : prev_line_end]
            if re.match(r"^# =+$", prev_line.strip()):
                block_start = prev_line_start + 1 if prev_line_start >= 0 else 0

        block_end = len(cleaned)
        end_idx = cleaned.find(SHARED_MCP_REGISTRY_END_MARKER, marker_idx)
        if end_idx >= 0:
            end_line_break = cleaned.find("\n", end_idx)
            block_end = end_line_break + 1 if end_line_break >= 0 else len(cleaned)

        before = cleaned[:block_start].rstrip()
        after = cleaned[block_end:].lstrip()
        parts = [p for p in (before, after) if p]
        cleaned = "\n\n".join(parts)
        removed += 1

    return cleaned, removed


def _to_mcp_server_table_key(name: str) -> str:
    if re.match(r"^[A-Za-z0-9_-]+$", name):
        return f"mcp_servers.{name}"
    return f'mcp_servers."{_escape_toml_string(name)}"'


def _config_has_mcp_server(config: str, name: str) -> bool:
    table_name = re.escape(_to_mcp_server_table_key(name))
    return bool(re.search(rf"^\s*\[{table_name}\]\s*$", config, re.MULTILINE))


def _get_shared_mcp_registry_block(
    servers: list[UnifiedMcpRegistryServer],
    source_path: Optional[str],
    existing_config: str,
) -> str:
    if not servers:
        return ""
    deduped = [s for s in servers if not _config_has_mcp_server(existing_config, s.name)]
    if not deduped:
        return ""

    lines = [
        "# ============================================================",
        f"# {SHARED_MCP_REGISTRY_MARKER}",
        "# Managed by omx setup - edit the registry file instead",
    ]
    if source_path:
        lines.append(f"# Source: {source_path}")
    lines.extend([
        "# ============================================================",
        "",
    ])

    for server in deduped:
        lines.append(f"# Shared MCP Server: {server.name}")
        lines.append(f"[{_to_mcp_server_table_key(server.name)}]")
        lines.append(f'command = "{_escape_toml_string(server.command)}"')
        args_str = ", ".join(f'"{_escape_toml_string(a)}"' for a in server.args)
        lines.append(f"args = [{args_str}]")
        lines.append(f"enabled = {'true' if server.enabled else 'false'}")
        if server.startup_timeout_sec is not None:
            lines.append(f"startup_timeout_sec = {server.startup_timeout_sec}")
        lines.append("")

    lines.append("# ============================================================")
    lines.append(SHARED_MCP_REGISTRY_END_MARKER)
    return "\n".join(lines)


def _get_omx_tables_block(pkg_root: str, include_tui: bool = True) -> str:
    state_server = _escape_toml_string(
        str(Path(pkg_root) / "dist" / "mcp" / "state-server.js")
    )
    memory_server = _escape_toml_string(
        str(Path(pkg_root) / "dist" / "mcp" / "memory-server.js")
    )
    code_intel_server = _escape_toml_string(
        str(Path(pkg_root) / "dist" / "mcp" / "code-intel-server.js")
    )
    trace_server = _escape_toml_string(
        str(Path(pkg_root) / "dist" / "mcp" / "trace-server.js")
    )
    team_server = _escape_toml_string(
        str(Path(pkg_root) / "dist" / "mcp" / "team-server.js")
    )

    parts = [
        "",
        "# ============================================================",
        "# pyclaude Pyclaude Configuration",
        "# Managed by omx setup - manual edits preserved on next setup",
        "# ============================================================",
        "",
        "# Pyclaude State Management MCP Server",
        "[mcp_servers.omx_state]",
        'command = "node"',
        f'args = ["{state_server}"]',
        "enabled = true",
        "startup_timeout_sec = 5",
        "",
        "# Pyclaude Project Memory MCP Server",
        "[mcp_servers.omx_memory]",
        'command = "node"',
        f'args = ["{memory_server}"]',
        "enabled = true",
        "startup_timeout_sec = 5",
        "",
        "# Pyclaude Code Intelligence MCP Server (LSP diagnostics, AST search)",
        "[mcp_servers.omx_code_intel]",
        'command = "node"',
        f'args = ["{code_intel_server}"]',
        "enabled = true",
        "startup_timeout_sec = 10",
        "",
        "# Pyclaude Trace MCP Server (agent flow timeline & statistics)",
        "[mcp_servers.omx_trace]",
        'command = "node"',
        f'args = ["{trace_server}"]',
        "enabled = true",
        "startup_timeout_sec = 5",
        "",
        "# Pyclaude Team MCP Server (team job lifecycle: start, status, wait, cleanup)",
        "[mcp_servers.omx_team_run]",
        'command = "node"',
        f'args = ["{team_server}"]',
        "enabled = true",
        "startup_timeout_sec = 5",
    ]

    if include_tui:
        parts.extend([
            "",
            "# Pyclaude TUI StatusLine (Codex CLI v0.101.0+)",
            "[tui]",
            PYCLAUDE_TUI_STATUS_LINE,
            "",
        ])

    parts.extend([
        "# ============================================================",
        "# End pyclaude",
        "",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_merged_config(
    existing_config: str,
    pkg_root: str,
    options: Optional[MergeOptions] = None,
) -> str:
    """Merge Pyclaude config into existing config.toml."""
    if options is None:
        options = MergeOptions()

    existing = existing_config
    include_tui = options.include_tui

    if "pyclaude Pyclaude Configuration" in existing:
        existing, _ = strip_existing_pyclaude_blocks(existing)
    if SHARED_MCP_REGISTRY_MARKER in existing:
        existing, _ = strip_existing_shared_mcp_registry_block(existing)

    existing = strip_omx_top_level_keys(existing)
    existing = _strip_orphaned_managed_notify(existing)
    if options.model_override:
        existing = _strip_root_level_keys(existing, ["model"])
    existing = _strip_orphaned_omx_sections(existing)
    existing = _upsert_feature_flags(existing)
    existing = _upsert_env_settings(existing)
    existing = _upsert_agents_settings(existing)

    if include_tui:
        existing, had_existing_tui = _upsert_tui_status_line(existing)
    else:
        had_existing_tui = False

    top_lines = _get_omx_top_level_lines(pkg_root, existing, options.model_override)
    tables_block = _get_omx_tables_block(
        pkg_root, include_tui and not had_existing_tui
    )
    shared_registry_block = _get_shared_mcp_registry_block(
        options.shared_mcp_servers,
        options.shared_mcp_registry_source,
        existing,
    )

    body = existing.rstrip()
    if shared_registry_block:
        body = f"{body}\n\n{shared_registry_block}" if body else shared_registry_block

    return "\n".join(top_lines) + "\n\n" + body + "\n" + tables_block


async def repair_config_if_needed(
    config_path: str,
    pkg_root: str,
    options: Optional[MergeOptions] = None,
) -> bool:
    """Detect and repair duplicate TOML table headers in config.toml."""
    p = Path(config_path)
    if not p.exists():
        return False

    content = p.read_text("utf-8")
    tui_count = len(re.findall(r"^\s*\[tui\]\s*$", content, re.MULTILINE))
    if tui_count <= 1:
        return False

    repaired = build_merged_config(content, pkg_root, options)
    p.write_text(repaired, "utf-8")
    return True


async def merge_config(
    config_path: str,
    pkg_root: str,
    options: Optional[MergeOptions] = None,
) -> None:
    """Merge Pyclaude config and write to disk."""
    if options is None:
        options = MergeOptions()

    p = Path(config_path)
    existing = ""
    if p.exists():
        existing = p.read_text("utf-8")

    if "pyclaude Pyclaude Configuration" in existing:
        _, removed = strip_existing_pyclaude_blocks(existing)
        if options.verbose and removed > 0:
            print("  Updating existing Pyclaude config block.")

    final_config = build_merged_config(existing, pkg_root, options)
    p.write_text(final_config, "utf-8")
    if options.verbose:
        print(f"  Written to {config_path}")
