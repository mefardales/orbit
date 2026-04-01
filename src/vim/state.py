"""VimState - manages vim emulation state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VimMode(Enum):
    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"
    VISUAL_LINE = "visual_line"
    COMMAND = "command"
    REPLACE = "replace"


@dataclass
class CursorPosition:
    """Cursor position in the buffer."""

    row: int = 0
    col: int = 0

    def clamp(self, max_row: int, max_col: int) -> CursorPosition:
        """Return a new position clamped to valid bounds."""
        return CursorPosition(
            row=max(0, min(self.row, max_row)),
            col=max(0, min(self.col, max_col)),
        )


class VimState:
    """Full state for vim mode emulation."""

    def __init__(self) -> None:
        self._mode: VimMode = VimMode.NORMAL
        self._cursor: CursorPosition = CursorPosition()
        self._registers: dict[str, str] = {}
        self._command_buffer: str = ""
        self._count_prefix: str = ""
        self._last_search: str = ""
        self._visual_start: Optional[CursorPosition] = None
        self._undo_stack: list[str] = []
        self._redo_stack: list[str] = []
        self._last_command: str = ""
        self._insert_start: Optional[CursorPosition] = None

    @property
    def mode(self) -> VimMode:
        return self._mode

    @property
    def cursor_pos(self) -> CursorPosition:
        return self._cursor

    @cursor_pos.setter
    def cursor_pos(self, pos: CursorPosition) -> None:
        self._cursor = pos

    @property
    def register(self) -> dict[str, str]:
        """Named registers (a-z, 0-9, and special)."""
        return self._registers

    @property
    def command_buffer(self) -> str:
        return self._command_buffer

    @property
    def count(self) -> int:
        """Parsed numeric prefix, default 1."""
        return int(self._count_prefix) if self._count_prefix else 1

    def enter_mode(self, mode: VimMode) -> None:
        """Transition to a new mode."""
        if mode == VimMode.INSERT:
            self._insert_start = CursorPosition(self._cursor.row, self._cursor.col)
        elif mode == VimMode.VISUAL:
            self._visual_start = CursorPosition(self._cursor.row, self._cursor.col)
        elif mode == VimMode.NORMAL:
            self._visual_start = None
            self._insert_start = None
            self._command_buffer = ""
            self._count_prefix = ""
        elif mode == VimMode.COMMAND:
            self._command_buffer = ":"
        self._mode = mode

    def feed_key(self, key: str) -> Optional[str]:
        """Feed a key into the state machine.

        Returns:
            An action string if a complete command is recognized, else None.
        """
        # Handle escape from any mode
        if key == "escape" or key == "\x1b":
            self.enter_mode(VimMode.NORMAL)
            return "mode_normal"

        if self._mode == VimMode.COMMAND:
            return self._handle_command_mode(key)

        if self._mode == VimMode.INSERT:
            return self._handle_insert_mode(key)

        # Normal / Visual mode
        return self._handle_normal_mode(key)

    def _handle_command_mode(self, key: str) -> Optional[str]:
        """Process keys in command mode."""
        if key == "\n" or key == "enter":
            cmd = self._command_buffer[1:]  # strip leading ':'
            self.enter_mode(VimMode.NORMAL)
            self._last_command = cmd
            return f"ex_command:{cmd}"
        elif key == "backspace" or key == "\x7f":
            if len(self._command_buffer) > 1:
                self._command_buffer = self._command_buffer[:-1]
            else:
                self.enter_mode(VimMode.NORMAL)
            return None
        else:
            self._command_buffer += key
            return None

    def _handle_insert_mode(self, key: str) -> Optional[str]:
        """Process keys in insert mode."""
        if key == "\x1b":
            self.enter_mode(VimMode.NORMAL)
            return "mode_normal"
        return f"insert_char:{key}"

    def _handle_normal_mode(self, key: str) -> Optional[str]:
        """Process keys in normal mode."""
        # Numeric prefix accumulation
        if key.isdigit() and (self._count_prefix or key != "0"):
            self._count_prefix += key
            return None

        action = None
        count = self.count
        self._count_prefix = ""

        # Mode transitions
        if key == "i":
            self.enter_mode(VimMode.INSERT)
            action = "mode_insert"
        elif key == "a":
            self._cursor.col += 1
            self.enter_mode(VimMode.INSERT)
            action = "mode_insert_after"
        elif key == "v":
            self.enter_mode(VimMode.VISUAL)
            action = "mode_visual"
        elif key == "V":
            self.enter_mode(VimMode.VISUAL_LINE)
            action = "mode_visual_line"
        elif key == ":":
            self.enter_mode(VimMode.COMMAND)
            action = "mode_command"
        # Motions
        elif key == "h":
            self._cursor.col = max(0, self._cursor.col - count)
            action = "move_left"
        elif key == "l":
            self._cursor.col += count
            action = "move_right"
        elif key == "j":
            self._cursor.row += count
            action = "move_down"
        elif key == "k":
            self._cursor.row = max(0, self._cursor.row - count)
            action = "move_up"
        elif key == "0":
            self._cursor.col = 0
            action = "move_bol"
        elif key == "$":
            self._cursor.col = 999999  # will be clamped
            action = "move_eol"
        elif key == "w":
            action = f"move_word_forward:{count}"
        elif key == "b":
            action = f"move_word_backward:{count}"
        elif key == "G":
            action = f"move_end" if count == 1 else f"goto_line:{count}"
        # Operations
        elif key == "d":
            self._command_buffer = "d"
            action = "pending_delete"
        elif key == "y":
            self._command_buffer = "y"
            action = "pending_yank"
        elif key == "p":
            action = "paste_after"
        elif key == "P":
            action = "paste_before"
        elif key == "u":
            action = "undo"
        elif key == "x":
            action = "delete_char"
        elif key == "/":
            self.enter_mode(VimMode.COMMAND)
            self._command_buffer = "/"
            action = "search_forward"
        elif key == "n":
            action = "search_next"
        elif key == ".":
            action = f"repeat:{self._last_command}"

        if action and not action.startswith("pending"):
            self._last_command = key

        return action

    def yank(self, text: str, register: str = '"') -> None:
        """Store text in a register."""
        self._registers[register] = text
        self._registers['"'] = text  # unnamed register always gets it

    def get_register(self, name: str = '"') -> str:
        """Retrieve text from a register."""
        return self._registers.get(name, "")

    def push_undo(self, state: str) -> None:
        """Save a buffer state for undo."""
        self._undo_stack.append(state)
        self._redo_stack.clear()

    def undo(self) -> Optional[str]:
        """Pop and return previous state, or None."""
        if self._undo_stack:
            current = self._undo_stack.pop()
            self._redo_stack.append(current)
            return self._undo_stack[-1] if self._undo_stack else None
        return None

    def redo(self) -> Optional[str]:
        """Redo last undone state, or None."""
        if self._redo_stack:
            state = self._redo_stack.pop()
            self._undo_stack.append(state)
            return state
        return None

    @property
    def mode_display(self) -> str:
        """String suitable for status line display."""
        labels = {
            VimMode.NORMAL: "-- NORMAL --",
            VimMode.INSERT: "-- INSERT --",
            VimMode.VISUAL: "-- VISUAL --",
            VimMode.VISUAL_LINE: "-- VISUAL LINE --",
            VimMode.COMMAND: self._command_buffer,
            VimMode.REPLACE: "-- REPLACE --",
        }
        return labels.get(self._mode, "")
