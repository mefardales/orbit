from __future__ import annotations
from .types import HudState
from .colors import COLOR_MAP, ANSI_RESET, ANSI_BOLD
from .constants import HUD_DEFAULT_WIDTH

def render_hud(state: HudState) -> str:
    if not state.visible or not state.entries:
        return ''
    lines = [f'{ANSI_BOLD}{"─" * HUD_DEFAULT_WIDTH}{ANSI_RESET}']
    for entry in state.entries:
        color = COLOR_MAP.get(entry.color, '')
        lines.append(f'  {entry.label}: {color}{entry.value}{ANSI_RESET}')
    lines.append(f'{ANSI_BOLD}{"─" * HUD_DEFAULT_WIDTH}{ANSI_RESET}')
    return '\n'.join(lines)
