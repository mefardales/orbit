"""
Unified MCP Registry loader and Claude Code settings sync planner.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class UnifiedMcpRegistryServer:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    enabled: bool = True
    startup_timeout_sec: Optional[int] = None


@dataclass
class UnifiedMcpRegistryLoadResult:
    servers: list[UnifiedMcpRegistryServer] = field(default_factory=list)
    source_path: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ClaudeCodeMcpServerConfig:
    command: str
    args: list[str]
    enabled: bool


@dataclass
class ClaudeCodeSettingsSyncPlan:
    content: Optional[str] = None
    added: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _normalize_timeout(
    value: Any, name: str, warnings: list[str]
) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        warnings.append(
            f'registry entry "{name}" has invalid timeout; ignoring timeout'
        )
        return None
    return int(value)


def _normalize_entry(
    name: str, value: Any, warnings: list[str]
) -> Optional[UnifiedMcpRegistryServer]:
    if not _is_record(value):
        warnings.append(f'registry entry "{name}" is not an object; skipping')
        return None

    command = value.get("command")
    if not isinstance(command, str) or not command.strip():
        warnings.append(f'registry entry "{name}" is missing command; skipping')
        return None

    args_value = value.get("args")
    if args_value is not None:
        if not isinstance(args_value, list) or any(
            not isinstance(item, str) for item in args_value
        ):
            warnings.append(
                f'registry entry "{name}" has non-string args; skipping'
            )
            return None

    enabled_value = value.get("enabled")
    if enabled_value is not None and not isinstance(enabled_value, bool):
        warnings.append(
            f'registry entry "{name}" has non-boolean enabled; skipping'
        )
        return None

    timeout_candidate = (
        value.get("timeout")
        or value.get("startup_timeout_sec")
        or value.get("startupTimeoutSec")
    )

    return UnifiedMcpRegistryServer(
        name=name,
        command=command,
        args=list(args_value) if args_value else [],
        enabled=enabled_value if enabled_value is not None else True,
        startup_timeout_sec=_normalize_timeout(timeout_candidate, name, warnings),
    )


def get_unified_mcp_registry_candidates(
    home_dir: Optional[str] = None,
) -> list[str]:
    home = Path(home_dir) if home_dir else Path.home()
    return [
        str(home / ".pyclaude" / "mcp-registry.json"),
        str(home / ".omc" / "mcp-registry.json"),
    ]


async def load_unified_mcp_registry(
    candidates: Optional[list[str]] = None,
    home_dir: Optional[str] = None,
) -> UnifiedMcpRegistryLoadResult:
    if candidates is None:
        candidates = get_unified_mcp_registry_candidates(home_dir)

    source_path: Optional[str] = None
    for candidate in candidates:
        if Path(candidate).exists():
            source_path = candidate
            break

    if not source_path:
        return UnifiedMcpRegistryLoadResult()

    warnings: list[str] = []
    try:
        parsed = json.loads(Path(source_path).read_text("utf-8"))
    except Exception as error:
        warnings.append(
            f"failed to parse shared MCP registry at {source_path}: {error}"
        )
        return UnifiedMcpRegistryLoadResult(
            source_path=source_path, warnings=warnings
        )

    if not _is_record(parsed):
        warnings.append(
            f"shared MCP registry at {source_path} must be a JSON object"
        )
        return UnifiedMcpRegistryLoadResult(
            source_path=source_path, warnings=warnings
        )

    servers: list[UnifiedMcpRegistryServer] = []
    for name, value in parsed.items():
        normalized = _normalize_entry(name, value, warnings)
        if normalized:
            servers.append(normalized)

    return UnifiedMcpRegistryLoadResult(
        servers=servers, source_path=source_path, warnings=warnings
    )


def _to_claude_code_mcp_server_config(
    server: UnifiedMcpRegistryServer,
) -> dict[str, Any]:
    return {
        "command": server.command,
        "args": list(server.args),
        "enabled": server.enabled,
    }


def plan_claude_code_mcp_settings_sync(
    existing_content: str,
    servers: list[UnifiedMcpRegistryServer],
) -> ClaudeCodeSettingsSyncPlan:
    if not servers:
        return ClaudeCodeSettingsSyncPlan()

    parsed: Any = {}
    trimmed = existing_content.strip()
    if trimmed:
        try:
            parsed = json.loads(existing_content)
        except Exception as error:
            return ClaudeCodeSettingsSyncPlan(
                warnings=[f"failed to parse Claude settings.json: {error}"]
            )

    if not _is_record(parsed):
        return ClaudeCodeSettingsSyncPlan(
            warnings=["Claude settings.json must contain a JSON object"]
        )

    current_mcp_servers = parsed.get("mcpServers")
    if current_mcp_servers is not None and not _is_record(current_mcp_servers):
        return ClaudeCodeSettingsSyncPlan(
            warnings=['Claude settings.json field "mcpServers" must be an object']
        )

    next_mcp_servers = dict(current_mcp_servers or {})
    added: list[str] = []
    unchanged: list[str] = []

    for server in servers:
        if server.name in next_mcp_servers:
            unchanged.append(server.name)
            continue
        next_mcp_servers[server.name] = _to_claude_code_mcp_server_config(server)
        added.append(server.name)

    if not added:
        return ClaudeCodeSettingsSyncPlan(added=added, unchanged=unchanged)

    result = {**parsed, "mcpServers": next_mcp_servers}
    return ClaudeCodeSettingsSyncPlan(
        content=json.dumps(result, indent=2) + "\n",
        added=added,
        unchanged=unchanged,
    )
