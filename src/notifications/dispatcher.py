"""
Notification Dispatcher

Sends notifications to configured platforms (Discord, Telegram, Slack, webhook).
All sends are non-blocking with timeouts. Failures are swallowed to avoid
blocking hooks.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional
from urllib.parse import urlparse

from .config import parse_mention_allowed_mentions
from .types import (
    DiscordBotNotificationConfig,
    DiscordNotificationConfig,
    DispatchResult,
    FullNotificationConfig,
    FullNotificationPayload,
    NotificationPlatform,
    NotificationResult,
    SlackNotificationConfig,
    TelegramNotificationConfig,
    WebhookNotificationConfig,
)

SEND_TIMEOUT_S = 10
DISPATCH_TIMEOUT_S = 15
DISCORD_MAX_CONTENT_LENGTH = 2000


def _compose_discord_content(
    message: str,
    mention: Optional[str],
) -> dict:
    """Build Discord message body with mention handling and length capping."""
    mention_parsed = parse_mention_allowed_mentions(mention)
    allowed_mentions = {
        "parse": [],
        **({"users": mention_parsed["users"]} if "users" in mention_parsed else {}),
        **({"roles": mention_parsed["roles"]} if "roles" in mention_parsed else {}),
    }

    if mention:
        prefix = f"{mention}\n"
        max_body = DISCORD_MAX_CONTENT_LENGTH - len(prefix)
        body = message[:max_body - 1] + "\u2026" if len(message) > max_body else message
        content = f"{prefix}{body}"
    else:
        content = (
            message[:DISCORD_MAX_CONTENT_LENGTH - 1] + "\u2026"
            if len(message) > DISCORD_MAX_CONTENT_LENGTH
            else message
        )

    return {"content": content, "allowed_mentions": allowed_mentions}


def _validate_discord_url(webhook_url: str) -> bool:
    try:
        parsed = urlparse(webhook_url)
        allowed_hosts = ["discord.com", "discordapp.com"]
        if not any(
            parsed.hostname == host or (parsed.hostname and parsed.hostname.endswith(f".{host}"))
            for host in allowed_hosts
        ):
            return False
        return parsed.scheme == "https"
    except Exception:
        return False


def _validate_telegram_token(token: str) -> bool:
    return bool(re.match(r"^[0-9]+:[A-Za-z0-9_-]+$", token))


def _validate_slack_url(webhook_url: str) -> bool:
    try:
        parsed = urlparse(webhook_url)
        return (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and (
                parsed.hostname == "hooks.slack.com"
                or parsed.hostname.endswith(".hooks.slack.com")
            )
        )
    except Exception:
        return False


def _validate_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https"
    except Exception:
        return False


async def _http_post_json(
    url: str,
    body: dict,
    headers: Optional[dict[str, str]] = None,
    method: str = "POST",
    timeout: float = SEND_TIMEOUT_S,
) -> tuple[int, Optional[dict]]:
    """Perform an HTTP POST/PUT with JSON body. Returns (status_code, response_json)."""
    import aiohttp

    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)

    async with aiohttp.ClientSession() as session:
        async with session.request(
            method,
            url,
            json=body,
            headers=all_headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = None
            return resp.status, data


async def send_discord(
    config: DiscordNotificationConfig,
    payload: FullNotificationPayload,
) -> NotificationResult:
    """Send a notification via Discord webhook."""
    if not config.enabled or not config.webhook_url:
        return NotificationResult(platform=NotificationPlatform.DISCORD, success=False, error="Not configured")

    if not _validate_discord_url(config.webhook_url):
        return NotificationResult(platform=NotificationPlatform.DISCORD, success=False, error="Invalid webhook URL")

    try:
        composed = _compose_discord_content(payload.message, config.mention)
        body: dict = {**composed}
        if config.username:
            body["username"] = config.username

        status, _ = await _http_post_json(config.webhook_url, body)
        if status < 200 or status >= 300:
            return NotificationResult(platform=NotificationPlatform.DISCORD, success=False, error=f"HTTP {status}")
        return NotificationResult(platform=NotificationPlatform.DISCORD, success=True)
    except Exception as e:
        return NotificationResult(platform=NotificationPlatform.DISCORD, success=False, error=str(e))


async def send_discord_bot(
    config: DiscordBotNotificationConfig,
    payload: FullNotificationPayload,
) -> NotificationResult:
    """Send a notification via Discord Bot API."""
    if not config.enabled:
        return NotificationResult(platform=NotificationPlatform.DISCORD_BOT, success=False, error="Not enabled")

    if not config.bot_token or not config.channel_id:
        return NotificationResult(
            platform=NotificationPlatform.DISCORD_BOT, success=False, error="Missing bot_token or channel_id"
        )

    try:
        composed = _compose_discord_content(payload.message, config.mention)
        url = f"https://discord.com/api/v10/channels/{config.channel_id}/messages"
        headers = {"Authorization": f"Bot {config.bot_token}"}

        status, data = await _http_post_json(url, composed, headers=headers)
        if status < 200 or status >= 300:
            return NotificationResult(platform=NotificationPlatform.DISCORD_BOT, success=False, error=f"HTTP {status}")

        message_id = data.get("id") if isinstance(data, dict) else None
        return NotificationResult(platform=NotificationPlatform.DISCORD_BOT, success=True, message_id=message_id)
    except Exception as e:
        return NotificationResult(platform=NotificationPlatform.DISCORD_BOT, success=False, error=str(e))


async def send_telegram(
    config: TelegramNotificationConfig,
    payload: FullNotificationPayload,
) -> NotificationResult:
    """Send a notification via Telegram Bot API."""
    if not config.enabled or not config.bot_token or not config.chat_id:
        return NotificationResult(platform=NotificationPlatform.TELEGRAM, success=False, error="Not configured")

    if not _validate_telegram_token(config.bot_token):
        return NotificationResult(
            platform=NotificationPlatform.TELEGRAM, success=False, error="Invalid bot token format"
        )

    try:
        url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
        body = {
            "chat_id": config.chat_id,
            "text": payload.message,
            "parse_mode": config.parse_mode or "Markdown",
        }

        status, data = await _http_post_json(url, body)
        if status < 200 or status >= 300:
            return NotificationResult(platform=NotificationPlatform.TELEGRAM, success=False, error=f"HTTP {status}")

        message_id = None
        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict) and "message_id" in result:
                message_id = str(result["message_id"])

        return NotificationResult(platform=NotificationPlatform.TELEGRAM, success=True, message_id=message_id)
    except Exception as e:
        return NotificationResult(platform=NotificationPlatform.TELEGRAM, success=False, error=str(e))


async def send_slack(
    config: SlackNotificationConfig,
    payload: FullNotificationPayload,
) -> NotificationResult:
    """Send a notification via Slack incoming webhook."""
    if not config.enabled or not config.webhook_url:
        return NotificationResult(platform=NotificationPlatform.SLACK, success=False, error="Not configured")

    if not _validate_slack_url(config.webhook_url):
        return NotificationResult(platform=NotificationPlatform.SLACK, success=False, error="Invalid webhook URL")

    try:
        body: dict = {"text": payload.message}
        if config.channel:
            body["channel"] = config.channel
        if config.username:
            body["username"] = config.username

        status, _ = await _http_post_json(config.webhook_url, body)
        if status < 200 or status >= 300:
            return NotificationResult(platform=NotificationPlatform.SLACK, success=False, error=f"HTTP {status}")
        return NotificationResult(platform=NotificationPlatform.SLACK, success=True)
    except Exception as e:
        return NotificationResult(platform=NotificationPlatform.SLACK, success=False, error=str(e))


async def send_webhook(
    config: WebhookNotificationConfig,
    payload: FullNotificationPayload,
) -> NotificationResult:
    """Send a notification via generic webhook."""
    if not config.enabled or not config.url:
        return NotificationResult(platform=NotificationPlatform.WEBHOOK, success=False, error="Not configured")

    if not _validate_webhook_url(config.url):
        return NotificationResult(
            platform=NotificationPlatform.WEBHOOK, success=False, error="Invalid URL (HTTPS required)"
        )

    try:
        body = {
            "event": payload.event.value if hasattr(payload.event, "value") else payload.event,
            "session_id": payload.session_id,
            "message": payload.message,
            "timestamp": payload.timestamp,
            "tmux_session": payload.tmux_session,
            "project_name": payload.project_name,
            "project_path": payload.project_path,
            "modes_used": payload.modes_used,
            "duration_ms": payload.duration_ms,
            "reason": payload.reason,
            "active_mode": payload.active_mode,
            "question": payload.question,
        }

        status, _ = await _http_post_json(
            config.url,
            body,
            headers=config.headers,
            method=config.method or "POST",
        )
        if status < 200 or status >= 300:
            return NotificationResult(platform=NotificationPlatform.WEBHOOK, success=False, error=f"HTTP {status}")
        return NotificationResult(platform=NotificationPlatform.WEBHOOK, success=True)
    except Exception as e:
        return NotificationResult(platform=NotificationPlatform.WEBHOOK, success=False, error=str(e))


def _get_effective_platform_config(
    platform: NotificationPlatform,
    config: FullNotificationConfig,
    event: str,
):
    """Get the effective platform config, checking event-level overrides first."""
    event_config = (config.events or {}).get(event)
    if event_config:
        attr_name = platform.value.replace("-", "_")
        event_plat = getattr(event_config, attr_name, None)
        if event_plat is not None and hasattr(event_plat, "enabled"):
            return event_plat

    attr_name = platform.value.replace("-", "_")
    return getattr(config, attr_name, None)


async def dispatch_notifications(
    config: FullNotificationConfig,
    event: str,
    payload: FullNotificationPayload,
) -> DispatchResult:
    """Dispatch notifications to all enabled platforms for an event."""
    tasks: list[asyncio.Task] = []

    discord_config = _get_effective_platform_config(NotificationPlatform.DISCORD, config, event)
    if isinstance(discord_config, DiscordNotificationConfig) and discord_config.enabled:
        tasks.append(asyncio.create_task(send_discord(discord_config, payload)))

    telegram_config = _get_effective_platform_config(NotificationPlatform.TELEGRAM, config, event)
    if isinstance(telegram_config, TelegramNotificationConfig) and telegram_config.enabled:
        tasks.append(asyncio.create_task(send_telegram(telegram_config, payload)))

    slack_config = _get_effective_platform_config(NotificationPlatform.SLACK, config, event)
    if isinstance(slack_config, SlackNotificationConfig) and slack_config.enabled:
        tasks.append(asyncio.create_task(send_slack(slack_config, payload)))

    webhook_config = _get_effective_platform_config(NotificationPlatform.WEBHOOK, config, event)
    if isinstance(webhook_config, WebhookNotificationConfig) and webhook_config.enabled:
        tasks.append(asyncio.create_task(send_webhook(webhook_config, payload)))

    discord_bot_config = _get_effective_platform_config(NotificationPlatform.DISCORD_BOT, config, event)
    if isinstance(discord_bot_config, DiscordBotNotificationConfig) and discord_bot_config.enabled:
        tasks.append(asyncio.create_task(send_discord_bot(discord_bot_config, payload)))

    if not tasks:
        return DispatchResult(event=payload.event, results=[], any_success=False)

    try:
        done, _ = await asyncio.wait(tasks, timeout=DISPATCH_TIMEOUT_S)
        results: list[NotificationResult] = []
        for task in done:
            try:
                results.append(task.result())
            except Exception as e:
                results.append(
                    NotificationResult(
                        platform=NotificationPlatform.WEBHOOK,
                        success=False,
                        error=str(e),
                    )
                )

        # Add timeout results for pending tasks
        for task in tasks:
            if task not in done:
                results.append(
                    NotificationResult(
                        platform=NotificationPlatform.WEBHOOK,
                        success=False,
                        error="Dispatch timeout",
                    )
                )
                task.cancel()

        return DispatchResult(
            event=payload.event,
            results=results,
            any_success=any(r.success for r in results),
        )
    except Exception as e:
        return DispatchResult(
            event=payload.event,
            results=[
                NotificationResult(
                    platform=NotificationPlatform.WEBHOOK,
                    success=False,
                    error=str(e),
                )
            ],
            any_success=False,
        )
