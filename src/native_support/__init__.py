"""Native platform support subsystem."""

from native_support.platform import detect_platform, get_arch, get_shell, get_terminal
from native_support.clipboard import copy_to_clipboard, paste_from_clipboard
from native_support.notifications import send_notification

__all__ = [
    "detect_platform", "get_arch", "get_shell", "get_terminal",
    "copy_to_clipboard", "paste_from_clipboard",
    "send_notification",
]
