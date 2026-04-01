"""Vim keymap definitions for normal, insert, and visual modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from vim.state import VimMode


@dataclass(frozen=True)
class KeyAction:
    """An action bound to a key in vim mode."""

    key: str
    action: str
    description: str = ""
    repeatable: bool = True


# Default keymaps per mode
_NORMAL_MAP: list[KeyAction] = [
    KeyAction("h", "move_left", "Move cursor left"),
    KeyAction("j", "move_down", "Move cursor down"),
    KeyAction("k", "move_up", "Move cursor up"),
    KeyAction("l", "move_right", "Move cursor right"),
    KeyAction("w", "word_forward", "Move to next word"),
    KeyAction("b", "word_backward", "Move to previous word"),
    KeyAction("e", "word_end", "Move to end of word"),
    KeyAction("0", "line_start", "Move to start of line"),
    KeyAction("$", "line_end", "Move to end of line"),
    KeyAction("^", "first_non_blank", "Move to first non-blank"),
    KeyAction("G", "goto_end", "Go to end of file"),
    KeyAction("gg", "goto_start", "Go to start of file"),
    KeyAction("i", "enter_insert", "Enter insert mode"),
    KeyAction("a", "enter_insert_after", "Enter insert mode after cursor"),
    KeyAction("A", "enter_insert_eol", "Enter insert mode at end of line"),
    KeyAction("I", "enter_insert_bol", "Enter insert mode at start of line"),
    KeyAction("o", "open_below", "Open line below and enter insert"),
    KeyAction("O", "open_above", "Open line above and enter insert"),
    KeyAction("v", "enter_visual", "Enter visual mode"),
    KeyAction("V", "enter_visual_line", "Enter visual line mode"),
    KeyAction("x", "delete_char", "Delete character under cursor"),
    KeyAction("X", "delete_char_before", "Delete character before cursor"),
    KeyAction("dd", "delete_line", "Delete current line"),
    KeyAction("yy", "yank_line", "Yank current line"),
    KeyAction("p", "paste_after", "Paste after cursor"),
    KeyAction("P", "paste_before", "Paste before cursor"),
    KeyAction("u", "undo", "Undo"),
    KeyAction("ctrl+r", "redo", "Redo"),
    KeyAction("/", "search_forward", "Search forward"),
    KeyAction("?", "search_backward", "Search backward"),
    KeyAction("n", "search_next", "Next search result"),
    KeyAction("N", "search_prev", "Previous search result"),
    KeyAction(".", "repeat_last", "Repeat last command"),
    KeyAction(":", "enter_command", "Enter command mode"),
    KeyAction("ZZ", "save_quit", "Save and quit"),
    KeyAction("ZQ", "force_quit", "Quit without saving"),
]

_INSERT_MAP: list[KeyAction] = [
    KeyAction("escape", "exit_insert", "Return to normal mode"),
    KeyAction("ctrl+[", "exit_insert", "Return to normal mode"),
    KeyAction("ctrl+c", "exit_insert", "Return to normal mode"),
    KeyAction("ctrl+w", "delete_word_back", "Delete word backward"),
    KeyAction("ctrl+u", "delete_to_bol", "Delete to start of line"),
    KeyAction("ctrl+h", "backspace", "Delete character before cursor"),
    KeyAction("ctrl+t", "indent", "Indent current line"),
    KeyAction("ctrl+d", "dedent", "Dedent current line"),
    KeyAction("ctrl+n", "autocomplete_next", "Next autocomplete suggestion"),
    KeyAction("ctrl+p", "autocomplete_prev", "Previous autocomplete suggestion"),
]

_VISUAL_MAP: list[KeyAction] = [
    KeyAction("escape", "exit_visual", "Return to normal mode"),
    KeyAction("h", "extend_left", "Extend selection left"),
    KeyAction("j", "extend_down", "Extend selection down"),
    KeyAction("k", "extend_up", "Extend selection up"),
    KeyAction("l", "extend_right", "Extend selection right"),
    KeyAction("w", "extend_word", "Extend selection by word"),
    KeyAction("b", "extend_word_back", "Extend selection by word backward"),
    KeyAction("$", "extend_eol", "Extend selection to end of line"),
    KeyAction("0", "extend_bol", "Extend selection to start of line"),
    KeyAction("d", "delete_selection", "Delete selection"),
    KeyAction("y", "yank_selection", "Yank selection"),
    KeyAction("c", "change_selection", "Change selection"),
    KeyAction(">", "indent_selection", "Indent selection"),
    KeyAction("<", "dedent_selection", "Dedent selection"),
    KeyAction("o", "swap_anchor", "Swap selection anchor"),
    KeyAction("gv", "reselect", "Reselect previous visual area"),
]


class VimKeymap:
    """Manages vim keybindings for all modes with customization support."""

    def __init__(self) -> None:
        self._maps: dict[VimMode, dict[str, KeyAction]] = {
            VimMode.NORMAL: {},
            VimMode.INSERT: {},
            VimMode.VISUAL: {},
            VimMode.VISUAL_LINE: {},
            VimMode.COMMAND: {},
            VimMode.REPLACE: {},
        }
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default keymaps."""
        for ka in _NORMAL_MAP:
            self._maps[VimMode.NORMAL][ka.key] = ka
        for ka in _INSERT_MAP:
            self._maps[VimMode.INSERT][ka.key] = ka
        for ka in _VISUAL_MAP:
            self._maps[VimMode.VISUAL][ka.key] = ka
            self._maps[VimMode.VISUAL_LINE][ka.key] = ka

    @property
    def normal_mode(self) -> dict[str, KeyAction]:
        return dict(self._maps[VimMode.NORMAL])

    @property
    def insert_mode(self) -> dict[str, KeyAction]:
        return dict(self._maps[VimMode.INSERT])

    @property
    def visual_mode(self) -> dict[str, KeyAction]:
        return dict(self._maps[VimMode.VISUAL])

    def map_key(self, mode: VimMode, key: str, action: str, description: str = "") -> None:
        """Add or override a key mapping in a mode."""
        self._maps[mode][key] = KeyAction(key=key, action=action, description=description)

    def unmap_key(self, mode: VimMode, key: str) -> bool:
        """Remove a key mapping. Returns True if removed."""
        return self._maps[mode].pop(key, None) is not None

    def resolve(self, mode: VimMode, key: str) -> Optional[KeyAction]:
        """Resolve a key to its action in the given mode."""
        return self._maps.get(mode, {}).get(key)

    def list_bindings(self, mode: VimMode) -> list[KeyAction]:
        """List all bindings for a mode, sorted by key."""
        return sorted(self._maps.get(mode, {}).values(), key=lambda ka: ka.key)

    def get_action(self, mode: VimMode, key: str) -> Optional[str]:
        """Get just the action string for a key in a mode."""
        ka = self.resolve(mode, key)
        return ka.action if ka else None
