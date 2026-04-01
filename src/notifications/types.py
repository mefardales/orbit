"""
Notification System Types

Defines types for the multi-platform lifecycle notification system.
Supports Discord, Telegram, Slack, and generic webhooks across
session lifecycle events (start, stop, end, ask-user-question).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NotificationEvent(str, Enum):
    """Events that can trigger notifications."""
    SESSION_START = "session-start"
    SESSION_STOP = "session-stop"
    SESSION_END = "session-end"
    SESSION_IDLE = "session-idle"
    ASK_USER_QUESTION = "ask-user-question"


class VerbosityLevel(str, Enum):
    """
    Verbosity levels for notification filtering.

    - verbose: all text/tool call output
    - agent:   per-agent-call events (includes ask-user-question)
    - session: start/idle/stop/end + tmux tail snippet [DEFAULT]
    - minimal: start/stop/end only, no idle, no tmux tail
    """
    VERBOSE = "verbose"
    AGENT = "agent"
    SESSION = "session"
    MINIMAL = "minimal"


class NotificationPlatform(str, Enum):
    """Supported notification platforms."""
    DISCORD = "discord"
    DISCORD_BOT = "discord-bot"
    TELEGRAM = "telegram"
    SLACK = "slack"
    WEBHOOK = "webhook"


@dataclass
class DiscordNotificationConfig:
    """Discord webhook configuration."""
    enabled: bool = False
    webhook_url: str = ""
    username: Optional[str] = None
    mention: Optional[str] = None


@dataclass
class DiscordBotNotificationConfig:
    """Discord Bot API configuration (bot token + channel ID)."""
    enabled: bool = False
    bot_token: Optional[str] = None
    channel_id: Optional[str] = None
    mention: Optional[str] = None


@dataclass
class TelegramNotificationConfig:
    """Telegram platform configuration."""
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    parse_mode: str = "Markdown"  # "Markdown" or "HTML"


@dataclass
class SlackNotificationConfig:
    """Slack platform configuration."""
    enabled: bool = False
    webhook_url: str = ""
    channel: Optional[str] = None
    username: Optional[str] = None
    mention: Optional[str] = None


@dataclass
class WebhookNotificationConfig:
    """Generic webhook configuration."""
    enabled: bool = False
    url: str = ""
    headers: Optional[dict[str, str]] = None
    method: str = "POST"  # "POST" or "PUT"


@dataclass
class CustomWebhookCommandConfig:
    """Generic custom webhook command config."""
    enabled: Optional[bool] = None
    url: str = ""
    headers: Optional[dict[str, str]] = None
    method: str = "POST"
    timeout: Optional[int] = None


@dataclass
class CustomCliCommandConfig:
    """Generic custom CLI command config."""
    enabled: Optional[bool] = None
    command: str = ""
    timeout: Optional[int] = None


# PlatformConfig is a union type in TS; in Python use Union from typing.
from typing import Union
PlatformConfig = Union[
    DiscordNotificationConfig,
    DiscordBotNotificationConfig,
    TelegramNotificationConfig,
    SlackNotificationConfig,
    WebhookNotificationConfig,
]


@dataclass
class EventNotificationConfig:
    """Per-event notification configuration."""
    enabled: bool = True
    message_template: Optional[str] = None
    discord: Optional[DiscordNotificationConfig] = None
    discord_bot: Optional[DiscordBotNotificationConfig] = None
    telegram: Optional[TelegramNotificationConfig] = None
    slack: Optional[SlackNotificationConfig] = None
    webhook: Optional[WebhookNotificationConfig] = None


@dataclass
class FullNotificationConfig:
    """Top-level notification configuration (stored in .orbit-config.json)."""
    enabled: bool = False
    verbosity: Optional[VerbosityLevel] = None

    discord: Optional[DiscordNotificationConfig] = None
    discord_bot: Optional[DiscordBotNotificationConfig] = None
    telegram: Optional[TelegramNotificationConfig] = None
    slack: Optional[SlackNotificationConfig] = None
    webhook: Optional[WebhookNotificationConfig] = None

    openclaw: Optional[dict[str, bool]] = None  # e.g. {"enabled": True}
    custom_webhook_command: Optional[CustomWebhookCommandConfig] = None
    custom_cli_command: Optional[CustomCliCommandConfig] = None

    events: Optional[dict[str, EventNotificationConfig]] = None


@dataclass
class FullNotificationPayload:
    """Payload sent with each notification."""
    event: NotificationEvent
    session_id: str
    message: str = ""
    timestamp: str = ""
    tmux_session: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    modes_used: Optional[list[str]] = None
    context_summary: Optional[str] = None
    duration_ms: Optional[int] = None
    agents_spawned: Optional[int] = None
    agents_completed: Optional[int] = None
    reason: Optional[str] = None
    active_mode: Optional[str] = None
    iteration: Optional[int] = None
    max_iterations: Optional[int] = None
    question: Optional[str] = None
    incomplete_tasks: Optional[int] = None
    tmux_pane_id: Optional[str] = None
    tmux_tail: Optional[str] = None
    agent_name: Optional[str] = None
    agent_type: Optional[str] = None


@dataclass
class NotificationResult:
    """Result of a notification send attempt."""
    platform: NotificationPlatform
    success: bool
    error: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class DispatchResult:
    """Result of dispatching notifications for an event."""
    event: NotificationEvent
    results: list[NotificationResult] = field(default_factory=list)
    any_success: bool = False


@dataclass
class NotificationProfilesConfig:
    """Named notification profiles configuration."""
    enabled: bool = False
    default_profile: Optional[str] = None
    profiles: dict[str, FullNotificationConfig] = field(default_factory=dict)


@dataclass
class NotificationsBlock(FullNotificationConfig):
    """Top-level notifications block (supports both flat and profiled config)."""
    default_profile: Optional[str] = None
    profiles: Optional[dict[str, FullNotificationConfig]] = None


@dataclass
class ReplyConfig:
    """Reply injection configuration."""
    enabled: bool = False
    poll_interval_ms: int = 3000
    max_message_length: int = 500
    rate_limit_per_minute: int = 10
    include_prefix: bool = True
    authorized_discord_user_ids: list[str] = field(default_factory=list)
