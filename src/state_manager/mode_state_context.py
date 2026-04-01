"""Mode runtime context: captures tmux pane info into mode state."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional


def capture_tmux_pane_from_env(env: Optional[dict[str, str]] = None) -> Optional[str]:
    """Return the TMUX_PANE value from environment, or None."""
    if env is None:
        env = dict(os.environ)
    value = env.get("TMUX_PANE")
    if not isinstance(value, str):
        return None
    pane = value.strip()
    return pane if pane else None


def _has_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def with_mode_runtime_context(
    existing: dict[str, Any],
    next_state: dict[str, Any],
    *,
    env: Optional[dict[str, str]] = None,
    now_iso: Optional[str] = None,
) -> dict[str, Any]:
    """Enrich next_state with tmux pane context when transitioning to active.

    Args:
        existing: The previous mode state dict.
        next_state: The new mode state dict (mutated in place and returned).
        env: Environment variables dict. Defaults to os.environ.
        now_iso: ISO timestamp override for testing.

    Returns:
        next_state with tmux_pane_id/tmux_pane_set_at set if applicable.
    """
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat()

    was_active = existing.get("active") is True
    is_active = next_state.get("active") is True
    has_pane = _has_non_empty_string(next_state.get("tmux_pane_id"))

    if is_active and (not was_active or not has_pane):
        pane = capture_tmux_pane_from_env(env)
        if pane:
            next_state["tmux_pane_id"] = pane
            if not _has_non_empty_string(next_state.get("tmux_pane_set_at")):
                next_state["tmux_pane_set_at"] = now_iso

    return next_state
