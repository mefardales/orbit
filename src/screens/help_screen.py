"""Help screen with command list and examples."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Optional

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"


@dataclass
class CommandHelp:
    """A single help entry for a command."""

    name: str
    shortcut: str
    description: str
    examples: list[str] = field(default_factory=list)
    category: str = "General"


DEFAULT_COMMANDS: list[CommandHelp] = [
    CommandHelp("help", "?", "Show this help screen", ["help", "help <command>"], "General"),
    CommandHelp("quit", "q", "Exit pyclaude", ["quit", "Ctrl+C"], "General"),
    CommandHelp("ask", "a", "Ask the AI a question", ["ask How do I sort a list?"], "AI"),
    CommandHelp("run", "r", "Run a shell command", ["run ls -la", "run python test.py"], "Execution"),
    CommandHelp("edit", "e", "Open file in editor", ["edit main.py", "edit src/lib.py:42"], "Files"),
    CommandHelp("search", "s", "Search codebase", ["search def my_func", "search TODO"], "Files"),
    CommandHelp("diff", "d", "Show git diff", ["diff", "diff HEAD~1"], "Git"),
    CommandHelp("commit", "c", "Create a git commit", ["commit Fix typo in docs"], "Git"),
    CommandHelp("agent", "ag", "Manage agents", ["agent list", "agent start coder"], "Agents"),
    CommandHelp("task", "t", "Manage tasks", ["task add Write tests", "task list"], "Tasks"),
    CommandHelp("config", "cfg", "View/edit config", ["config set theme dark"], "Settings"),
    CommandHelp("buddy", "b", "AI pair programming", ["buddy suggest", "buddy explain"], "AI"),
    CommandHelp("voice", "v", "Voice input mode", ["voice start", "voice stop"], "Input"),
    CommandHelp("vim", ":", "Toggle vim mode", ["vim on", "vim off"], "Input"),
    CommandHelp("dashboard", "dash", "Show dashboard", ["dashboard"], "Views"),
    CommandHelp("clear", "cl", "Clear the screen", ["clear"], "General"),
]


def _group_commands(commands: list[CommandHelp]) -> dict[str, list[CommandHelp]]:
    """Group commands by category."""
    groups: dict[str, list[CommandHelp]] = {}
    for cmd in commands:
        groups.setdefault(cmd.category, []).append(cmd)
    return groups


def _render_command_table(commands: list[CommandHelp], width: int) -> str:
    """Render a table of commands."""
    lines: list[str] = []
    name_w = max((len(c.name) for c in commands), default=10) + 2
    short_w = 6
    for cmd in commands:
        name_col = f"{GREEN}{cmd.name:<{name_w}}{RESET}"
        short_col = f"{DIM}({cmd.shortcut}){RESET:<{short_w}}"
        desc_w = width - name_w - short_w - 8
        desc = cmd.description[:desc_w]
        lines.append(f"  {name_col} {short_col} {desc}")
    return "\n".join(lines)


def _render_examples(cmd: CommandHelp) -> str:
    """Render examples for a single command."""
    if not cmd.examples:
        return f"  {DIM}No examples available{RESET}"
    lines = [f"  {DIM}${RESET} {CYAN}{ex}{RESET}" for ex in cmd.examples]
    return "\n".join(lines)


def render_help(
    commands: Optional[list[CommandHelp]] = None,
    filter_command: Optional[str] = None,
    width: Optional[int] = None,
) -> str:
    """Render the help screen.

    Args:
        commands: Command list to display. Uses defaults if None.
        filter_command: Show detailed help for a specific command.
        width: Terminal width override.

    Returns:
        Rendered help screen as a string.
    """
    if commands is None:
        commands = DEFAULT_COMMANDS
    if width is None:
        width = shutil.get_terminal_size((80, 24)).columns

    # Detailed help for a single command
    if filter_command:
        matches = [c for c in commands if c.name == filter_command or c.shortcut == filter_command]
        if not matches:
            return f"\n  {YELLOW}Unknown command: {filter_command}{RESET}\n  Type {GREEN}help{RESET} to see all commands.\n"
        cmd = matches[0]
        parts = [
            "",
            f"  {BOLD}{cmd.name}{RESET}  ({DIM}{cmd.shortcut}{RESET})",
            f"  {cmd.description}",
            f"  Category: {CYAN}{cmd.category}{RESET}",
            "",
            f"  {BOLD}Examples:{RESET}",
            _render_examples(cmd),
            "",
        ]
        return "\n".join(parts)

    # Full help listing
    header = f"\n{BOLD}{'pyclaude Help'.center(width)}{RESET}\n"
    rule = DIM + "\u2500" * width + RESET

    parts = [header, rule, ""]
    groups = _group_commands(commands)
    for category, cmds in groups.items():
        parts.append(f"  {BOLD}{YELLOW}{category}{RESET}")
        parts.append(_render_command_table(cmds, width))
        parts.append("")

    parts.extend([
        rule,
        f"  {DIM}Type {GREEN}help <command>{DIM} for detailed usage{RESET}",
        "",
    ])
    return "\n".join(parts)
