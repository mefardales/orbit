"""
Notification Configuration Reader

Reads notification config from .orbit-config.json and provides
backward compatibility with the old stopHookCallbacks format.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path
from typing import Optional

from .types import (
    DiscordBotNotificationConfig,
    DiscordNotificationConfig,
    EventNotificationConfig,
    FullNotificationConfig,
    NotificationEvent,
    NotificationPlatform,
    NotificationsBlock,
    SlackNotificationConfig,
    TelegramNotificationConfig,
    VerbosityLevel,
)


def _codex_home() -> Path:
    """Return the codex home directory (~/.codex by default)."""
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


CONFIG_FILE = _codex_home() / ".orbit-config.json"


def _read_raw_config() -> Optional[dict]:
    if not CONFIG_FILE.exists():
        return None
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _migrate_stop_hook_callbacks(raw: dict) -> Optional[FullNotificationConfig]:
    callbacks = raw.get("stopHookCallbacks")
    if not callbacks or not isinstance(callbacks, dict):
        return None

    config = FullNotificationConfig(
        enabled=True,
        events={"session-end": EventNotificationConfig(enabled=True)},
    )

    telegram = callbacks.get("telegram")
    if isinstance(telegram, dict) and telegram.get("enabled"):
        config.telegram = TelegramNotificationConfig(
            enabled=True,
            bot_token=telegram.get("botToken", ""),
            chat_id=telegram.get("chatId", ""),
        )

    discord = callbacks.get("discord")
    if isinstance(discord, dict) and discord.get("enabled"):
        config.discord = DiscordNotificationConfig(
            enabled=True,
            webhook_url=discord.get("webhookUrl", ""),
        )

    return config


def _normalize_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def validate_mention(raw: Optional[str]) -> Optional[str]:
    """Validate a Discord mention string."""
    mention = _normalize_optional(raw)
    if not mention:
        return None
    if re.match(r"^<@!?\d{17,20}>$", mention) or re.match(r"^<@&\d{17,20}>$", mention):
        return mention
    return None


def validate_slack_mention(raw: Optional[str]) -> Optional[str]:
    """
    Validate Slack mention format.
    Accepts: <@UXXXXXXXX> (user), <!channel>, <!here>, <!everyone>,
    <!subteam^SXXXXXXXXX> (user group).
    """
    mention = _normalize_optional(raw)
    if not mention:
        return None
    if re.match(r"^<@[UW][A-Z0-9]{8,11}>$", mention):
        return mention
    if re.match(r"^<!(?:channel|here|everyone)>$", mention):
        return mention
    if re.match(r"^<!subteam\^S[A-Z0-9]{8,11}>$", mention):
        return mention
    return None


def parse_mention_allowed_mentions(mention: Optional[str]) -> dict:
    """Parse a Discord mention into allowed_mentions structure."""
    if not mention:
        return {}
    user_match = re.match(r"^<@!?(\d{17,20})>$", mention)
    if user_match:
        return {"users": [user_match.group(1)]}
    role_match = re.match(r"^<@&(\d{17,20})>$", mention)
    if role_match:
        return {"roles": [role_match.group(1)]}
    return {}


def build_config_from_env() -> Optional[FullNotificationConfig]:
    """Build notification config from environment variables."""
    config = FullNotificationConfig(enabled=False)
    has_any_platform = False

    discord_mention = validate_mention(os.environ.get("ORBIT_DISCORD_MENTION"))

    # Discord Bot
    discord_bot_token = os.environ.get("ORBIT_DISCORD_NOTIFIER_BOT_TOKEN")
    discord_channel = os.environ.get("ORBIT_DISCORD_NOTIFIER_CHANNEL")
    if discord_bot_token and discord_channel:
        config.discord_bot = DiscordBotNotificationConfig(
            enabled=True,
            bot_token=discord_bot_token,
            channel_id=discord_channel,
            mention=discord_mention,
        )
        has_any_platform = True

    # Discord Webhook
    discord_webhook = os.environ.get("ORBIT_DISCORD_WEBHOOK_URL")
    if discord_webhook:
        config.discord = DiscordNotificationConfig(
            enabled=True,
            webhook_url=discord_webhook,
            mention=discord_mention,
        )
        has_any_platform = True

    # Telegram
    telegram_token = (
        os.environ.get("ORBIT_TELEGRAM_BOT_TOKEN")
        or os.environ.get("ORBIT_TELEGRAM_NOTIFIER_BOT_TOKEN")
    )
    telegram_chat_id = (
        os.environ.get("ORBIT_TELEGRAM_CHAT_ID")
        or os.environ.get("ORBIT_TELEGRAM_NOTIFIER_CHAT_ID")
        or os.environ.get("ORBIT_TELEGRAM_NOTIFIER_UID")
    )
    if telegram_token and telegram_chat_id:
        config.telegram = TelegramNotificationConfig(
            enabled=True,
            bot_token=telegram_token,
            chat_id=telegram_chat_id,
        )
        has_any_platform = True

    # Slack
    slack_webhook = os.environ.get("ORBIT_SLACK_WEBHOOK_URL")
    if slack_webhook:
        slack_mention = validate_slack_mention(os.environ.get("ORBIT_SLACK_MENTION"))
        config.slack = SlackNotificationConfig(
            enabled=True,
            webhook_url=slack_webhook,
            mention=slack_mention,
        )
        has_any_platform = True

    if not has_any_platform:
        return None

    config.enabled = True
    return config


def _merge_env_into_file_config(
    file_config: FullNotificationConfig,
    env_config: FullNotificationConfig,
) -> FullNotificationConfig:
    """Merge environment-derived config into file-based config."""
    import dataclasses
    merged = dataclasses.replace(file_config)

    # Discord Bot merge
    if not merged.discord_bot and env_config.discord_bot:
        merged.discord_bot = env_config.discord_bot
    elif merged.discord_bot and env_config.discord_bot:
        merged.discord_bot = DiscordBotNotificationConfig(
            enabled=merged.discord_bot.enabled,
            bot_token=merged.discord_bot.bot_token or env_config.discord_bot.bot_token,
            channel_id=merged.discord_bot.channel_id or env_config.discord_bot.channel_id,
            mention=(
                validate_mention(merged.discord_bot.mention)
                if merged.discord_bot.mention is not None
                else env_config.discord_bot.mention
            ),
        )

    # Discord Webhook merge
    if not merged.discord and env_config.discord:
        merged.discord = env_config.discord
    elif merged.discord and env_config.discord:
        merged.discord = DiscordNotificationConfig(
            enabled=merged.discord.enabled,
            webhook_url=merged.discord.webhook_url or env_config.discord.webhook_url,
            mention=(
                validate_mention(merged.discord.mention)
                if merged.discord.mention is not None
                else env_config.discord.mention
            ),
        )
    elif merged.discord:
        merged.discord = DiscordNotificationConfig(
            enabled=merged.discord.enabled,
            webhook_url=merged.discord.webhook_url,
            mention=validate_mention(merged.discord.mention),
        )

    # Telegram merge
    if not merged.telegram and env_config.telegram:
        merged.telegram = env_config.telegram

    # Slack merge
    if not merged.slack and env_config.slack:
        merged.slack = env_config.slack
    elif merged.slack and env_config.slack:
        merged.slack = SlackNotificationConfig(
            enabled=merged.slack.enabled,
            webhook_url=merged.slack.webhook_url or env_config.slack.webhook_url,
            mention=(
                validate_slack_mention(merged.slack.mention)
                if merged.slack.mention is not None
                else env_config.slack.mention
            ),
        )
    elif merged.slack:
        merged.slack = SlackNotificationConfig(
            enabled=merged.slack.enabled,
            webhook_url=merged.slack.webhook_url,
            mention=validate_slack_mention(merged.slack.mention),
        )

    return merged


def resolve_profile_config(
    notifications: NotificationsBlock,
    profile_name: Optional[str] = None,
) -> Optional[FullNotificationConfig]:
    """
    Resolve a named profile from the notifications block.

    Priority:
      1. Explicit profile_name argument
      2. ORBIT_NOTIFY_PROFILE environment variable
      3. defaultProfile field in config
      4. None (no profile selected -> fall back to flat config)
    """
    profiles = notifications.profiles
    if not profiles:
        return None

    name = (
        profile_name
        or os.environ.get("ORBIT_NOTIFY_PROFILE")
        or notifications.default_profile
    )

    if not name:
        return None

    profile = profiles.get(name)
    if not profile:
        available = ", ".join(profiles.keys())
        warnings.warn(
            f'[notifications] Profile "{name}" not found. Available: {available}'
        )
        return None

    return profile


def list_profiles() -> list[str]:
    """List available profile names from the config file."""
    raw = _read_raw_config()
    if not raw:
        return []
    notifications = raw.get("notifications")
    if not isinstance(notifications, dict):
        return []
    profiles = notifications.get("profiles")
    if not isinstance(profiles, dict):
        return []
    return list(profiles.keys())


def get_active_profile_name() -> Optional[str]:
    """
    Get the active profile name based on resolution priority.
    Returns None if no profile is active (flat config mode).
    """
    env_profile = os.environ.get("ORBIT_NOTIFY_PROFILE")
    if env_profile:
        return env_profile
    raw = _read_raw_config()
    if not raw:
        return None
    notifications = raw.get("notifications")
    if not isinstance(notifications, dict):
        return None
    profiles = notifications.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        return None
    return notifications.get("defaultProfile")


def _has_custom_transport_alias(config: FullNotificationConfig) -> bool:
    cli = config.custom_cli_command
    webhook = config.custom_webhook_command
    cli_enabled = bool(cli and cli.enabled is not False and cli.command)
    webhook_enabled = bool(webhook and webhook.enabled is not False and webhook.url)
    return cli_enabled or webhook_enabled


def _normalize_custom_transport_gate(config: FullNotificationConfig) -> FullNotificationConfig:
    if config.openclaw and config.openclaw.get("enabled"):
        return config
    if not _has_custom_transport_alias(config):
        return config
    import dataclasses
    merged = dataclasses.replace(config)
    merged.openclaw = {"enabled": True}
    return merged


# -- Verbosity helpers -------------------------------------------------------

VALID_VERBOSITY_LEVELS = [v.value for v in VerbosityLevel]
DEFAULT_VERBOSITY = VerbosityLevel.SESSION

VERBOSITY_RANK: dict[VerbosityLevel, int] = {
    VerbosityLevel.MINIMAL: 0,
    VerbosityLevel.SESSION: 1,
    VerbosityLevel.AGENT: 2,
    VerbosityLevel.VERBOSE: 3,
}

EVENT_MIN_VERBOSITY: dict[str, VerbosityLevel] = {
    "session-start": VerbosityLevel.MINIMAL,
    "session-stop": VerbosityLevel.MINIMAL,
    "session-end": VerbosityLevel.MINIMAL,
    "session-idle": VerbosityLevel.SESSION,
    "ask-user-question": VerbosityLevel.AGENT,
}


def get_verbosity(config: Optional[FullNotificationConfig]) -> VerbosityLevel:
    """
    Resolve the effective verbosity level.
    Priority: env var > config field > default ("session").
    """
    env_val = os.environ.get("ORBIT_NOTIFY_VERBOSITY")
    if env_val and env_val in VALID_VERBOSITY_LEVELS:
        return VerbosityLevel(env_val)
    if config and config.verbosity and config.verbosity.value in VALID_VERBOSITY_LEVELS:
        return config.verbosity
    return DEFAULT_VERBOSITY


def is_event_allowed_by_verbosity(verbosity: VerbosityLevel, event: str) -> bool:
    """Check whether a given event is allowed at the specified verbosity level."""
    required = EVENT_MIN_VERBOSITY.get(event, VerbosityLevel.SESSION)
    return VERBOSITY_RANK[verbosity] >= VERBOSITY_RANK[required]


def should_include_tmux_tail(verbosity: VerbosityLevel) -> bool:
    """Whether the given verbosity level should include tmux tail output."""
    return VERBOSITY_RANK[verbosity] >= VERBOSITY_RANK[VerbosityLevel.SESSION]


def is_event_enabled(config: FullNotificationConfig, event: str) -> bool:
    """Check whether an event should trigger notifications."""
    if not config.enabled:
        return False

    verbosity = get_verbosity(config)
    if not is_event_allowed_by_verbosity(verbosity, event):
        return False

    event_config = (config.events or {}).get(event)

    if event_config and event_config.enabled is False:
        return False

    def _any_platform_enabled() -> bool:
        return bool(
            (config.discord and config.discord.enabled)
            or (config.discord_bot and config.discord_bot.enabled)
            or (config.telegram and config.telegram.enabled)
            or (config.slack and config.slack.enabled)
            or (config.webhook and config.webhook.enabled)
            or (config.openclaw and config.openclaw.get("enabled"))
            or _has_custom_transport_alias(config)
        )

    if not event_config:
        return _any_platform_enabled()

    if (
        (event_config.discord and event_config.discord.enabled)
        or (event_config.discord_bot and event_config.discord_bot.enabled)
        or (event_config.telegram and event_config.telegram.enabled)
        or (event_config.slack and event_config.slack.enabled)
        or (event_config.webhook and event_config.webhook.enabled)
    ):
        return True

    return _any_platform_enabled()


def get_enabled_platforms(
    config: FullNotificationConfig,
    event: str,
) -> list[NotificationPlatform]:
    """Get the list of platforms enabled for a given event."""
    if not config.enabled:
        return []

    platforms: list[NotificationPlatform] = []
    event_config = (config.events or {}).get(event)

    if event_config and event_config.enabled is False:
        return []

    def _check_platform(platform: NotificationPlatform) -> None:
        # Check event-level override first
        if event_config:
            attr_name = platform.value.replace("-", "_")
            event_plat = getattr(event_config, attr_name, None)
            if event_plat is not None and hasattr(event_plat, "enabled"):
                if event_plat.enabled:
                    platforms.append(platform)
                return

        # Fall back to top-level
        attr_name = platform.value.replace("-", "_")
        top_level = getattr(config, attr_name, None)
        if top_level is not None and hasattr(top_level, "enabled") and top_level.enabled:
            platforms.append(platform)

    _check_platform(NotificationPlatform.DISCORD)
    _check_platform(NotificationPlatform.DISCORD_BOT)
    _check_platform(NotificationPlatform.TELEGRAM)
    _check_platform(NotificationPlatform.SLACK)
    _check_platform(NotificationPlatform.WEBHOOK)

    return platforms


def get_notification_config(
    profile_name: Optional[str] = None,
) -> Optional[FullNotificationConfig]:
    """
    Get the resolved notification configuration.

    Reads from config file, merges environment variables,
    handles profiles and legacy migration.
    """
    raw = _read_raw_config()

    if raw:
        notifications_raw = raw.get("notifications")
        if isinstance(notifications_raw, dict):
            # Try profile resolution first
            # (simplified: real implementation would deserialize into NotificationsBlock)
            profiles = notifications_raw.get("profiles")
            if profiles and isinstance(profiles, dict) and profile_name:
                profile = profiles.get(profile_name)
                if profile:
                    # Would deserialize and merge env here
                    pass

            enabled = notifications_raw.get("enabled")
            if not isinstance(enabled, bool):
                env_config = build_config_from_env()
                if env_config:
                    return env_config
                return None

            # Build a FullNotificationConfig from the raw dict
            config = FullNotificationConfig(enabled=enabled)

            # Populate platform configs from raw
            discord_raw = notifications_raw.get("discord")
            if isinstance(discord_raw, dict):
                config.discord = DiscordNotificationConfig(
                    enabled=discord_raw.get("enabled", False),
                    webhook_url=discord_raw.get("webhookUrl", ""),
                    mention=discord_raw.get("mention"),
                )

            discord_bot_raw = notifications_raw.get("discord-bot")
            if isinstance(discord_bot_raw, dict):
                config.discord_bot = DiscordBotNotificationConfig(
                    enabled=discord_bot_raw.get("enabled", False),
                    bot_token=discord_bot_raw.get("botToken"),
                    channel_id=discord_bot_raw.get("channelId"),
                    mention=discord_bot_raw.get("mention"),
                )

            telegram_raw = notifications_raw.get("telegram")
            if isinstance(telegram_raw, dict):
                config.telegram = TelegramNotificationConfig(
                    enabled=telegram_raw.get("enabled", False),
                    bot_token=telegram_raw.get("botToken", ""),
                    chat_id=telegram_raw.get("chatId", ""),
                )

            slack_raw = notifications_raw.get("slack")
            if isinstance(slack_raw, dict):
                config.slack = SlackNotificationConfig(
                    enabled=slack_raw.get("enabled", False),
                    webhook_url=slack_raw.get("webhookUrl", ""),
                    mention=slack_raw.get("mention"),
                )

            env_config = build_config_from_env()
            if env_config:
                return _normalize_custom_transport_gate(
                    _merge_env_into_file_config(config, env_config)
                )

            return _normalize_custom_transport_gate(config)

    # Try env-only config
    env_config = build_config_from_env()
    if env_config:
        return env_config

    # Legacy migration
    if raw:
        migrated = _migrate_stop_hook_callbacks(raw)
        if migrated:
            return migrated

    return None
