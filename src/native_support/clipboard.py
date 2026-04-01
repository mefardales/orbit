"""Clipboard operations using native platform tools."""

from __future__ import annotations

import subprocess
import shutil
from typing import Optional

from native_support.platform import detect_platform, PlatformType


class ClipboardError(RuntimeError):
    """Raised when clipboard operations fail."""


def _find_tool(candidates: list[str]) -> Optional[str]:
    """Find the first available tool from a list of candidates."""
    for tool in candidates:
        if shutil.which(tool):
            return tool
    return None


def _get_copy_cmd() -> list[str]:
    """Get the platform-appropriate clipboard copy command."""
    plat = detect_platform()
    if plat == PlatformType.MACOS:
        return ["pbcopy"]
    if plat == PlatformType.LINUX:
        # Try wayland first, then X11
        if shutil.which("wl-copy"):
            return ["wl-copy"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--input"]
        raise ClipboardError(
            "No clipboard tool found. Install xclip, xsel, or wl-clipboard."
        )
    if plat == PlatformType.WINDOWS:
        return ["clip.exe"]
    raise ClipboardError(f"Unsupported platform: {plat.value}")


def _get_paste_cmd() -> list[str]:
    """Get the platform-appropriate clipboard paste command."""
    plat = detect_platform()
    if plat == PlatformType.MACOS:
        return ["pbpaste"]
    if plat == PlatformType.LINUX:
        if shutil.which("wl-paste"):
            return ["wl-paste", "--no-newline"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-o"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--output"]
        raise ClipboardError(
            "No clipboard tool found. Install xclip, xsel, or wl-clipboard."
        )
    if plat == PlatformType.WINDOWS:
        return ["powershell.exe", "-command", "Get-Clipboard"]
    raise ClipboardError(f"Unsupported platform: {plat.value}")


def copy_to_clipboard(text: str, timeout: int = 5) -> bool:
    """Copy text to the system clipboard.

    Args:
        text: The text to copy.
        timeout: Timeout in seconds.

    Returns:
        True if successful.

    Raises:
        ClipboardError: If no clipboard tool is available.
    """
    cmd = _get_copy_cmd()
    try:
        proc = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        raise ClipboardError("Clipboard copy timed out")
    except FileNotFoundError:
        raise ClipboardError(f"Clipboard tool not found: {cmd[0]}")


def paste_from_clipboard(timeout: int = 5) -> str:
    """Paste text from the system clipboard.

    Args:
        timeout: Timeout in seconds.

    Returns:
        The clipboard contents as a string.

    Raises:
        ClipboardError: If no clipboard tool is available or paste fails.
    """
    cmd = _get_paste_cmd()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise ClipboardError(f"Paste failed: {proc.stderr.strip()}")
        return proc.stdout
    except subprocess.TimeoutExpired:
        raise ClipboardError("Clipboard paste timed out")
    except FileNotFoundError:
        raise ClipboardError(f"Clipboard tool not found: {cmd[0]}")


def clipboard_available() -> bool:
    """Check if clipboard operations are available on this platform."""
    try:
        _get_copy_cmd()
        _get_paste_cmd()
        return True
    except ClipboardError:
        return False
