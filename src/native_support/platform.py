"""Platform detection utilities."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PlatformType(Enum):
    MACOS = "macos"
    LINUX = "linux"
    WINDOWS = "windows"
    FREEBSD = "freebsd"
    UNKNOWN = "unknown"


class Architecture(Enum):
    X86_64 = "x86_64"
    ARM64 = "arm64"
    AARCH64 = "aarch64"
    I386 = "i386"
    UNKNOWN = "unknown"


@dataclass
class PlatformInfo:
    """Complete platform information."""

    os_type: PlatformType
    arch: Architecture
    shell: str
    terminal: str
    os_version: str
    hostname: str
    python_version: str


def detect_platform() -> PlatformType:
    """Detect the current operating system."""
    system = platform.system().lower()
    mapping = {
        "darwin": PlatformType.MACOS,
        "linux": PlatformType.LINUX,
        "windows": PlatformType.WINDOWS,
        "freebsd": PlatformType.FREEBSD,
    }
    return mapping.get(system, PlatformType.UNKNOWN)


def get_arch() -> Architecture:
    """Detect the CPU architecture."""
    machine = platform.machine().lower()
    mapping = {
        "x86_64": Architecture.X86_64,
        "amd64": Architecture.X86_64,
        "arm64": Architecture.ARM64,
        "aarch64": Architecture.AARCH64,
        "i386": Architecture.I386,
        "i686": Architecture.I386,
    }
    return mapping.get(machine, Architecture.UNKNOWN)


def get_shell() -> str:
    """Detect the current shell."""
    shell = os.environ.get("SHELL", "")
    if shell:
        return os.path.basename(shell)
    # Fallback: check parent process on Linux/macOS
    if detect_platform() != PlatformType.WINDOWS:
        try:
            ppid = os.getppid()
            result = subprocess.run(
                ["ps", "-p", str(ppid), "-o", "comm="],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return os.path.basename(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    # Windows fallback
    if os.environ.get("COMSPEC"):
        return os.path.basename(os.environ["COMSPEC"])
    return "unknown"


def get_terminal() -> str:
    """Detect the terminal emulator in use."""
    # Check common environment variables
    for var in ("TERM_PROGRAM", "TERMINAL_EMULATOR", "TERM"):
        val = os.environ.get(var)
        if val and val != "xterm-256color":
            return val

    plat = detect_platform()
    if plat == PlatformType.MACOS:
        term_prog = os.environ.get("TERM_PROGRAM", "")
        if term_prog:
            return term_prog
        return "Terminal.app"

    if plat == PlatformType.LINUX:
        # Try to detect from /proc
        try:
            ppid = os.getppid()
            exe = os.readlink(f"/proc/{ppid}/exe")
            name = os.path.basename(exe)
            if name not in ("bash", "zsh", "fish", "sh"):
                return name
        except OSError:
            pass
        # Check for known terminals
        for term in ("kitty", "alacritty", "gnome-terminal", "konsole", "xterm"):
            if shutil.which(term):
                return term

    return os.environ.get("TERM", "unknown")


def get_platform_info() -> PlatformInfo:
    """Gather complete platform information."""
    return PlatformInfo(
        os_type=detect_platform(),
        arch=get_arch(),
        shell=get_shell(),
        terminal=get_terminal(),
        os_version=platform.version(),
        hostname=platform.node(),
        python_version=platform.python_version(),
    )
