"""Vim motion parsing and execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from vim.state import CursorPosition


class MotionType(Enum):
    CHAR = "char"        # h, l, f, t
    LINE = "line"        # j, k, G
    WORD = "word"        # w, b, e, W, B, E
    SEARCH = "search"    # /, ?, n, N
    PARAGRAPH = "para"   # {, }
    SENTENCE = "sent"    # (, )
    SCREEN = "screen"    # H, M, L


@dataclass
class Motion:
    """A parsed vim motion."""

    motion_type: MotionType
    direction: int = 1       # 1 = forward, -1 = backward
    count: int = 1
    char: str = ""           # for f/t motions
    inclusive: bool = False   # whether the endpoint is included


# Regex for parsing a motion string (simplified)
_MOTION_RE = re.compile(
    r'^(?P<count>\d+)?(?P<motion>[hjklwbWeB$0GHMLftFT{}()/\?nN])(?P<char>.)?$'
)


def parse_motion(input_str: str) -> Optional[Motion]:
    """Parse a vim motion string into a Motion object.

    Args:
        input_str: Raw motion string like "3w", "f(", "$", "2j".

    Returns:
        Parsed Motion or None if invalid.
    """
    m = _MOTION_RE.match(input_str)
    if not m:
        return None

    count = int(m.group("count")) if m.group("count") else 1
    key = m.group("motion")
    char = m.group("char") or ""

    motion_map: dict[str, tuple[MotionType, int, bool]] = {
        "h": (MotionType.CHAR, -1, False),
        "l": (MotionType.CHAR, 1, False),
        "j": (MotionType.LINE, 1, True),
        "k": (MotionType.LINE, -1, True),
        "w": (MotionType.WORD, 1, False),
        "W": (MotionType.WORD, 1, False),
        "b": (MotionType.WORD, -1, False),
        "B": (MotionType.WORD, -1, False),
        "e": (MotionType.WORD, 1, True),
        "E": (MotionType.WORD, 1, True),
        "$": (MotionType.CHAR, 1, True),
        "0": (MotionType.CHAR, -1, False),
        "G": (MotionType.LINE, 1, True),
        "H": (MotionType.SCREEN, -1, False),
        "M": (MotionType.SCREEN, 0, False),
        "L": (MotionType.SCREEN, 1, False),
        "f": (MotionType.CHAR, 1, True),
        "F": (MotionType.CHAR, -1, True),
        "t": (MotionType.CHAR, 1, False),
        "T": (MotionType.CHAR, -1, False),
        "{": (MotionType.PARAGRAPH, -1, False),
        "}": (MotionType.PARAGRAPH, 1, False),
        "(": (MotionType.SENTENCE, -1, False),
        ")": (MotionType.SENTENCE, 1, False),
        "/": (MotionType.SEARCH, 1, False),
        "?": (MotionType.SEARCH, -1, False),
        "n": (MotionType.SEARCH, 1, False),
        "N": (MotionType.SEARCH, -1, False),
    }

    if key not in motion_map:
        return None

    mtype, direction, inclusive = motion_map[key]
    return Motion(
        motion_type=mtype,
        direction=direction,
        count=count,
        char=char,
        inclusive=inclusive,
    )


def _find_word_boundary(line: str, col: int, direction: int) -> int:
    """Find the next word boundary in a line."""
    if direction > 0:
        # Forward: skip to next word start
        rest = line[col:]
        m = re.search(r'\b\w', rest[1:]) if len(rest) > 1 else None
        if m:
            return col + 1 + m.start()
        return len(line)
    else:
        # Backward: find previous word start
        before = line[:col]
        matches = list(re.finditer(r'\b\w', before))
        if matches:
            return matches[-1].start()
        return 0


def _find_char_in_line(line: str, col: int, char: str, direction: int, inclusive: bool) -> int:
    """Find a character in the line for f/t/F/T motions."""
    if direction > 0:
        idx = line.find(char, col + 1)
        if idx == -1:
            return col
        return idx if inclusive else idx - 1
    else:
        idx = line.rfind(char, 0, col)
        if idx == -1:
            return col
        return idx if inclusive else idx + 1


def execute_motion(
    motion: Motion,
    lines: list[str],
    cursor: CursorPosition,
) -> CursorPosition:
    """Execute a motion on a buffer, returning the new cursor position.

    Args:
        motion: The parsed motion to execute.
        lines: The buffer contents as a list of lines.
        cursor: Current cursor position.

    Returns:
        New cursor position after the motion.
    """
    if not lines:
        return CursorPosition(0, 0)

    row, col = cursor.row, cursor.col
    max_row = len(lines) - 1

    for _ in range(motion.count):
        if motion.motion_type == MotionType.CHAR:
            if motion.char:
                # f/t/F/T motion
                current_line = lines[min(row, max_row)]
                col = _find_char_in_line(current_line, col, motion.char, motion.direction, motion.inclusive)
            elif motion.direction > 0 and not motion.inclusive:
                # 'l' motion
                current_line = lines[min(row, max_row)]
                col = min(col + 1, max(0, len(current_line) - 1))
            elif motion.direction < 0 and not motion.inclusive:
                if col == 0 and motion.char == "":
                    col = 0  # '0' motion: start of line
                else:
                    col = max(0, col - 1)  # 'h' motion
            elif motion.inclusive:
                # '$' motion
                current_line = lines[min(row, max_row)]
                col = max(0, len(current_line) - 1)

        elif motion.motion_type == MotionType.LINE:
            row = max(0, min(max_row, row + motion.direction))
            current_line = lines[row]
            col = min(col, max(0, len(current_line) - 1))

        elif motion.motion_type == MotionType.WORD:
            current_line = lines[min(row, max_row)]
            new_col = _find_word_boundary(current_line, col, motion.direction)
            if new_col == col and motion.direction > 0 and row < max_row:
                row += 1
                col = 0
                # skip leading whitespace
                next_line = lines[row]
                m = re.match(r'\s*', next_line)
                if m:
                    col = m.end()
            elif new_col == col and motion.direction < 0 and row > 0:
                row -= 1
                col = max(0, len(lines[row]) - 1)
            else:
                col = new_col

        elif motion.motion_type == MotionType.PARAGRAPH:
            # Move to next/prev blank line
            step = motion.direction
            row += step
            while 0 <= row <= max_row:
                if not lines[row].strip():
                    break
                row += step
            row = max(0, min(max_row, row))
            col = 0

    return CursorPosition(row=max(0, min(row, max_row)), col=max(0, col))
