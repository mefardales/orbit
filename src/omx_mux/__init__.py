"""omx-mux: Terminal multiplexer abstraction layer."""

from .types import (
    MUX_OPERATION_NAMES,
    MUX_TARGET_KINDS,
    MuxTarget,
    SubmitPolicy,
    InputEnvelope,
    InjectionPreflight,
    PaneReadinessReason,
    PaneReadiness,
    DeliveryConfirmation,
    ConfirmationPolicy,
    DeliveryAttempt,
    MuxOperation,
    MuxOutcome,
    MuxError,
    MuxAdapter,
    describe_operation,
)
from .tmux import TmuxAdapter, build_capture_pane_args

__all__ = [
    "MUX_OPERATION_NAMES",
    "MUX_TARGET_KINDS",
    "MuxTarget",
    "SubmitPolicy",
    "InputEnvelope",
    "InjectionPreflight",
    "PaneReadinessReason",
    "PaneReadiness",
    "DeliveryConfirmation",
    "ConfirmationPolicy",
    "DeliveryAttempt",
    "MuxOperation",
    "MuxOutcome",
    "MuxError",
    "MuxAdapter",
    "describe_operation",
    "TmuxAdapter",
    "build_capture_pane_args",
]


def canonical_contract_summary() -> str:
    return (
        f"mux-operations={', '.join(MUX_OPERATION_NAMES)}\n"
        f"mux-target-kinds={', '.join(MUX_TARGET_KINDS)}\n"
        f"submit-policy={SubmitPolicy.enter(2, 100)}\n"
        f"readiness={PaneReadinessReason.OK}\n"
        f"confirmation={DeliveryConfirmation.CONFIRMED}\n"
        f"adapter=tmux"
    )
