"""Command execution wrapper."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List

from .error import SparkshellError


@dataclass
class CommandOutput:
    returncode: int
    stdout: bytes
    stderr: bytes

    def exit_code(self) -> int:
        return self.returncode

    def stdout_text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", errors="replace")


def execute_command(argv: List[str]) -> CommandOutput:
    """Execute a command directly (no shell metacharacter parsing)."""
    if not argv:
        raise SparkshellError.invalid_args("usage: omx-sparkshell <command> [args...]")

    try:
        result = subprocess.run(argv, capture_output=True)
    except FileNotFoundError as exc:
        raise SparkshellError.io_error(exc) from exc
    except OSError as exc:
        raise SparkshellError.io_error(exc) from exc

    return CommandOutput(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
