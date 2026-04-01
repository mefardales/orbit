"""Native desktop notification support."""

from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass
from typing import Optional

from .platform import detect_platform, PlatformType


class NotificationError(RuntimeError):
    """Raised when notifications fail."""


@dataclass
class NotificationResult:
    """Result of a notification attempt."""

    sent: bool
    method: str
    error: Optional[str] = None


def _send_macos(title: str, message: str, subtitle: Optional[str], sound: bool) -> NotificationResult:
    """Send notification on macOS via osascript."""
    parts = [f'display notification "{message}"']
    parts.append(f'with title "{title}"')
    if subtitle:
        parts.append(f'subtitle "{subtitle}"')
    if sound:
        parts.append('sound name "default"')
    script = " ".join(parts)
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            return NotificationResult(sent=True, method="osascript")
        return NotificationResult(sent=False, method="osascript", error=proc.stderr.strip())
    except FileNotFoundError:
        return NotificationResult(sent=False, method="osascript", error="osascript not found")
    except subprocess.TimeoutExpired:
        return NotificationResult(sent=False, method="osascript", error="Timed out")


def _send_linux(title: str, message: str, subtitle: Optional[str], sound: bool) -> NotificationResult:
    """Send notification on Linux via notify-send."""
    if not shutil.which("notify-send"):
        return NotificationResult(sent=False, method="notify-send", error="notify-send not installed")
    body = f"{subtitle}\n{message}" if subtitle else message
    args = ["notify-send", title, body]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return NotificationResult(sent=True, method="notify-send")
        return NotificationResult(sent=False, method="notify-send", error=proc.stderr.strip())
    except subprocess.TimeoutExpired:
        return NotificationResult(sent=False, method="notify-send", error="Timed out")


def _send_terminal_bell() -> NotificationResult:
    """Fallback: send a terminal bell character."""
    print("\a", end="", flush=True)
    return NotificationResult(sent=True, method="terminal_bell")


def send_notification(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound: bool = True,
    fallback_bell: bool = True,
) -> NotificationResult:
    """Send a desktop notification using the platform's native method.

    Args:
        title: Notification title.
        message: Notification body text.
        subtitle: Optional subtitle (macOS only).
        sound: Play a notification sound.
        fallback_bell: If True, fall back to terminal bell if native fails.

    Returns:
        NotificationResult indicating success/failure and method used.
    """
    # Escape quotes in message/title to prevent injection
    title = title.replace('"', '\\"')
    message = message.replace('"', '\\"')
    if subtitle:
        subtitle = subtitle.replace('"', '\\"')

    plat = detect_platform()

    if plat == PlatformType.MACOS:
        result = _send_macos(title, message, subtitle, sound)
        if result.sent:
            return result

    elif plat == PlatformType.LINUX:
        result = _send_linux(title, message, subtitle, sound)
        if result.sent:
            return result

    # Fallback
    if fallback_bell:
        return _send_terminal_bell()

    return NotificationResult(
        sent=False,
        method="none",
        error=f"No notification method available for {plat.value}",
    )


def notifications_available() -> bool:
    """Check if native notifications are available."""
    plat = detect_platform()
    if plat == PlatformType.MACOS:
        return shutil.which("osascript") is not None
    if plat == PlatformType.LINUX:
        return shutil.which("notify-send") is not None
    return False
