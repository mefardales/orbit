"""Colour themes for terminal output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Theme:
    """A complete colour theme for terminal output."""

    name: str
    # Foreground palette (ANSI codes)
    fg_default: str = "\033[37m"
    fg_error: str = "\033[31m"
    fg_warning: str = "\033[33m"
    fg_info: str = "\033[34m"
    fg_success: str = "\033[32m"
    fg_muted: str = "\033[2m"
    fg_accent: str = "\033[36m"
    # Background palette
    bg_default: str = ""
    bg_highlight: str = "\033[48;5;236m"
    bg_error: str = "\033[41m"
    # Decorations
    bold: str = "\033[1m"
    dim: str = "\033[2m"
    underline: str = "\033[4m"
    reset: str = "\033[0m"
    # Semantic
    border_char: str = "│"
    header_char: str = "─"
    bullet_char: str = "•"
    # Feature flags
    use_icons: bool = True
    use_bold_headers: bool = True

    def wrap(self, code: str, text: str) -> str:
        """Wrap text in the given ANSI code and reset."""
        return f"{code}{text}{self.reset}"

    def error(self, text: str) -> str:
        return self.wrap(self.fg_error + self.bold, text)

    def warning(self, text: str) -> str:
        return self.wrap(self.fg_warning, text)

    def info(self, text: str) -> str:
        return self.wrap(self.fg_info, text)

    def success(self, text: str) -> str:
        return self.wrap(self.fg_success, text)

    def muted(self, text: str) -> str:
        return self.wrap(self.fg_muted, text)

    def accent(self, text: str) -> str:
        return self.wrap(self.fg_accent, text)

    def header(self, text: str) -> str:
        if self.use_bold_headers:
            return self.wrap(self.bold, text)
        return text


# ---------------------------------------------------------------------------
# Built-in themes
# ---------------------------------------------------------------------------

DARK_THEME = Theme(
    name="dark",
    fg_default="\033[38;5;252m",
    fg_error="\033[38;5;203m",
    fg_warning="\033[38;5;214m",
    fg_info="\033[38;5;75m",
    fg_success="\033[38;5;114m",
    fg_muted="\033[38;5;242m",
    fg_accent="\033[38;5;141m",
    bg_highlight="\033[48;5;236m",
    use_icons=True,
    use_bold_headers=True,
)

LIGHT_THEME = Theme(
    name="light",
    fg_default="\033[38;5;235m",
    fg_error="\033[38;5;160m",
    fg_warning="\033[38;5;130m",
    fg_info="\033[38;5;25m",
    fg_success="\033[38;5;28m",
    fg_muted="\033[38;5;245m",
    fg_accent="\033[38;5;90m",
    bg_highlight="\033[48;5;254m",
    use_icons=True,
    use_bold_headers=True,
)

MINIMAL_THEME = Theme(
    name="minimal",
    fg_default="",
    fg_error="",
    fg_warning="",
    fg_info="",
    fg_success="",
    fg_muted="",
    fg_accent="",
    bg_highlight="",
    bg_error="",
    bold="",
    dim="",
    underline="",
    reset="",
    border_char="|",
    header_char="-",
    bullet_char="-",
    use_icons=False,
    use_bold_headers=False,
)

_THEMES: dict[str, Theme] = {
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
    "minimal": MINIMAL_THEME,
}

_current_theme: Theme = DARK_THEME


def apply_theme(theme: Theme | str) -> Theme:
    """Set the active global theme and return it.

    Accepts a ``Theme`` instance or a name (``"dark"``, ``"light"``,
    ``"minimal"``).
    """
    global _current_theme
    if isinstance(theme, str):
        resolved = _THEMES.get(theme.lower())
        if resolved is None:
            raise ValueError(
                f"Unknown theme {theme!r}. Choose from: {', '.join(_THEMES)}"
            )
        _current_theme = resolved
    else:
        _current_theme = theme
    return _current_theme


def get_current_theme() -> Theme:
    """Return the currently active theme."""
    return _current_theme
