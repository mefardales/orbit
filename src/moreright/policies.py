"""Escalation policies governing what permissions may be granted."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class EscalationPolicy:
    """Defines the rules for permission escalation."""

    name: str
    # Maximum tool-access level that can be escalated to.
    max_tool_access: str = "write_all"
    # Whether escalation can be auto-approved (no human in the loop).
    allow_auto_approve: bool = False
    # Which permissions are never allowed, regardless of approval.
    deny_list: frozenset[str] = frozenset()
    # Which permissions are always allowed without approval.
    allow_list: frozenset[str] = frozenset()
    # Maximum number of escalations per session before a hard block.
    max_escalations_per_session: int = 10
    # Whether to log escalation requests to the audit trail.
    audit: bool = True
    # Timeout in seconds before an unanswered escalation request is denied.
    request_timeout: float = 120.0
    # Human readable description of the policy.
    description: str = ""

    def is_explicitly_denied(self, permission: str) -> bool:
        """Return ``True`` if *permission* is on the deny list."""
        return permission in self.deny_list

    def is_explicitly_allowed(self, permission: str) -> bool:
        """Return ``True`` if *permission* is on the pre-approved allow list."""
        return permission in self.allow_list

    def check(self, permission: str) -> str:
        """Return ``"allow"``, ``"deny"``, or ``"ask"``."""
        if self.is_explicitly_denied(permission):
            return "deny"
        if self.is_explicitly_allowed(permission):
            return "allow"
        return "ask"


DEFAULT_POLICY = EscalationPolicy(
    name="default",
    max_tool_access="write_all",
    allow_auto_approve=False,
    deny_list=frozenset({"rm_rf", "format_disk", "sudo"}),
    allow_list=frozenset({"read_file", "list_dir", "search"}),
    max_escalations_per_session=10,
    audit=True,
    request_timeout=120.0,
    description="Balanced policy: common reads auto-allowed, destructive ops blocked.",
)

STRICT_POLICY = EscalationPolicy(
    name="strict",
    max_tool_access="read_only",
    allow_auto_approve=False,
    deny_list=frozenset({"rm_rf", "format_disk", "sudo", "write_file", "exec"}),
    allow_list=frozenset(),
    max_escalations_per_session=3,
    audit=True,
    request_timeout=60.0,
    description="Strict policy: everything requires approval, most writes denied.",
)
