"""
Runtime State Management MCP Server.

Provides state read/write/clear/list tools for workflow modes.
Storage: .omx/state/{mode}-state.json
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .bootstrap import (
    McpServer,
    ToolDefinition,
    ToolResult,
    auto_start_stdio_mcp_server,
    error_result,
    text_result,
)
from .state_paths import (
    get_all_scoped_state_paths,
    get_base_state_dir,
    get_read_scoped_state_dirs,
    get_read_scoped_state_paths,
    get_state_dir,
    get_state_path,
    resolve_state_scope,
    resolve_working_directory_for_state,
)
from .validation import validate_session_id

# ── Constants ────────────────────────────────────────────────────────────────

SUPPORTED_MODES = (
    "autopilot",
    "team",
    "ralph",
    "ultrawork",
    "ultraqa",
    "ralplan",
    "deep-interview",
)

# ── Write lock ───────────────────────────────────────────────────────────────

_write_locks: Dict[str, asyncio.Lock] = {}


def _get_write_lock(path: str) -> asyncio.Lock:
    if path not in _write_locks:
        _write_locks[path] = asyncio.Lock()
    return _write_locks[path]


def _atomic_write(path: str, data: str) -> None:
    """Write data atomically via temp file + rename."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        os.write(fd, data.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Server ───────────────────────────────────────────────────────────────────


