"""Table renderer component for terminal output."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Alignment(Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass
class Column:
    """Column definition for a table."""
    header: str
    alignment: Alignment = Alignment.LEFT
    min_width: int = 0
    max_width: int = 0  # 0 = no limit

    def format_cell(self, value: str, width: int) -> str:
        if self.max_width and len(value) > self.max_width:
            value = value[: self.max_width - 1] + "…"
        if self.alignment == Alignment.LEFT:
            return value.ljust(width)
        elif self.alignment == Alignment.RIGHT:
            return value.rjust(width)
        else:
            return value.center(width)


@dataclass
class TableStyle:
    """Visual style for table rendering."""
    horizontal: str = "─"
    vertical: str = "│"
    corner_tl: str = "┌"
    corner_tr: str = "┐"
    corner_bl: str = "└"
    corner_br: str = "┘"
    tee_left: str = "├"
    tee_right: str = "┤"
    tee_top: str = "┬"
    tee_bottom: str = "┴"
    cross: str = "┼"
    padding: int = 1
    show_header_separator: bool = True
    show_border: bool = True


class TableRenderer:
    """Renders tabular data as formatted text strings."""

    def __init__(
        self,
        columns: list[Column | str] | None = None,
        style: TableStyle | None = None,
    ) -> None:
        self.columns: list[Column] = []
        if columns:
            for c in columns:
                if isinstance(c, str):
                    self.columns.append(Column(header=c))
                else:
                    self.columns.append(c)
        self.style = style or TableStyle()
        self._rows: list[list[str]] = []

    def add_column(self, header: str, alignment: Alignment = Alignment.LEFT, **kwargs: Any) -> None:
        self.columns.append(Column(header=header, alignment=alignment, **kwargs))

    def add_row(self, *values: Any) -> None:
        """Add a row of values. Values are converted to strings."""
        self._rows.append([str(v) for v in values])

    def add_rows(self, rows: list[list[Any]]) -> None:
        for row in rows:
            self.add_row(*row)

    def clear(self) -> None:
        self._rows.clear()

    def _compute_widths(self) -> list[int]:
        widths = [max(len(c.header), c.min_width) for c in self.columns]
        for row in self._rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(cell))
        return widths

    def render(self) -> str:
        """Render the table to a string."""
        if not self.columns:
            return ""
        widths = self._compute_widths()
        s = self.style
        pad = " " * s.padding
        lines: list[str] = []

        def make_separator(left: str, mid: str, right: str) -> str:
            parts = [s.horizontal * (w + 2 * s.padding) for w in widths]
            return left + mid.join(parts) + right

        def make_row(cells: list[str]) -> str:
            formatted = []
            for i, cell in enumerate(cells):
                if i < len(self.columns):
                    formatted.append(pad + self.columns[i].format_cell(cell, widths[i]) + pad)
                else:
                    formatted.append(pad + cell.ljust(widths[i] if i < len(widths) else 0) + pad)
            return s.vertical + s.vertical.join(formatted) + s.vertical

        if s.show_border:
            lines.append(make_separator(s.corner_tl, s.tee_top, s.corner_tr))

        # Header
        headers = [c.header for c in self.columns]
        lines.append(make_row(headers))

        if s.show_header_separator:
            lines.append(make_separator(s.tee_left, s.cross, s.tee_right))

        # Data rows
        for row in self._rows:
            # Pad row to column count
            padded = row + [""] * (len(self.columns) - len(row))
            lines.append(make_row(padded))

        if s.show_border:
            lines.append(make_separator(s.corner_bl, s.tee_bottom, s.corner_br))

        return "\n".join(lines)

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def __str__(self) -> str:
        return self.render()
