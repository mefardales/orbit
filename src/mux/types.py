"""Types for the mux abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

MUX_OPERATION_NAMES = [
    "resolve-target",
    "send-input",
    "capture-tail",
    "inspect-liveness",
    "attach",
    "detach",
]

MUX_TARGET_KINDS = ["delivery-handle", "detached"]


# ---------------------------------------------------------------------------
# MuxTarget
# ---------------------------------------------------------------------------

class MuxTarget:
    """Tagged union: DeliveryHandle(str) | Detached."""

    def __init__(self, kind: str, handle: Optional[str] = None):
        self._kind = kind
        self._handle = handle

    @classmethod
    def delivery_handle(cls, handle: str) -> MuxTarget:
        return cls("delivery-handle", handle)

    @classmethod
    def detached(cls) -> MuxTarget:
        return cls("detached")

    @property
    def is_delivery_handle(self) -> bool:
        return self._kind == "delivery-handle"

    @property
    def handle(self) -> Optional[str]:
        return self._handle

    def __repr__(self) -> str:
        if self._kind == "delivery-handle":
            return f"delivery-handle({self._handle})"
        return "detached"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MuxTarget):
            return NotImplemented
        return self._kind == other._kind and self._handle == other._handle


# ---------------------------------------------------------------------------
# SubmitPolicy
# ---------------------------------------------------------------------------

class SubmitPolicy:
    """Tagged union: NONE | Enter(presses, delay_ms)."""

    def __init__(self, kind: str, presses: int = 0, delay_ms: int = 0):
        self._kind = kind
        self._presses = max(presses, 1) if kind == "enter" else 0
        self._delay_ms = delay_ms

    NONE: SubmitPolicy  # set below

    @classmethod
    def enter(cls, presses: int = 1, delay_ms: int = 0) -> SubmitPolicy:
        return cls("enter", presses, delay_ms)

    @property
    def presses(self) -> int:
        return self._presses

    @property
    def delay_ms(self) -> int:
        return self._delay_ms

    @property
    def is_enter(self) -> bool:
        return self._kind == "enter"

    def __repr__(self) -> str:
        if self._kind == "enter":
            return f"enter(presses={self._presses}, delay_ms={self._delay_ms})"
        return "none"

    def __str__(self) -> str:
        return self.__repr__()


SubmitPolicy.NONE = SubmitPolicy("none")


# ---------------------------------------------------------------------------
# InputEnvelope
# ---------------------------------------------------------------------------

@dataclass
class InputEnvelope:
    literal_text: str
    submit: SubmitPolicy
    replace_newlines_with_spaces: bool = True

    @classmethod
    def new(cls, literal_text: str, submit: SubmitPolicy) -> InputEnvelope:
        return cls(literal_text=literal_text, submit=submit)

    def normalized_text(self) -> str:
        if self.replace_newlines_with_spaces:
            return self.literal_text.replace("\r", " ").replace("\n", " ")
        return self.literal_text


# ---------------------------------------------------------------------------
# InjectionPreflight
# ---------------------------------------------------------------------------

@dataclass
class InjectionPreflight:
    skip_if_scrolling: bool = True
    require_running_agent: bool = True
    require_ready: bool = True
    require_idle: bool = True
    capture_lines: int = 80


# ---------------------------------------------------------------------------
# PaneReadinessReason
# ---------------------------------------------------------------------------

class PaneReadinessReason(Enum):
    OK = "ok"
    MISSING_TARGET = "missing_target"
    SCROLL_ACTIVE = "scroll_active"
    PANE_RUNNING_SHELL = "pane_running_shell"
    PANE_HAS_ACTIVE_TASK = "pane_has_active_task"
    PANE_NOT_READY = "pane_not_ready"

    def __str__(self) -> str:
        return self.value


class PaneReadinessReasonResolutionFailed:
    """Separate class for the parameterized variant."""

    def __init__(self, reason: str):
        self.reason = reason

    def __str__(self) -> str:
        return f"target_resolution_failed({self.reason})"


# ---------------------------------------------------------------------------
# PaneReadiness
# ---------------------------------------------------------------------------

@dataclass
class PaneReadiness:
    reason: PaneReadinessReason | PaneReadinessReasonResolutionFailed
    pane_target: Optional[str] = None
    pane_current_command: Optional[str] = None
    pane_capture: Optional[str] = None

    @classmethod
    def ok(cls, pane_target: str) -> PaneReadiness:
        return cls(reason=PaneReadinessReason.OK, pane_target=pane_target)


# ---------------------------------------------------------------------------
# DeliveryConfirmation
# ---------------------------------------------------------------------------

class DeliveryConfirmation(Enum):
    CONFIRMED = "Confirmed"
    CONFIRMED_ACTIVE_TASK = "ConfirmedActiveTask"
    UNCONFIRMED = "Unconfirmed"

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# ConfirmationPolicy
# ---------------------------------------------------------------------------

@dataclass
class ConfirmationPolicy:
    narrow_capture_lines: int = 8
    wide_capture_lines: int = 80
    verify_delay_ms: int = 250
    verify_rounds: int = 3
    allow_active_task_confirmation: bool = True
    require_ready_for_worker_targets: bool = True
    non_empty_tail_lines: int = 24
    retry_submit_without_retyping: bool = True


# ---------------------------------------------------------------------------
# DeliveryAttempt
# ---------------------------------------------------------------------------

@dataclass
class DeliveryAttempt:
    pane_target: str
    input: InputEnvelope
    typed_prompt: bool
    confirmation: DeliveryConfirmation


# ---------------------------------------------------------------------------
# MuxOperation
# ---------------------------------------------------------------------------

@dataclass
class MuxOperation:
    """Tagged union for mux operations."""
    kind: str
    target: Optional[MuxTarget] = None
    envelope: Optional[InputEnvelope] = None
    visible_lines: Optional[int] = None

    @classmethod
    def resolve_target(cls, target: MuxTarget) -> MuxOperation:
        return cls(kind="resolve-target", target=target)

    @classmethod
    def send_input(cls, target: MuxTarget, envelope: InputEnvelope) -> MuxOperation:
        return cls(kind="send-input", target=target, envelope=envelope)

    @classmethod
    def capture_tail(cls, target: MuxTarget, visible_lines: int) -> MuxOperation:
        return cls(kind="capture-tail", target=target, visible_lines=visible_lines)

    @classmethod
    def inspect_liveness(cls, target: MuxTarget) -> MuxOperation:
        return cls(kind="inspect-liveness", target=target)

    @classmethod
    def attach(cls, target: MuxTarget) -> MuxOperation:
        return cls(kind="attach", target=target)

    @classmethod
    def detach(cls, target: MuxTarget) -> MuxOperation:
        return cls(kind="detach", target=target)


# ---------------------------------------------------------------------------
# MuxOutcome
# ---------------------------------------------------------------------------

@dataclass
class MuxOutcome:
    kind: str
    resolved_handle: Optional[str] = None
    bytes_written: Optional[int] = None
    visible_lines: Optional[int] = None
    body: Optional[str] = None
    alive: Optional[bool] = None
    handle: Optional[str] = None

    @classmethod
    def target_resolved(cls, resolved_handle: str) -> MuxOutcome:
        return cls(kind="target-resolved", resolved_handle=resolved_handle)

    @classmethod
    def input_accepted(cls, bytes_written: int) -> MuxOutcome:
        return cls(kind="input-accepted", bytes_written=bytes_written)

    @classmethod
    def tail_captured(cls, visible_lines: int, body: str) -> MuxOutcome:
        return cls(kind="tail-captured", visible_lines=visible_lines, body=body)

    @classmethod
    def liveness_checked(cls, alive: bool) -> MuxOutcome:
        return cls(kind="liveness-checked", alive=alive)

    @classmethod
    def attached(cls, handle: str) -> MuxOutcome:
        return cls(kind="attached", handle=handle)

    @classmethod
    def detached(cls, handle: str) -> MuxOutcome:
        return cls(kind="detached", handle=handle)


# ---------------------------------------------------------------------------
# MuxError
# ---------------------------------------------------------------------------

class MuxError(Exception):
    """Mux-layer error with a tagged kind."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind

    @classmethod
    def unsupported(cls, message: str) -> MuxError:
        return cls("unsupported", message)

    @classmethod
    def invalid_target(cls, message: str) -> MuxError:
        return cls("invalid_target", message)

    @classmethod
    def adapter_failed(cls, message: str) -> MuxError:
        return cls("adapter_failed", message)


# ---------------------------------------------------------------------------
# MuxAdapter (abstract base)
# ---------------------------------------------------------------------------

class MuxAdapter(ABC):
    @abstractmethod
    def adapter_name(self) -> str: ...

    @abstractmethod
    def execute(self, operation: MuxOperation) -> MuxOutcome: ...


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def describe_operation(operation: MuxOperation) -> str:
    return operation.kind
