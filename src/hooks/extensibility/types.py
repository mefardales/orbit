"""
Hook extensibility type definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Literal, Optional, Protocol

HookSchemaVersion = Literal["1"]
HookEventSource = Literal["native", "derived"]

HookEventName = str  # Union of known names + arbitrary strings

# Known event names for documentation:
# "session-start", "session-end", "session-idle", "turn-complete",
# "blocked", "finished", "failed", "retry-needed", "pr-created",
# "test-started", "test-finished", "test-failed", "handoff-needed",
# "needs-input", "pre-tool-use", "post-tool-use"


@dataclass
class HookEventEnvelope:
    """Envelope wrapping a hook event for dispatch."""

    schema_version: HookSchemaVersion = "1"
    event: str = ""
    timestamp: str = ""
    source: HookEventSource = "native"
    context: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    turn_id: Optional[str] = None
    mode: Optional[str] = None
    confidence: Optional[float] = None
    parser_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "event": self.event,
            "timestamp": self.timestamp,
            "source": self.source,
            "context": self.context,
        }
        if self.session_id:
            d["session_id"] = self.session_id
        if self.thread_id:
            d["thread_id"] = self.thread_id
        if self.turn_id:
            d["turn_id"] = self.turn_id
        if self.mode:
            d["mode"] = self.mode
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.parser_reason:
            d["parser_reason"] = self.parser_reason
        return d


@dataclass
class HookPluginDescriptor:
    """Descriptor for a discovered hook plugin."""

    id: str
    name: str
    file: str
    path: str
    file_path: str
    file_name: str
    valid: bool = True
    reason: Optional[str] = None


HookPluginDispatchStatus = Literal[
    "ok", "timeout", "error", "invalid_export",
    "runner_error", "spawn_failed", "runner_missing",
    "skipped_team_worker", "skipped",
]


@dataclass
class HookPluginDispatchResult:
    """Result of dispatching an event to a single plugin."""

    plugin: str
    path: str
    ok: bool
    duration_ms: float = 0.0
    plugin_id: Optional[str] = None
    file: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    error: Optional[str] = None
    output: Any = None
    exit_code: Optional[int] = None
    skipped: bool = False


@dataclass
class HookDispatchResult:
    """Result of dispatching an event to all plugins."""

    enabled: bool
    event: str
    source: Optional[HookEventSource] = None
    plugin_count: int = 0
    reason: Optional[str] = None
    results: List[HookPluginDispatchResult] = field(default_factory=list)


@dataclass
class HookDispatchOptions:
    """Options for hook event dispatch."""

    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    timeout_ms: Optional[int] = None
    allow_in_team_worker: bool = False
    allow_team_worker_side_effects: bool = False
    side_effects_enabled: Optional[bool] = None
    enabled: Optional[bool] = None


@dataclass
class HookValidateOptions:
    """Options for hook validation."""

    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    timeout_ms: Optional[int] = None
