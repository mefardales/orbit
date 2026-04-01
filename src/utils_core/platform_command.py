"""Platform-aware command execution utilities."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple, Union


def is_macos() -> bool:
    """Return True if running on macOS."""
    return platform.system() == "Darwin"


def is_linux() -> bool:
    """Return True if running on Linux."""
    return platform.system() == "Linux"


def get_shell() -> str:
    """Return the current user's shell path.

    Falls back to /bin/sh if the shell cannot be determined.
    """
    shell = os.environ.get("SHELL", "")
    if shell and shutil.which(shell):
        return shell
    for candidate in ["/bin/zsh", "/bin/bash", "/bin/sh"]:
        if os.path.exists(candidate):
            return candidate
    return "/bin/sh"


def run_platform_command(
    command: Union[str, List[str]],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
    capture_output: bool = True,
    shell: bool = False,
) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr).

    Args:
        command: Command string or arg list.
        cwd: Working directory for the command.
        env: Environment variables (merged with current env).
        timeout: Maximum seconds to wait.
        capture_output: Whether to capture stdout/stderr.
        shell: Whether to run via shell.

    Returns:
        Tuple of (return_code, stdout_text, stderr_text).
    """
    run_env = dict(os.environ)
    if env:
        run_env.update(env)

    if isinstance(command, str) and not shell:
        shell = True

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=run_env,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
            shell=shell,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return -1, "", f"Command not found: {e}"
    except OSError as e:
        return -1, "", f"OS error: {e}"
