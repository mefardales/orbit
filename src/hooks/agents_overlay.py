"""
AGENTS.md Runtime Overlay.

Dynamically injects session-specific context into AGENTS.md before a session
launches, then strips it after session ends. Uses marker-bounded sections
for idempotent apply/strip cycles.

Injected context:
- Codebase map (directory/module structure)
- Active mode state
- Priority notepad content
- Project memory summary
- Compaction survival instructions
- Session metadata
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from .codebase_map import generate_codebase_map
from .explore_routing import build_explore_routing_guidance

START_MARKER = "<!-- OMX:RUNTIME:START -->"
END_MARKER = "<!-- OMX:RUNTIME:END -->"
WORKER_START_MARKER = "<!-- OMX:TEAM:WORKER:START -->"
WORKER_END_MARKER = "<!-- OMX:TEAM:WORKER:END -->"
MAX_OVERLAY_SIZE = 3500
SKILL_REFERENCE_PATTERN = re.compile(r"/skills/([^/\s`]+)/SKILL\.md\b")

SessionOrchestrationMode = Literal["default", "team"]


@dataclass
class OverlaySection:
    key: str
    text: str
    optional: bool


@dataclass
class GenerateOverlayOptions:
    orchestration_mode: SessionOrchestrationMode = "default"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _join_sections(sections: List[OverlaySection]) -> str:
    return "\n\n".join(s.text for s in sections)


def _cap_body_to_max(sections: List[OverlaySection], max_body: int) -> str:
    """Deterministic overflow: drop optional sections from end, then hard-truncate."""
    body = _join_sections(sections)
    if len(body) <= max_body:
        return body

    optional_indices = [i for i in range(len(sections) - 1, -1, -1) if sections[i].optional]
    current = list(sections)
    for idx in optional_indices:
        if idx < len(current):
            current.pop(idx)
        body = _join_sections(current)
        if len(body) <= max_body:
            return body

    if len(body) > max_body:
        if max_body <= 3:
            return "." * max(0, max_body)
        body = body[: max_body - 3] + "..."

    return body


def _get_compaction_instructions() -> str:
    return "\n".join([
        "Before context compaction, preserve critical state:",
        "1. Write progress checkpoint via state_write MCP tool",
        "2. Save key decisions to notepad via notepad_write_working",
        "3. If context is >80% full, proactively checkpoint state",
    ])


def _read_notepad_priority(cwd: str) -> str:
    """Read priority section from the notepad file."""
    notepad_path = Path(cwd) / ".omx" / "notepad.md"
    if not notepad_path.exists():
        return ""
    try:
        content = notepad_path.read_text()
        header = "## PRIORITY"
        idx = content.find(header)
        if idx < 0:
            return ""
        next_header = content.find("\n## ", idx + len(header))
        section = (
            content[idx + len(header) : next_header].strip()
            if next_header >= 0
            else content[idx + len(header) :].strip()
        )
        return section
    except OSError:
        return ""


def _read_project_memory_summary(cwd: str) -> str:
    """Read project memory summary."""
    mem_path = Path(cwd) / ".omx" / "project-memory.json"
    if not mem_path.exists():
        return ""
    try:
        data = json.loads(mem_path.read_text())
        parts: List[str] = []
        if data.get("techStack"):
            parts.append(f"- Stack: {data['techStack']}")
        if data.get("conventions"):
            parts.append(f"- Conventions: {data['conventions']}")
        if data.get("build"):
            parts.append(f"- Build: {data['build']}")
        directives = data.get("directives", [])
        if isinstance(directives, list):
            high_priority = [d for d in directives if isinstance(d, dict) and d.get("priority") == "high"]
            for d in high_priority[:3]:
                parts.append(f"- Directive: {d.get('directive', '')}")
        return "\n".join(parts)
    except (OSError, json.JSONDecodeError):
        return ""


def _read_active_modes(cwd: str, session_id: Optional[str] = None) -> str:
    """Read active mode states from state directory."""
    state_dir = Path(cwd) / ".omx" / "state"
    if not state_dir.exists():
        return ""
    modes: List[str] = []
    try:
        for p in sorted(state_dir.glob("*-state.json")):
            try:
                data = json.loads(p.read_text())
                if not data.get("active"):
                    continue
                mode_name = p.stem.replace("-state", "")
                details: List[str] = []
                if "iteration" in data:
                    details.append(f"iteration {data['iteration']}/{data.get('max_iterations', '?')}")
                if data.get("current_phase"):
                    details.append(f"phase: {data['current_phase']}")
                modes.append(f"- {mode_name}: {', '.join(details) or 'active'}")
            except (json.JSONDecodeError, OSError):
                continue
    except OSError:
        pass
    return "\n".join(modes)


async def generate_overlay(
    cwd: str,
    session_id: Optional[str] = None,
    options: Optional[GenerateOverlayOptions] = None,
) -> str:
    """
    Generate the overlay content to inject into AGENTS.md.
    Total output is capped at MAX_OVERLAY_SIZE chars.
    """
    if options is None:
        options = GenerateOverlayOptions()

    active_modes = _read_active_modes(cwd, session_id)
    notepad_priority = _read_notepad_priority(cwd)
    project_memory = _read_project_memory_summary(cwd)
    codebase_map = await generate_codebase_map(cwd)
    explore_guidance = build_explore_routing_guidance()

    sections: List[OverlaySection] = []

    # Session metadata - required
    session_meta = f"**Session:** {session_id or 'unknown'} | {datetime.now(timezone.utc).isoformat()}"
    sections.append(OverlaySection(key="session", text=_truncate(session_meta, 200), optional=False))

    # Codebase map - optional
    if codebase_map:
        sections.append(OverlaySection(
            key="codebase_map",
            text=f"**Codebase Map:**\n{_truncate(codebase_map, 1000)}",
            optional=True,
        ))

    # Active modes - optional
    if active_modes:
        sections.append(OverlaySection(
            key="active_modes",
            text=f"**Active Modes:**\n{_truncate(active_modes, 600)}",
            optional=True,
        ))

    # Priority notepad - optional
    if notepad_priority:
        sections.append(OverlaySection(
            key="priority_notes",
            text=f"**Priority Notes:**\n{_truncate(notepad_priority, 600)}",
            optional=True,
        ))

    # Project memory - optional
    if project_memory:
        sections.append(OverlaySection(
            key="project_context",
            text=f"**Project Context:**\n{_truncate(project_memory, 1000)}",
            optional=True,
        ))

    # Explore routing guidance - optional
    if explore_guidance:
        sections.append(OverlaySection(
            key="explore_routing",
            text=_truncate(explore_guidance, 600),
            optional=True,
        ))

    # Compaction protocol - required
    sections.append(OverlaySection(
        key="compaction",
        text=f"**Compaction Protocol:**\n{_truncate(_get_compaction_instructions(), 380)}",
        optional=False,
    ))

    prefix = f"{START_MARKER}\n<session_context>\n"
    suffix = f"\n</session_context>\n{END_MARKER}"
    max_body = max(0, MAX_OVERLAY_SIZE - len(prefix) - len(suffix))
    body = _cap_body_to_max(sections, max_body)

    overlay = f"{prefix}{body}{suffix}"
    if len(overlay) <= MAX_OVERLAY_SIZE:
        return overlay

    # Fallback: minimal overlay
    safe_sections = [
        OverlaySection(key="session", text=_truncate(session_meta, 200), optional=False),
        OverlaySection(
            key="compaction",
            text=f"**Compaction Protocol:**\n{_truncate(_get_compaction_instructions(), 380)}",
            optional=False,
        ),
    ]
    safe_body = _cap_body_to_max(safe_sections, max_body)
    return f"{prefix}{safe_body}{suffix}"[:MAX_OVERLAY_SIZE]


def strip_overlay_content(content: str) -> str:
    """Remove overlay markers and content from a string (pure function)."""
    result = content
    max_iterations = 50

    for _ in range(max_iterations):
        start_idx = result.find(START_MARKER)
        if start_idx < 0:
            break

        end_idx = result.find(END_MARKER, start_idx)
        if end_idx < 0:
            # Malformed block - find next known marker
            candidates = []
            next_start = result.find(START_MARKER, start_idx + len(START_MARKER))
            if next_start >= 0:
                candidates.append(next_start)
            next_worker_start = result.find(WORKER_START_MARKER, start_idx + len(START_MARKER))
            if next_worker_start >= 0:
                candidates.append(next_worker_start)
            next_worker_end = result.find(WORKER_END_MARKER, start_idx + len(START_MARKER))
            if next_worker_end >= 0:
                candidates.append(next_worker_end)

            if not candidates:
                result = result[:start_idx].rstrip() + "\n"
                break

            next_marker_idx = min(candidates)
            before = result[:start_idx].rstrip()
            after = result[next_marker_idx:].lstrip()
            result = f"{before}\n{after}" if after else f"{before}\n"
            continue

        before = result[:start_idx].rstrip()
        after = result[end_idx + len(END_MARKER):].lstrip()
        result = f"{before}\n{after}" if after else f"{before}\n"

    return result


async def apply_overlay(agents_md_path: str, overlay: str, cwd: Optional[str] = None) -> None:
    """Apply overlay to AGENTS.md. Strips any existing overlay first (idempotent)."""
    path = Path(agents_md_path)
    content = ""
    if path.exists():
        content = path.read_text()

    content = strip_overlay_content(content)
    content = content.rstrip() + "\n\n" + overlay + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


async def strip_overlay(agents_md_path: str, cwd: Optional[str] = None) -> None:
    """Strip overlay from AGENTS.md, restoring it to clean state."""
    path = Path(agents_md_path)
    if not path.exists():
        return

    content = path.read_text()
    stripped = strip_overlay_content(content)

    if stripped != content:
        path.write_text(stripped)


def has_overlay(content: str) -> bool:
    """Check if AGENTS.md currently has an overlay applied."""
    return START_MARKER in content and END_MARKER in content