class StateServer:
    """MCP server providing runtime state management tools."""

    def _build_tools(self) -> List[ToolDefinition]:
        mode_enum = list(SUPPORTED_MODES)
        return [
            ToolDefinition(
                name="state_read",
                description="Read state for a specific mode. Returns JSON state data or indicates no state exists.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": mode_enum},
                        "workingDirectory": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["mode"],
                },
            ),
            ToolDefinition(
                name="state_write",
                description="Write/update state for a specific mode. Creates directories if needed.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": mode_enum},
                        "active": {"type": "boolean"},
                        "iteration": {"type": "number"},
                        "max_iterations": {"type": "number"},
                        "current_phase": {"type": "string"},
                        "task_description": {"type": "string"},
                        "started_at": {"type": "string"},
                        "completed_at": {"type": "string"},
                        "error": {"type": "string"},
                        "state": {"type": "object", "description": "Additional custom fields"},
                        "workingDirectory": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["mode"],
                },
            ),
            ToolDefinition(
                name="state_clear",
                description="Clear/delete state for a specific mode.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": mode_enum},
                        "workingDirectory": {"type": "string"},
                        "session_id": {"type": "string"},
                        "all_sessions": {"type": "boolean"},
                    },
                    "required": ["mode"],
                },
            ),
            ToolDefinition(
                name="state_list_active",
                description="List all currently active modes.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workingDirectory": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                },
            ),
            ToolDefinition(
                name="state_get_status",
                description="Get detailed status for a specific mode or all modes.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": mode_enum},
                        "workingDirectory": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                },
            ),
        ]

    async def list_tools(self) -> List[ToolDefinition]:
        return self._build_tools()

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        a = arguments or {}

        # Resolve working directory
        try:
            wd = resolve_working_directory_for_state(a.get("workingDirectory"))
        except ValueError as e:
            return error_result(str(e))

        # Validate session_id
        try:
            explicit_session_id = validate_session_id(a.get("session_id"))
        except ValueError as e:
            return error_result(str(e))

        try:
            scope = await asyncio.get_event_loop().run_in_executor(
                None, resolve_state_scope, wd, explicit_session_id
            )
            effective_session_id = scope.session_id

            # Ensure state directories exist
            state_dir = get_state_dir(wd)
            Path(state_dir).mkdir(parents=True, exist_ok=True)
            if effective_session_id:
                session_dir = get_state_dir(wd, effective_session_id)
                Path(session_dir).mkdir(parents=True, exist_ok=True)

            if name == "state_read":
                mode = a.get("mode", "")
                if mode not in SUPPORTED_MODES:
                    return error_result(f"mode must be one of: {', '.join(SUPPORTED_MODES)}")
                paths = get_read_scoped_state_paths(mode, wd, explicit_session_id)
                for p in paths:
                    if Path(p).exists():
                        data = Path(p).read_text("utf-8")
                        return ToolResult(content=[__import__("mcp.bootstrap", fromlist=["TextContent"]).TextContent(text=data)])
                return text_result({"exists": False, "mode": mode})

            elif name == "state_write":
                mode = a.get("mode", "")
                path = get_state_path(mode, wd, effective_session_id)
                # Extract fields (exclude meta-keys)
                skip_keys = {"mode", "workingDirectory", "session_id", "state"}
                fields = {k: v for k, v in a.items() if k not in skip_keys}
                custom_state = a.get("state", {}) or {}

                lock = _get_write_lock(path)
                async with lock:
                    existing: Dict[str, Any] = {}
                    if Path(path).exists():
                        try:
                            existing = json.loads(Path(path).read_text("utf-8"))
                        except (json.JSONDecodeError, OSError):
                            pass

                    merged = {**existing, **fields, **custom_state}

                    # Add runtime context
                    if "started_at" in merged and merged.get("active"):
                        merged.setdefault("_updated_at", __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat())

                    _atomic_write(path, json.dumps(merged, indent=2))

                return text_result({"success": True, "mode": mode, "path": path})

            elif name == "state_clear":
                mode = a.get("mode", "")
                all_sessions = a.get("all_sessions", False)

                if not all_sessions:
                    path = get_state_path(mode, wd, effective_session_id)
                    if Path(path).exists():
                        Path(path).unlink()
                    return text_result({"cleared": True, "mode": mode, "path": path})

                # Clear all session-scoped state files
                removed: List[str] = []
                all_paths = get_all_scoped_state_paths(mode, wd)
                for p in all_paths:
                    if Path(p).exists():
                        Path(p).unlink()
                        removed.append(p)
                return text_result({
                    "cleared": True,
                    "mode": mode,
                    "all_sessions": True,
                    "removed": len(removed),
                    "paths": removed,
                    "warning": "all_sessions clears global and session-scoped state files",
                })

            elif name == "state_list_active":
                state_dirs = get_read_scoped_state_dirs(wd, explicit_session_id)
                active: List[str] = []
                seen_modes: Set[str] = set()
                for sd in state_dirs:
                    sd_path = Path(sd)
                    if not sd_path.exists():
                        continue
                    for f in sorted(sd_path.iterdir()):
                        if not f.name.endswith("-state.json"):
                            continue
                        mode = f.name.replace("-state.json", "")
                        if mode in seen_modes:
                            continue
                        seen_modes.add(mode)
                        try:
                            data = json.loads(f.read_text("utf-8"))
                            if data.get("active"):
                                active.append(mode)
                        except (json.JSONDecodeError, OSError):
                            pass
                return text_result({"active_modes": active})

            elif name == "state_get_status":
                mode = a.get("mode")
                state_dirs = get_read_scoped_state_dirs(wd, explicit_session_id)
                statuses: Dict[str, Any] = {}
                seen_modes: Set[str] = set()
                for sd in state_dirs:
                    sd_path = Path(sd)
                    if not sd_path.exists():
                        continue
                    for f in sorted(sd_path.iterdir()):
                        if not f.name.endswith("-state.json"):
                            continue
                        m = f.name.replace("-state.json", "")
                        if mode and m != mode:
                            continue
                        if m in seen_modes:
                            continue
                        seen_modes.add(m)
                        try:
                            data = json.loads(f.read_text("utf-8"))
                            statuses[m] = {
                                "active": data.get("active"),
                                "phase": data.get("current_phase"),
                                "path": str(f),
                                "data": data,
                            }
                        except (json.JSONDecodeError, OSError):
                            statuses[m] = {"error": "malformed state file"}
                return text_result({"statuses": statuses})

            return error_result(f"Unknown tool: {name}")

        except Exception as e:
            return error_result(str(e))

    async def close(self) -> None:
        _write_locks.clear()


def main() -> None:
    auto_start_stdio_mcp_server("state", StateServer())


if __name__ == "__main__":
    main()
