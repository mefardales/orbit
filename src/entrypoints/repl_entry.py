"""Interactive REPL mode for pyclaude."""

from __future__ import annotations

import readline
import sys
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class REPLConfig:
    """Configuration for the REPL session."""
    prompt: str = "pyclaude> "
    continuation_prompt: str = "... "
    history_file: str = ""
    max_history: int = 1000
    model: str | None = None
    multiline: bool = True


@dataclass
class REPLSession:
    """Tracks state for a REPL session."""
    session_id: str = ""
    turn_count: int = 0
    config: REPLConfig = field(default_factory=REPLConfig)
    _commands: dict[str, Callable[[str], str | None]] = field(default_factory=dict)
    _running: bool = False

    def register_command(self, name: str, handler: Callable[[str], str | None]) -> None:
        """Register a slash command (e.g., /quit, /clear)."""
        self._commands[name] = handler

    def handle_input(self, raw: str) -> str | None:
        """Process raw input, dispatching slash commands or returning user text."""
        stripped = raw.strip()
        if not stripped:
            return None
        if stripped.startswith("/"):
            parts = stripped[1:].split(None, 1)
            cmd_name = parts[0]
            cmd_args = parts[1] if len(parts) > 1 else ""
            handler = self._commands.get(cmd_name)
            if handler:
                return handler(cmd_args)
            return f"Unknown command: /{cmd_name}. Type /help for available commands."
        self.turn_count += 1
        return stripped

    def run_loop(self) -> int:
        """Main REPL loop. Returns exit code."""
        self._running = True
        self._setup_readline()
        self._register_default_commands()

        print(f"pyclaude interactive mode (model={self.config.model or 'default'})")
        print("Type /help for commands, /quit to exit.\n")

        while self._running:
            try:
                raw = input(self.config.prompt)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\n(Use /quit to exit)")
                continue

            result = self.handle_input(raw)
            if result is not None:
                print(result)

        self._save_history()
        return 0

    def stop(self) -> None:
        self._running = False

    def _setup_readline(self) -> None:
        try:
            if self.config.history_file:
                try:
                    readline.read_history_file(self.config.history_file)
                except FileNotFoundError:
                    pass
                readline.set_history_length(self.config.max_history)
        except Exception:
            pass

    def _save_history(self) -> None:
        if self.config.history_file:
            try:
                readline.write_history_file(self.config.history_file)
            except Exception:
                pass

    def _register_default_commands(self) -> None:
        self.register_command("quit", lambda _: (self.stop(), "Goodbye.")[1])
        self.register_command("exit", lambda _: (self.stop(), "Goodbye.")[1])
        self.register_command("clear", lambda _: "Context cleared.")
        self.register_command("help", self._help_command)
        self.register_command("model", lambda args: f"Model set to: {args}" if args else f"Current model: {self.config.model or 'default'}")
        self.register_command("turns", lambda _: f"Turns so far: {self.turn_count}")

    def _help_command(self, _: str) -> str:
        lines = ["Available commands:"]
        for name in sorted(self._commands):
            lines.append(f"  /{name}")
        return "\n".join(lines)


def start_repl(
    initial_prompt: str | None = None,
    model: str | None = None,
    resume_session: str | None = None,
) -> int:
    """Entry point to start the REPL."""
    config = REPLConfig(model=model)
    session = REPLSession(config=config, session_id=resume_session or "")

    if initial_prompt:
        result = session.handle_input(initial_prompt)
        if result:
            print(result)

    return session.run_loop()
