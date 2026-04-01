"""
Hook event construction utilities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .types import HookEventEnvelope, HookEventSource

DERIVED_EVENTS = {"needs-input", "pre-tool-use", "post-tool-use"}


def _clamp_confidence(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    if not isinstance(value, float) and not isinstance(value, int):
        return None
    v = float(value)
    if v != v:  # NaN check
        return None
    if v < 0:
        return 0.0
    if v > 1:
        return 1.0
    return v


def is_derived_event_name(event: str) -> bool:
    """Check if an event name is a derived (non-native) event."""
    return event in DERIVED_EVENTS


def build_hook_event(
    event: str,
    source: Optional[HookEventSource] = None,
    timestamp: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    mode: Optional[str] = None,
    confidence: Optional[float] = None,
    parser_reason: Optional[str] = None,
) -> HookEventEnvelope:
    """Build a hook event envelope with proper defaults."""
    if source is None:
        source = "derived" if is_derived_event_name(event) else "native"

    clamped_confidence = _clamp_confidence(confidence)

    envelope = HookEventEnvelope(
        schema_version="1",
        event=event,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        source=source,
        context=context if isinstance(context, dict) else {},
    )

    if session_id:
        envelope.session_id = session_id
    if thread_id:
        envelope.thread_id = thread_id
    if turn_id:
        envelope.turn_id = turn_id
    if mode:
        envelope.mode = mode

    if source == "derived":
        envelope.confidence = clamped_confidence if clamped_confidence is not None else 0.5
        if parser_reason:
            envelope.parser_reason = parser_reason

    return envelope


def build_native_hook_event(
    event: str,
    context: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    mode: Optional[str] = None,
) -> HookEventEnvelope:
    """Build a native (high-confidence) hook event."""
    return build_hook_event(
        event=event,
        source="native",
        context=context or {},
        session_id=session_id,
        thread_id=thread_id,
        turn_id=turn_id,
        mode=mode,
    )


def build_derived_hook_event(
    event: str,
    context: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    mode: Optional[str] = None,
    confidence: Optional[float] = None,
    parser_reason: Optional[str] = None,
) -> HookEventEnvelope:
    """Build a derived (parsed/inferred) hook event."""
    return build_hook_event(
        event=event,
        source="derived",
        context=context or {},
        session_id=session_id,
        thread_id=thread_id,
        turn_id=turn_id,
        mode=mode,
        confidence=confidence,
        parser_reason=parser_reason,
    )
