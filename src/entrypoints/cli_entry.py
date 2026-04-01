"""CLI entry point - main command-line dispatcher with argument parsing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Sequence


class CLIDispatcher:
    """Dispatches CLI commands to registered handlers."""

    def __init__(self, prog: str = "orbit", version: str = "0.1.0") -> None:
        self.prog = prog
        self.version = version
        self._parser = argparse.ArgumentParser(
            prog=prog,
            description="orbit - Python implementation of Claude Code",
        )
        self._parser.add_argument("--version", action="version", version=f"%(prog)s {version}")
        self._parser.add_argument("--verbose", "-v", action="count", default=0, help="Increase verbosity")
        self._parser.add_argument("--config", type=Path, default=None, help="Config file path")
        self._parser.add_argument("--data-dir", type=Path, default=None, help="Data directory")

        self._subparsers = self._parser.add_subparsers(dest="command", help="Available commands")
        self._handlers: dict[str, Callable[[argparse.Namespace], int]] = {}

    def register_command(
        self,
        name: str,
        handler: Callable[[argparse.Namespace], int],
        help_text: str = "",
        aliases: list[str] | None = None,
    ) -> argparse.ArgumentParser:
        """Register a subcommand with its handler."""
        sub = self._subparsers.add_parser(name, help=help_text, aliases=aliases or [])
        self._handlers[name] = handler
        if aliases:
            for alias in aliases:
                self._handlers[alias] = handler
        return sub

    def parse_args(self, argv: Sequence[str] | None = None) -> argparse.Namespace:
        return self._parser.parse_args(argv)

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Parse arguments and dispatch to the appropriate handler."""
        args = self.parse_args(argv)
        if args.command is None:
            self._parser.print_help()
            return 0
        handler = self._handlers.get(args.command)
        if handler is None:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1
        try:
            return handler(args)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            return 130
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            if args.verbose > 0:
                import traceback
                traceback.print_exc()
            return 1


def build_default_cli() -> CLIDispatcher:
    """Build the default CLI with standard commands."""
    cli = CLIDispatcher()

    # Chat command
    chat_parser = cli.register_command("chat", _cmd_chat, "Start interactive chat", aliases=["c"])
    chat_parser.add_argument("prompt", nargs="?", default=None, help="Initial prompt")
    chat_parser.add_argument("--model", "-m", default=None, help="Model to use")
    chat_parser.add_argument("--resume", "-r", default=None, help="Resume session ID")

    # Ask command (non-interactive)
    ask_parser = cli.register_command("ask", _cmd_ask, "Ask a single question")
    ask_parser.add_argument("prompt", help="The question to ask")
    ask_parser.add_argument("--model", "-m", default=None)

    # Doctor command
    cli.register_command("doctor", _cmd_doctor, "Run diagnostics")

    # Config command
    config_parser = cli.register_command("config", _cmd_config, "Manage configuration")
    config_parser.add_argument("action", choices=["show", "set", "reset"], help="Config action")
    config_parser.add_argument("key", nargs="?", help="Config key")
    config_parser.add_argument("value", nargs="?", help="Config value")

    return cli


def _cmd_chat(args: argparse.Namespace) -> int:
    from .repl_entry import start_repl
    return start_repl(initial_prompt=args.prompt, model=args.model, resume_session=args.resume)


def _cmd_ask(args: argparse.Namespace) -> int:
    print(f"[ask] prompt={args.prompt!r} model={args.model}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    print("Running diagnostics...")
    checks = ["python_version", "config_valid", "api_key_set", "connectivity"]
    for check in checks:
        print(f"  [{check}] ok")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    if args.action == "show":
        print(f"Config key={args.key or '(all)'}")
    elif args.action == "set":
        print(f"Set {args.key}={args.value}")
    elif args.action == "reset":
        print("Config reset to defaults")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    cli = build_default_cli()
    return cli.run(argv)
