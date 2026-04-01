"""Panel component for bordered content display."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BorderStyle(Enum):
    """Available border styles."""
    SINGLE = "single"
    DOUBLE = "double"
    ROUNDED = "rounded"
    HEAVY = "heavy"
    NONE = "none"


BORDER_CHARS: dict[BorderStyle, tuple[str, str, str, str, str, str]] = {
    # (horizontal, vertical, top-left, top-right, bottom-left, bottom-right)
    BorderStyle.SINGLE: ("─", "│", "┌", "┐", "└", "┘"),
    BorderStyle.DOUBLE: ("═", "║", "╔", "╗", "╚", "╝"),
    BorderStyle.ROUNDED: ("─", "│", "╭", "╮", "╰", "╯"),
    BorderStyle.HEAVY: ("━", "┃", "┏", "┓", "┗", "┛"),
    BorderStyle.NONE: (" ", " ", " ", " ", " ", " "),
}


@dataclass
class PanelConfig:
    """Configuration for panel rendering."""
    border: BorderStyle = BorderStyle.ROUNDED
    padding_x: int = 1
    padding_y: int = 0
    width: int = 0  # 0 = auto-fit
    title: str = ""
    title_align: str = "left"  # left, center, right
    subtitle: str = ""


class Panel:
    """Renders content inside a bordered panel."""

    def __init__(self, content: str = "", config: PanelConfig | None = None) -> None:
        self.content = content
        self.config = config or PanelConfig()

    def render(self) -> str:
        """Render the panel to a string."""
        cfg = self.config
        h, v, tl, tr, bl, br = BORDER_CHARS[cfg.border]
        pad_x = " " * cfg.padding_x

        lines = self.content.splitlines() if self.content else [""]
        max_content_width = max((len(line) for line in lines), default=0)
        inner_width = max(max_content_width + 2 * cfg.padding_x, cfg.width - 2) if cfg.width else max_content_width + 2 * cfg.padding_x

        # Top border with optional title
        top = self._make_top_border(h, tl, tr, inner_width, cfg.title, cfg.title_align)

        out: list[str] = [top]

        # Top padding
        for _ in range(cfg.padding_y):
            out.append(f"{v}{' ' * inner_width}{v}")

        # Content lines
        for line in lines:
            padded = f"{pad_x}{line}"
            padded = padded.ljust(inner_width)
            out.append(f"{v}{padded}{v}")

        # Bottom padding
        for _ in range(cfg.padding_y):
            out.append(f"{v}{' ' * inner_width}{v}")

        # Bottom border with optional subtitle
        if cfg.subtitle:
            bottom = self._make_top_border(h, bl, br, inner_width, cfg.subtitle, cfg.title_align)
        else:
            bottom = f"{bl}{h * inner_width}{br}"
        out.append(bottom)

        return "\n".join(out)

    def _make_top_border(
        self, h: str, left: str, right: str, width: int, title: str, align: str
    ) -> str:
        if not title:
            return f"{left}{h * width}{right}"

        label = f" {title} "
        if len(label) > width - 4:
            label = label[: width - 5] + "… "

        fill_total = width - len(label)
        if align == "center":
            left_fill = fill_total // 2
            right_fill = fill_total - left_fill
        elif align == "right":
            left_fill = fill_total - 2
            right_fill = 2
        else:  # left
            left_fill = 2
            right_fill = fill_total - 2

        left_fill = max(0, left_fill)
        right_fill = max(0, right_fill)
        return f"{left}{h * left_fill}{label}{h * right_fill}{right}"

    def __str__(self) -> str:
        return self.render()

    @classmethod
    def from_lines(cls, lines: list[str], **kwargs: object) -> Panel:
        """Create a panel from a list of lines."""
        return cls(content="\n".join(lines), config=PanelConfig(**kwargs))  # type: ignore[arg-type]

    @classmethod
    def info(cls, message: str, title: str = "Info") -> Panel:
        return cls(content=message, config=PanelConfig(title=title, border=BorderStyle.ROUNDED))

    @classmethod
    def error(cls, message: str, title: str = "Error") -> Panel:
        return cls(content=message, config=PanelConfig(title=title, border=BorderStyle.HEAVY))

    @classmethod
    def warning(cls, message: str, title: str = "Warning") -> Panel:
        return cls(content=message, config=PanelConfig(title=title, border=BorderStyle.DOUBLE))
