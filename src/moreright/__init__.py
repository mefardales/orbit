"""Permission escalation subsystem for orbit."""

from .escalation import PermissionEscalation
from .policies import EscalationPolicy, DEFAULT_POLICY, STRICT_POLICY

__all__ = [
    "PermissionEscalation",
    "EscalationPolicy",
    "DEFAULT_POLICY",
    "STRICT_POLICY",
]
