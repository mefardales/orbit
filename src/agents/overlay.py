"""AGENTS.md runtime overlay injection.

Injects session context into AGENTS.md using HTML markers, with a strict
character cap and deterministic overflow handling — matching OMX behavior.
"""
from __future__ import annotations

import time
from pathlib import Path

_MARKER_START = '<!-- ORBIT:RUNTIME:START -->'
_MARKER_END = '<!-- ORBIT:RUNTIME:END -->'
_MAX_OVERLAY_CHARS = 3500


def build_overlay_block(
    session_id: str | None = None,
    mode: str | None = None,
    active_agents: list[str] | None = None,
    reasoning_effort: str = 'medium',
    autonomy: str = 'standard',
    model_tier: str = 'default',
    extra_context: str = '',
) -> str:
    """Build the runtime overlay block that gets injected into AGENTS.md."""
    lines: list[str] = []
    lines.append(f'_Runtime overlay generated at {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}_')
    lines.append('')

    if session_id:
        lines.append(f'**Session:** `{session_id}`')
    if mode:
        lines.append(f'**Mode:** {mode}')
    lines.append(f'**Autonomy:** {autonomy}')
    lines.append(f'**Reasoning effort:** {reasoning_effort}')
    lines.append(f'**Model tier:** {model_tier}')

    if active_agents:
        lines.append('')
        lines.append('**Active agents:**')
        for agent in active_agents:
            lines.append(f'- `{agent}`')

    if extra_context:
        lines.append('')
        lines.append(extra_context)

    content = '\n'.join(lines)

    # Enforce character cap with deterministic truncation
    if len(content) > _MAX_OVERLAY_CHARS:
        content = content[:_MAX_OVERLAY_CHARS - 20] + '\n\n_(truncated)_'

    return f'{_MARKER_START}\n{content}\n{_MARKER_END}'


def inject_overlay(agents_md_path: Path, overlay_block: str) -> str:
    """Inject or replace the runtime overlay in AGENTS.md content.

    Returns the updated content string.
    """
    if not agents_md_path.exists():
        return overlay_block + '\n'

    content = agents_md_path.read_text(encoding='utf-8')

    # Replace existing overlay
    start_idx = content.find(_MARKER_START)
    end_idx = content.find(_MARKER_END)

    if start_idx != -1 and end_idx != -1:
        end_idx += len(_MARKER_END)
        return content[:start_idx] + overlay_block + content[end_idx:]

    # Append at the end
    if not content.endswith('\n'):
        content += '\n'
    return content + '\n' + overlay_block + '\n'


def strip_overlay(content: str) -> str:
    """Remove the runtime overlay from AGENTS.md content."""
    start_idx = content.find(_MARKER_START)
    end_idx = content.find(_MARKER_END)

    if start_idx == -1 or end_idx == -1:
        return content

    end_idx += len(_MARKER_END)
    # Also strip surrounding blank lines
    before = content[:start_idx].rstrip('\n')
    after = content[end_idx:].lstrip('\n')
    if before and after:
        return before + '\n\n' + after
    return before + after


def update_agents_overlay(
    cwd: Path | None = None,
    session_id: str | None = None,
    mode: str | None = None,
    active_agents: list[str] | None = None,
) -> Path:
    """Update the AGENTS.md file in the given directory with runtime context."""
    from ..config.runtime_context import RuntimeContext

    ctx = RuntimeContext.get()
    target = (cwd or Path.cwd()) / 'AGENTS.md'

    block = build_overlay_block(
        session_id=session_id,
        mode=mode,
        active_agents=active_agents,
        reasoning_effort=ctx.reasoning_effort,
        autonomy=ctx.autonomy,
        model_tier=ctx.model_tier,
    )

    updated = inject_overlay(target, block)
    target.write_text(updated, encoding='utf-8')
    return target
