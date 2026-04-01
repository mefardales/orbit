"""Output formatting utilities for code, errors, warnings, diffs, and info."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Optional, Sequence


# ANSI escape codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"
_BG_RED = "\033[41m"
_BG_GREEN = "\033[42m"


@dataclass
class FormatOptions:
    """Controls how output is rendered."""

    use_color: bool = True
    line_numbers: bool = True
    max_width: int = 120
    indent: int = 2
    context_lines: int = 3


class OutputFormatter:
    """Formats various output types with optional ANSI colouring."""

    def __init__(self, options: Optional[FormatOptions] = None) -> None:
        self.options = options or FormatOptions()

    # -- helpers ---------------------------------------------------------------

    def _c(self, code: str, text: str) -> str:
        """Wrap *text* in an ANSI colour code if colour is enabled."""
        if not self.options.use_color:
            return text
        return f"{code}{text}{_RESET}"

    def _gutter(self, number: int, width: int = 4) -> str:
        if not self.options.line_numbers:
            return ""
        return self._c(_DIM, f"{number:>{width}} | ")

    # -- public API ------------------------------------------------------------

    def format_code(
        self,
        code: str,
        *,
        language: str = "",
        start_line: int = 1,
        highlight_lines: Optional[set[int]] = None,
    ) -> str:
        """Return *code* with optional line numbers and highlighted lines."""
        highlight_lines = highlight_lines or set()
        lines = code.splitlines()
        width = len(str(start_line + len(lines)))
        parts: list[str] = []

        if language:
            parts.append(self._c(_DIM, f"── {language} ──"))

        for idx, line in enumerate(lines, start=start_line):
            gutter = self._gutter(idx, width)
            if idx in highlight_lines:
                line_text = self._c(_YELLOW + _BOLD, line)
            else:
                line_text = line
            parts.append(f"{gutter}{line_text}")

        return "\n".join(parts)

    def format_error(
        self,
        message: str,
        *,
        title: str = "Error",
        hint: str = "",
        source: str = "",
        line: Optional[int] = None,
        column: Optional[int] = None,
    ) -> str:
        """Return a formatted error block."""
        header = self._c(_RED + _BOLD, f"✖ {title}")
        location = ""
        if source:
            loc_parts = [source]
            if line is not None:
                loc_parts.append(str(line))
                if column is not None:
                    loc_parts.append(str(column))
            location = "\n  " + self._c(_DIM, ":".join(loc_parts))

        body = textwrap.indent(message.strip(), "  ")
        parts = [header, location, "", body] if location else [header, "", body]

        if hint:
            parts.append("")
            parts.append(self._c(_CYAN, f"  💡 {hint}"))

        return "\n".join(parts)

    def format_warning(self, message: str, *, title: str = "Warning") -> str:
        """Return a formatted warning block."""
        header = self._c(_YELLOW + _BOLD, f"⚠ {title}")
        body = textwrap.indent(message.strip(), "  ")
        return f"{header}\n\n{body}"

    def format_info(self, message: str, *, title: str = "Info") -> str:
        """Return a formatted informational block."""
        header = self._c(_BLUE + _BOLD, f"ℹ {title}")
        body = textwrap.indent(message.strip(), "  ")
        return f"{header}\n\n{body}"

    def format_diff(
        self,
        old_text: str,
        new_text: str,
        *,
        filename: str = "",
        context_lines: Optional[int] = None,
    ) -> str:
        """Return a unified-diff-style formatted comparison of two texts."""
        import difflib

        ctx = context_lines if context_lines is not None else self.options.context_lines
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}" if filename else "a",
            tofile=f"b/{filename}" if filename else "b",
            n=ctx,
        )

        parts: list[str] = []
        for line in diff:
            line_stripped = line.rstrip("\n")
            if line.startswith("+++") or line.startswith("---"):
                parts.append(self._c(_BOLD, line_stripped))
            elif line.startswith("@@"):
                parts.append(self._c(_CYAN, line_stripped))
            elif line.startswith("+"):
                parts.append(self._c(_GREEN, line_stripped))
            elif line.startswith("-"):
                parts.append(self._c(_RED, line_stripped))
            else:
                parts.append(line_stripped)

        if not parts:
            return self._c(_DIM, "(no differences)")
        return "\n".join(parts)
