"""
Project Memory and Notepad MCP Server.

Provides persistent project memory (JSON) and session notepad (Markdown)
tools. Storage: .omx/project-memory.json, .omx/notepad.md
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .bootstrap import (
    McpServer,
    ToolDefinition,
    ToolResult,
    auto_start_stdio_mcp_server,
    error_result,
    text_result,
)
from .state_paths import resolve_working_directory_for_state
from .validation import parse_notepad_prune_days_old

# ── Path helpers ─────────────────────────────────────────────────────────────


def _memory_path(wd: str) -> Path:
    return Path(wd) / ".omx" / "project-memory.json"


def _notepad_path(wd: str) -> Path:
    return Path(wd) / ".omx" / "notepad.md"


def _ensure_omx_dir(wd: str) -> None:
    (Path(wd) / ".omx").mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically using a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, str(path))
    except BaseException:
        os.close(fd) if not os.get_inheritable(fd) else None
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Notepad section helpers ──────────────────────────────────────────────────


def _extract_section(content: str, section: str) -> str:
    header = f"## {section.upper()}"
    idx = content.find(header)
    if idx < 0:
        return ""
    start = idx + len(header)
    next_header = content.find("\n## ", start)
    if next_header < 0:
        return content[start:].strip()
    return content[start:next_header].strip()


def _replace_section(content: str, section: str, new_content: str) -> str:
    header = f"## {section}"
    idx = content.find(header)
    if idx < 0:
        return content + f"\n\n{header}\n{new_content}\n"
    next_header = content.find("\n## ", idx + len(header))
    if next_header < 0:
        return content[:idx] + f"{header}\n{new_content}\n"
    return content[:idx] + f"{header}\n{new_content}\n" + content[next_header:]


def _append_to_section(content: str, section: str, entry: str) -> str:
    header = f"## {section}"
    idx = content.find(header)
    if idx < 0:
        return content + f"\n\n{header}{entry}\n"
    next_header = content.find("\n## ", idx + len(header))
    if next_header < 0:
        return content + entry
    return content[:next_header] + entry + content[next_header:]


# ── Memory data helpers ──────────────────────────────────────────────────────


def _read_memory(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_memory(path: Path, data: Dict[str, Any]) -> None:
    _ensure_omx_dir(str(path.parent.parent))
    _atomic_write(path, json.dumps(data, indent=2))


def _read_notepad(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text("utf-8")
    except OSError:
        return ""


# ── MCP Server ───────────────────────────────────────────────────────────────


class MemoryServer:
    """MCP server providing project memory and notepad tools."""

    async def list_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="project_memory_read",
                description="Read project memory. Can read full memory or a specific section.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "section": {"type": "string", "enum": ["all", "techStack", "build", "conventions", "structure", "notes", "directives"]},
                        "workingDirectory": {"type": "string"},
                    },
                },
            ),
            ToolDefinition(
                name="project_memory_write",
                description="Write/update project memory. Can replace entirely or merge.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "memory": {"type": "object", "description": "Memory object to write"},
                        "merge": {"type": "boolean", "description": "Merge with existing (true) or replace (false)"},
                        "workingDirectory": {"type": "string"},
                    },
                    "required": ["memory"],
                },
            ),
            ToolDefinition(
                name="project_memory_add_note",
                description="Add a categorized note to project memory.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "content": {"type": "string"},
                        "workingDirectory": {"type": "string"},
                    },
                    "required": ["category", "content"],
                },
            ),
            ToolDefinition(
                name="project_memory_add_directive",
                description="Add a persistent directive to project memory.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "directive": {"type": "string"},
                        "priority": {"type": "string", "enum": ["high", "normal"]},
                        "context": {"type": "string"},
                        "workingDirectory": {"type": "string"},
                    },
                    "required": ["directive"],
                },
            ),
            ToolDefinition(
                name="notepad_read",
                description="Read notepad content. Can read full or a specific section.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "section": {"type": "string", "enum": ["all", "priority", "working", "manual"]},
                        "workingDirectory": {"type": "string"},
                    },
                },
            ),
            ToolDefinition(
                name="notepad_write_priority",
                description="Write to Priority Context section. Replaces existing. Keep under 500 chars.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "workingDirectory": {"type": "string"},
                    },
                    "required": ["content"],
                },
            ),
            ToolDefinition(
                name="notepad_write_working",
                description="Add timestamped entry to Working Memory section.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "workingDirectory": {"type": "string"},
                    },
                    "required": ["content"],
                },
            ),
            ToolDefinition(
                name="notepad_write_manual",
                description="Add entry to Manual section. Never auto-pruned.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "workingDirectory": {"type": "string"},
                    },
                    "required": ["content"],
                },
            ),
            ToolDefinition(
                name="notepad_prune",
                description="Prune Working Memory entries older than N days (default: 7).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "daysOld": {"type": "integer", "minimum": 0},
                        "workingDirectory": {"type": "string"},
                    },
                },
            ),
            ToolDefinition(
                name="notepad_stats",
                description="Get statistics about the notepad.",
                input_schema={
                    "type": "object",
                    "properties": {"workingDirectory": {"type": "string"}},
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        a = arguments or {}
        try:
            wd = resolve_working_directory_for_state(a.get("workingDirectory"))
        except ValueError as e:
            return error_result(str(e))

        # === Project Memory ===

        if name == "project_memory_read":
            mem_path = _memory_path(wd)
            if not mem_path.exists():
                return text_result({"exists": False})
            data = _read_memory(mem_path)
            section = a.get("section")
            if section and section != "all" and section in data:
                return text_result(data[section])
            return text_result(data)

        elif name == "project_memory_write":
            mem_path = _memory_path(wd)
            _ensure_omx_dir(wd)
            new_mem = a.get("memory", {})
            merge = a.get("merge", False)
            if merge and mem_path.exists():
                existing = _read_memory(mem_path)
                existing.update(new_mem)
                _write_memory(mem_path, existing)
            else:
                _write_memory(mem_path, new_mem)
            return text_result({"success": True})

        elif name == "project_memory_add_note":
            mem_path = _memory_path(wd)
            _ensure_omx_dir(wd)
            data = _read_memory(mem_path)
            if "notes" not in data:
                data["notes"] = []
            data["notes"].append({
                "category": a["category"],
                "content": a["content"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            _write_memory(mem_path, data)
            return text_result({"success": True, "noteCount": len(data["notes"])})

        elif name == "project_memory_add_directive":
            mem_path = _memory_path(wd)
            _ensure_omx_dir(wd)
            data = _read_memory(mem_path)
            if "directives" not in data:
                data["directives"] = []
            data["directives"].append({
                "directive": a["directive"],
                "priority": a.get("priority", "normal"),
                "context": a.get("context"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            _write_memory(mem_path, data)
            return text_result({"success": True, "directiveCount": len(data["directives"])})

        # === Notepad ===

        elif name == "notepad_read":
            note_path = _notepad_path(wd)
            if not note_path.exists():
                return text_result({"exists": False, "content": ""})
            content = _read_notepad(note_path)
            section = a.get("section")
            if section and section != "all":
                section_content = _extract_section(content, section)
                return text_result({"section": section, "content": section_content})
            return text_result({"content": content})

        elif name == "notepad_write_priority":
            note_path = _notepad_path(wd)
            _ensure_omx_dir(wd)
            existing = _read_notepad(note_path)
            existing = _replace_section(existing, "PRIORITY", a["content"][:500])
            _atomic_write(note_path, existing)
            return text_result({"success": True})

        elif name == "notepad_write_working":
            note_path = _notepad_path(wd)
            _ensure_omx_dir(wd)
            timestamp = datetime.now(timezone.utc).isoformat()
            entry = f"\n[{timestamp}] {a['content']}"
            existing = _read_notepad(note_path)
            existing = _append_to_section(existing, "WORKING MEMORY", entry)
            _atomic_write(note_path, existing)
            return text_result({"success": True})

        elif name == "notepad_write_manual":
            note_path = _notepad_path(wd)
            _ensure_omx_dir(wd)
            entry = f"\n{a['content']}"
            existing = _read_notepad(note_path)
            existing = _append_to_section(existing, "MANUAL", entry)
            _atomic_write(note_path, existing)
            return text_result({"success": True})

        elif name == "notepad_prune":
            note_path = _notepad_path(wd)
            if not note_path.exists():
                return text_result({"pruned": 0, "message": "No notepad file found"})

            parsed = parse_notepad_prune_days_old(a.get("daysOld"))
            if not parsed.ok:
                return error_result(parsed.error)

            cutoff_ms = datetime.now(timezone.utc).timestamp() * 1000 - parsed.days * 86_400_000
            content = _read_notepad(note_path)
            working_section = _extract_section(content, "WORKING MEMORY")
            if not working_section:
                return text_result({"pruned": 0, "message": "No working memory entries found"})

            lines = working_section.split("\n")
            pruned = 0
            kept: List[str] = []
            ts_re = __import__("re").compile(r"^\[(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)\]")
            for line in lines:
                m = ts_re.match(line)
                if m:
                    try:
                        entry_time = datetime.fromisoformat(m.group(1).rstrip("Z") + "+00:00").timestamp() * 1000
                        if entry_time < cutoff_ms:
                            pruned += 1
                            continue
                    except ValueError:
                        pass
                kept.append(line)

            if pruned > 0:
                updated = _replace_section(content, "WORKING MEMORY", "\n".join(kept))
                _atomic_write(note_path, updated)

            remaining = sum(1 for l in kept if ts_re.match(l))
            return text_result({"pruned": pruned, "remaining": remaining})

        elif name == "notepad_stats":
            note_path = _notepad_path(wd)
            if not note_path.exists():
                return text_result({"exists": False, "size": 0, "entryCount": 0, "oldestEntry": None})

            content = _read_notepad(note_path)
            size = note_path.stat().st_size
            working_section = _extract_section(content, "WORKING MEMORY")
            timestamps: List[str] = []
            if working_section:
                ts_re = __import__("re").compile(r"^\[(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)\]")
                for line in working_section.split("\n"):
                    m = ts_re.match(line)
                    if m:
                        timestamps.append(m.group(1))

            priority_section = _extract_section(content, "PRIORITY")
            manual_section = _extract_section(content, "MANUAL")
            return text_result({
                "exists": True,
                "size": size,
                "sections": {
                    "priority": len(priority_section) if priority_section else 0,
                    "working": len(timestamps),
                    "manual": len([l for l in manual_section.split("\n") if l.strip()]) if manual_section else 0,
                },
                "entryCount": len(timestamps),
                "oldestEntry": timestamps[0] if timestamps else None,
                "newestEntry": timestamps[-1] if timestamps else None,
            })

        return error_result(f"Unknown tool: {name}")

    async def close(self) -> None:
        pass


def main() -> None:
    auto_start_stdio_mcp_server("memory", MemoryServer())


if __name__ == "__main__":
    main()
