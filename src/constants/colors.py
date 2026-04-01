"""ANSI color codes and theme palettes for pyclaude terminal output."""

from dataclasses import dataclass, field
from typing import Dict

# ANSI escape sequences
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
BLINK = "\033[5m"
REVERSE = "\033[7m"
HIDDEN = "\033[8m"
STRIKETHROUGH = "\033[9m"


class Colors:
    """Standard ANSI color codes for 16-color terminals."""

    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    @staticmethod
    def rgb(r: int, g: int, b: int) -> str:
        """Generate a 24-bit true color ANSI escape sequence."""
        return f"\033[38;2;{r};{g};{b}m"

    @staticmethod
    def bg_rgb(r: int, g: int, b: int) -> str:
        """Generate a 24-bit true color background ANSI escape sequence."""
        return f"\033[48;2;{r};{g};{b}m"

    @staticmethod
    def color256(n: int) -> str:
        """Generate a 256-color ANSI escape sequence."""
        return f"\033[38;5;{n}m"

    @staticmethod
    def bg_color256(n: int) -> str:
        """Generate a 256-color background ANSI escape sequence."""
        return f"\033[48;5;{n}m"


@dataclass
class Theme:
    """Color theme for pyclaude terminal output."""

    name: str
    primary: str
    secondary: str
    accent: str
    success: str
    warning: str
    error: str
    info: str
    muted: str
    text: str
    background: str = ""
    border: str = ""
    highlight: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    def colorize(self, text: str, color_attr: str) -> str:
        """Apply a theme color to text, with reset appended."""
        color = getattr(self, color_attr, self.text)
        return f"{color}{text}{RESET}"

    def bold(self, text: str, color_attr: str = "text") -> str:
        """Apply bold + theme color to text."""
        color = getattr(self, color_attr, self.text)
        return f"{BOLD}{color}{text}{RESET}"


DEFAULT_THEME = Theme(
    name="default",
    primary=Colors.BRIGHT_BLUE,
    secondary=Colors.CYAN,
    accent=Colors.MAGENTA,
    success=Colors.BRIGHT_GREEN,
    warning=Colors.BRIGHT_YELLOW,
    error=Colors.BRIGHT_RED,
    info=Colors.BRIGHT_CYAN,
    muted=Colors.BRIGHT_BLACK,
    text=Colors.WHITE,
    border=Colors.BRIGHT_BLACK,
    highlight=Colors.BRIGHT_WHITE,
)

DARK_THEME = Theme(
    name="dark",
    primary=Colors.rgb(100, 149, 237),
    secondary=Colors.rgb(0, 206, 209),
    accent=Colors.rgb(186, 85, 211),
    success=Colors.rgb(50, 205, 50),
    warning=Colors.rgb(255, 165, 0),
    error=Colors.rgb(255, 69, 0),
    info=Colors.rgb(135, 206, 250),
    muted=Colors.rgb(128, 128, 128),
    text=Colors.rgb(220, 220, 220),
    border=Colors.rgb(80, 80, 80),
    highlight=Colors.rgb(255, 255, 255),
)

LIGHT_THEME = Theme(
    name="light",
    primary=Colors.BLUE,
    secondary=Colors.CYAN,
    accent=Colors.MAGENTA,
    success=Colors.GREEN,
    warning=Colors.YELLOW,
    error=Colors.RED,
    info=Colors.CYAN,
    muted=Colors.BRIGHT_BLACK,
    text=Colors.BLACK,
    border=Colors.BRIGHT_BLACK,
    highlight=Colors.BLACK,
)

THEMES: Dict[str, Theme] = {
    "default": DEFAULT_THEME,
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
}


def get_theme(name: str = "default") -> Theme:
    """Get a theme by name, falling back to default."""
    return THEMES.get(name, DEFAULT_THEME)


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from text."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)
