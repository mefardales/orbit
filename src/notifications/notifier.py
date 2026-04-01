"""
Notification system for pyclaude (legacy notifier)

Supports desktop notifications, Discord webhooks, and Telegram bots.
"""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

HTTP_REQUEST_TIMEOUT_S = 10


@dataclass
class NotificationConfig:
    """Legacy notification configuration."""
    desktop: Optional[bool] = None
    discord: Optional[dict] = None  # {"webhookUrl": str}
    telegram: Optional[dict] = None  # {"botToken": str, "chatId": str}


@dataclass
class NotificationPayload:
    """Legacy notification payload."""
    title: str = ""
    message: str = ""
    type: str = "info"  # "info" | "success" | "warning" | "error"
    mode: Optional[str] = None
    project_path: Optional[str] = None


async def load_notification_config(project_root: Optional[str] = None) -> Optional[NotificationConfig]:
    """Load notification config from .pyclaude/notifications.json."""
    root = Path(project_root) if project_root else Path.cwd()
    config_path = root / ".pyclaude" / "notifications.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return NotificationConfig(
            desktop=data.get("desktop"),
            discord=data.get("discord"),
            telegram=data.get("telegram"),
        )
    except Exception:
        return None


def build_desktop_args(
    title: str,
    message: str,
    os_platform: Optional[str] = None,
) -> Optional[tuple[str, list[str]]]:
    """
    Build the command and args for a desktop notification.
    Exported for unit testing.
    """
    plat = os_platform or sys.platform

    if plat == "darwin":
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
        return (
            "osascript",
            ["-e", f'display notification "{safe_message}" with title "{safe_title}"'],
        )
    elif plat == "linux":
        return ("notify-send", [title, message])
    elif plat == "win32":
        safe_title = title.replace("'", "''")
        safe_message = message.replace("'", "''")
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, "
            "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(0); "
            "$text = $xml.GetElementsByTagName('text'); "
            f"$text[0].AppendChild($xml.CreateTextNode('{safe_title}')) > $null; "
            f"$text[1].AppendChild($xml.CreateTextNode('{safe_message}')) > $null; "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('pyclaude').Show($xml)"
        )
        return ("powershell", ["-Command", ps])

    return None


async def _send_desktop_notification(payload: NotificationPayload) -> None:
    result = build_desktop_args(payload.title, payload.message)
    if not result:
        return
    cmd, args = result
    try:
        subprocess.run([cmd, *args], capture_output=True, timeout=5)
    except Exception:
        pass  # Desktop notification is best-effort


async def _send_json_https_request(
    url: str,
    body: str,
    error_prefix: str,
    timeout: float = HTTP_REQUEST_TIMEOUT_S,
) -> None:
    """Send an HTTPS POST with JSON body."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"{error_prefix}_http_{resp.status}")


async def _send_discord_notification(payload: NotificationPayload, webhook_url: str) -> None:
    color_map = {"info": 3447003, "success": 3066993, "warning": 15105570, "error": 15158332}
    from datetime import datetime, timezone

    body = json.dumps({
        "embeds": [{
            "title": f"[Pyclaude] {payload.title}",
            "description": payload.message,
            "color": color_map.get(payload.type, 3447003),
            "footer": {"text": f"pyclaude | {payload.mode or 'general'}"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    })

    try:
        await _send_json_https_request(webhook_url, body, "discord")
    except Exception:
        pass  # Discord notification is best-effort


async def _send_telegram_notification(
    payload: NotificationPayload,
    bot_token: str,
    chat_id: str,
) -> None:
    text = f"*[Pyclaude] {payload.title}*\n{payload.message}"
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        await _send_json_https_request(url, body, "telegram")
    except Exception:
        pass  # Telegram notification is best-effort


async def notify(
    payload: NotificationPayload,
    config: Optional[NotificationConfig] = None,
) -> None:
    """Send notification via all configured channels."""
    if config is None:
        config = await load_notification_config()
        if config is None:
            return

    tasks: list[asyncio.Task] = []

    if config.desktop:
        tasks.append(asyncio.create_task(_send_desktop_notification(payload)))

    if config.discord and config.discord.get("webhookUrl"):
        tasks.append(
            asyncio.create_task(
                _send_discord_notification(payload, config.discord["webhookUrl"])
            )
        )

    if config.telegram and config.telegram.get("botToken") and config.telegram.get("chatId"):
        tasks.append(
            asyncio.create_task(
                _send_telegram_notification(
                    payload,
                    config.telegram["botToken"],
                    config.telegram["chatId"],
                )
            )
        )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
