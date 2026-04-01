"""Voice command parsing and definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VoiceCommand:
    """A parsed voice command."""

    action: str
    args: list[str] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0

    @property
    def full_args(self) -> str:
        """Join args into a single string."""
        return " ".join(self.args)


@dataclass
class CommandPattern:
    """A pattern that maps spoken phrases to actions."""

    action: str
    patterns: list[str]      # regex patterns
    description: str = ""
    examples: list[str] = field(default_factory=list)


# Voice command definitions
VOICE_COMMANDS: dict[str, CommandPattern] = {
    "open_file": CommandPattern(
        action="open_file",
        patterns=[
            r"(?:open|edit|show)\s+(?:file\s+)?(.+)",
        ],
        description="Open a file for editing",
        examples=["open file main.py", "edit config.yaml"],
    ),
    "search": CommandPattern(
        action="search",
        patterns=[
            r"(?:search|find|look for|grep)\s+(?:for\s+)?(.+)",
        ],
        description="Search the codebase",
        examples=["search for TODO", "find function main"],
    ),
    "run_command": CommandPattern(
        action="run_command",
        patterns=[
            r"(?:run|execute|do)\s+(.+)",
        ],
        description="Run a shell command",
        examples=["run tests", "execute build"],
    ),
    "ask": CommandPattern(
        action="ask",
        patterns=[
            r"(?:ask|question|explain|what is|how to|how do I)\s+(.+)",
        ],
        description="Ask the AI a question",
        examples=["ask how to sort a list", "explain this function"],
    ),
    "git_commit": CommandPattern(
        action="git_commit",
        patterns=[
            r"(?:commit|save)\s+(?:with message\s+)?(.+)",
            r"(?:git\s+)?commit\s+(.+)",
        ],
        description="Create a git commit",
        examples=["commit fix typo", "git commit update readme"],
    ),
    "git_diff": CommandPattern(
        action="git_diff",
        patterns=[
            r"(?:show\s+)?(?:git\s+)?diff(?:\s+(.*))?",
            r"what(?:\s+did I|\s+has)\s+change[ds]?",
        ],
        description="Show git diff",
        examples=["show diff", "what changed"],
    ),
    "undo": CommandPattern(
        action="undo",
        patterns=[r"undo(?:\s+(.*))?", r"go\s+back"],
        description="Undo last action",
        examples=["undo", "go back"],
    ),
    "redo": CommandPattern(
        action="redo",
        patterns=[r"redo(?:\s+(.*))?"],
        description="Redo last undone action",
        examples=["redo"],
    ),
    "help": CommandPattern(
        action="help",
        patterns=[
            r"(?:show\s+)?help(?:\s+(.*))?",
            r"what can (?:you|I) do",
        ],
        description="Show help",
        examples=["help", "show help", "what can you do"],
    ),
    "quit": CommandPattern(
        action="quit",
        patterns=[r"(?:quit|exit|close|bye|goodbye|stop)"],
        description="Exit orbit",
        examples=["quit", "exit", "goodbye"],
    ),
    "navigate": CommandPattern(
        action="navigate",
        patterns=[
            r"(?:go to|jump to|navigate to)\s+(?:line\s+)?(\d+)",
            r"line\s+(\d+)",
        ],
        description="Navigate to a line number",
        examples=["go to line 42", "jump to 100"],
    ),
    "select": CommandPattern(
        action="select",
        patterns=[
            r"select\s+(?:lines?\s+)?(\d+)\s+(?:to|through)\s+(\d+)",
            r"highlight\s+(?:lines?\s+)?(\d+)\s+(?:to|through)\s+(\d+)",
        ],
        description="Select a range of lines",
        examples=["select lines 10 to 20", "highlight 5 through 15"],
    ),
    "copy": CommandPattern(
        action="copy",
        patterns=[r"copy(?:\s+(?:that|this|selection))?"],
        description="Copy current selection",
        examples=["copy", "copy that"],
    ),
    "paste": CommandPattern(
        action="paste",
        patterns=[r"paste(?:\s+(?:that|here))?"],
        description="Paste from clipboard",
        examples=["paste", "paste here"],
    ),
    "new_task": CommandPattern(
        action="new_task",
        patterns=[
            r"(?:new\s+|add\s+|create\s+)?task\s+(.+)",
        ],
        description="Create a new task",
        examples=["new task write tests", "add task fix bug"],
    ),
    "voice_stop": CommandPattern(
        action="voice_stop",
        patterns=[r"(?:stop\s+)?listening", r"voice\s+off"],
        description="Stop voice input",
        examples=["stop listening", "voice off"],
    ),
}


def parse_voice_command(
    text: str,
    commands: Optional[dict[str, CommandPattern]] = None,
) -> Optional[VoiceCommand]:
    """Parse spoken text into a VoiceCommand.

    Args:
        text: The transcribed speech text.
        commands: Command patterns to match against. Uses defaults if None.

    Returns:
        A VoiceCommand if matched, or None.
    """
    if commands is None:
        commands = VOICE_COMMANDS

    text = text.strip().lower()
    if not text:
        return None

    best_match: Optional[VoiceCommand] = None
    best_specificity = 0

    for cmd_name, pattern in commands.items():
        for regex in pattern.patterns:
            m = re.match(regex, text, re.IGNORECASE)
            if m:
                groups = [g for g in m.groups() if g is not None]
                specificity = len(regex)  # longer patterns are more specific
                if specificity > best_specificity:
                    best_specificity = specificity
                    best_match = VoiceCommand(
                        action=pattern.action,
                        args=groups,
                        raw_text=text,
                        confidence=0.8,
                    )

    return best_match


def list_voice_commands() -> list[tuple[str, str, list[str]]]:
    """List all available voice commands.

    Returns:
        List of (action, description, examples) tuples.
    """
    return [
        (cp.action, cp.description, cp.examples)
        for cp in VOICE_COMMANDS.values()
    ]
