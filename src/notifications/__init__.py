"""
Notification System - Public API

Multi-platform lifecycle notifications for oh-my-codex.
Sends notifications to Discord, Telegram, Slack, and generic webhooks
on session lifecycle events.

Usage:
    from notifications import notify_lifecycle
    await notify_lifecycle("session-start", session_id="abc", project_path="/my/project")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .types import (
    DiscordBotNotificationConfig,
    DiscordNotificationConfig,
    DispatchResult,
    EventNotificationConfig,
    FullNotificationConfig,
    FullNotificationPayload,
    NotificationEvent,
    NotificationPlatform,
    NotificationProfilesConfig,
    NotificationResult,
    NotificationsBlock,
    ReplyConfig,
    SlackNotificationConfig,
    TelegramNotificationConfig,
    VerbosityLevel,
    WebhookNotificationConfig,
)
from .config import (
    get_active_profile_name,
    get_enabled_platforms,
    get_notification_config,
    get_verbosity,
    is_event_allowed_by_verbosity,
    is_event_enabled,
    list_profiles,
    resolve_profile_config,
    should_include_tmux_tail,
)
from .dispatcher import (
    dispatch_notifications,
    send_discord,
    send_discord_bot,
    send_slack,
    send_telegram,
    send_webhook,
)
from .formatter import (
    format_ask_user_question,
    format_notification,
    format_session_end,
    format_session_idle,
    format_session_start,
    format_session_stop,
)
from .tmux_notify import (
    capture_tmux_pane,
    format_tmux_info,
    get_current_tmux_pane_id,
    get_current_tmux_session,
    get_team_tmux_sessions,
)

# Legacy notifier re-exports
from .notifier import notify, load_notification_config, NotificationConfig, NotificationPayload

logger = logging.getLogger(__name__)


async def notify_lifecycle(
    event: str,
    *,
    session_id: str,
    timestamp: Optional[str] = None,
    tmux_session: Optional[str] = None,
    tmux_pane_id: Optional[str] = None,
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    modes_used: Optional[list[str]] = None,
    context_summary: Optional[str] = None,
    duration_ms: Optional[int] = None,
    agents_spawned: Optional[int] = None,
    agents_completed: Optional[int] = None,
    reason: Optional[str] = None,
    active_mode: Optional[str] = None,
    iteration: Optional[int] = None,
    max_iterations: Optional[int] = None,
    question: Optional[str] = None,
    incomplete_tasks: Optional[int] = None,
    message: Optional[str] = None,
    tmux_tail: Optional[str] = None,
    profile_name: Optional[str] = None,
) -> Optional[DispatchResult]:
    """
    High-level notification function for lifecycle events.

    Reads config, checks if the event is enabled, formats the message,
    and dispatches to all configured platforms. Non-blocking, swallows errors.
    """
    try:
        config = get_notification_config(profile_name)
        if not config or not is_event_enabled(config, event):
            return None

        # Build notification event enum
        try:
            notification_event = NotificationEvent(event)
        except ValueError:
            return None

        payload = FullNotificationPayload(
            event=notification_event,
            session_id=session_id,
            message="",
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            tmux_session=tmux_session or get_current_tmux_session(),
            tmux_pane_id=tmux_pane_id or get_current_tmux_pane_id(),
            project_path=project_path,
            project_name=project_name or (Path(project_path).name if project_path else None),
            modes_used=modes_used,
            context_summary=context_summary,
            duration_ms=duration_ms,
            agents_spawned=agents_spawned,
            agents_completed=agents_completed,
            reason=reason,
            active_mode=active_mode,
            iteration=iteration,
            max_iterations=max_iterations,
            question=question,
            incomplete_tasks=incomplete_tasks,
        )

        # Capture tmux tail for session+ verbosity on idle/stop/end events
        verbosity = get_verbosity(config)
        if (
            should_include_tmux_tail(verbosity)
            and not tmux_tail
            and event in ("session-idle", "session-stop", "session-end")
        ):
            payload.tmux_tail = capture_tmux_pane(payload.tmux_pane_id)
        else:
            payload.tmux_tail = tmux_tail

        payload.message = message or format_notification(payload)

        result = await dispatch_notifications(config, event, payload)
        return result

    except Exception as e:
        logger.error("[notifications] Error: %s", e)
        return None


__all__ = [
    # Types
    "NotificationEvent",
    "NotificationPlatform",
    "VerbosityLevel",
    "DiscordNotificationConfig",
    "DiscordBotNotificationConfig",
    "TelegramNotificationConfig",
    "SlackNotificationConfig",
    "WebhookNotificationConfig",
    "EventNotificationConfig",
    "FullNotificationConfig",
    "FullNotificationPayload",
    "NotificationResult",
    "DispatchResult",
    "NotificationProfilesConfig",
    "NotificationsBlock",
    "ReplyConfig",
    # Config
    "get_notification_config",
    "is_event_enabled",
    "get_enabled_platforms",
    "get_verbosity",
    "is_event_allowed_by_verbosity",
    "should_include_tmux_tail",
    "resolve_profile_config",
    "list_profiles",
    "get_active_profile_name",
    # Dispatcher
    "dispatch_notifications",
    "send_discord",
    "send_discord_bot",
    "send_telegram",
    "send_slack",
    "send_webhook",
    # Formatter
    "format_notification",
    "format_session_start",
    "format_session_stop",
    "format_session_end",
    "format_session_idle",
    "format_ask_user_question",
    # Tmux
    "get_current_tmux_session",
    "get_current_tmux_pane_id",
    "get_team_tmux_sessions",
    "format_tmux_info",
    "capture_tmux_pane",
    # Legacy
    "notify",
    "load_notification_config",
    "NotificationConfig",
    "NotificationPayload",
    # High-level
    "notify_lifecycle",
]
