"""Platform-aware command execution."""
from __future__ import annotations
import platform
import subprocess

def run_platform_command(command: list[str], timeout: float = 30.0) -> tuple[str, str, int]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return '', f'Command not found: {command[0]}', 127
    except subprocess.TimeoutExpired:
        return '', f'Command timed out after {timeout}s', 124

def is_macos() -> bool:
    return platform.system() == 'Darwin'

def is_linux() -> bool:
    return platform.system() == 'Linux'
