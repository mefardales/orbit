"""Permission escalation request lifecycle."""

from __future__ import annotations

import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .policies import EscalationPolicy, DEFAULT_POLICY

logger = logging.getLogger(__name__)


class EscalationStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class EscalationRequest:
    """A single request for elevated permissions."""

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    permission: str = ""
    reason: str = ""
    requester: str = ""
    status: EscalationStatus = EscalationStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolver: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PermissionEscalation:
    """Manages the lifecycle of permission escalation requests."""

    def __init__(
        self,
        policy: Optional[EscalationPolicy] = None,
        on_request: Optional[Callable[[EscalationRequest], None]] = None,
    ) -> None:
        self.policy = policy or DEFAULT_POLICY
        self._on_request = on_request
        self._requests: dict[str, EscalationRequest] = {}
        self._session_count: int = 0

    # -- public API ------------------------------------------------------------

    def request(
        self,
        permission: str,
        *,
        reason: str = "",
        requester: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> EscalationRequest:
        """Create a new escalation request.

        Returns an :class:`EscalationRequest` whose *status* is already
        resolved if the policy auto-allows or denies the permission.
        """
        verdict = self.policy.check(permission)

        req = EscalationRequest(
            permission=permission,
            reason=reason,
            requester=requester,
            metadata=metadata or {},
        )

        if verdict == "deny":
            req.status = EscalationStatus.DENIED
            req.resolved_at = time.time()
            req.resolver = "policy"
            logger.info("Escalation %s denied by policy for %r", req.request_id, permission)
        elif verdict == "allow":
            req.status = EscalationStatus.APPROVED
            req.resolved_at = time.time()
            req.resolver = "policy"
            self._session_count += 1
            logger.info("Escalation %s auto-approved for %r", req.request_id, permission)
        else:
            if self._session_count >= self.policy.max_escalations_per_session:
                req.status = EscalationStatus.DENIED
                req.resolved_at = time.time()
                req.resolver = "session_limit"
                logger.warning("Escalation %s denied: session limit reached", req.request_id)
            elif self.policy.allow_auto_approve:
                req.status = EscalationStatus.APPROVED
                req.resolved_at = time.time()
                req.resolver = "auto"
                self._session_count += 1
            else:
                if self._on_request:
                    self._on_request(req)

        self._requests[req.request_id] = req
        return req

    def approve(self, request_id: str, *, resolver: str = "user") -> bool:
        """Approve a pending escalation request. Returns ``True`` on success."""
        req = self._requests.get(request_id)
        if req is None or req.status != EscalationStatus.PENDING:
            return False
        req.status = EscalationStatus.APPROVED
        req.resolved_at = time.time()
        req.resolver = resolver
        self._session_count += 1
        logger.info("Escalation %s approved by %s", request_id, resolver)
        return True

    def deny(self, request_id: str, *, resolver: str = "user") -> bool:
        """Deny a pending escalation request. Returns ``True`` on success."""
        req = self._requests.get(request_id)
        if req is None or req.status != EscalationStatus.PENDING:
            return False
        req.status = EscalationStatus.DENIED
        req.resolved_at = time.time()
        req.resolver = resolver
        logger.info("Escalation %s denied by %s", request_id, resolver)
        return True

    def check_allowed(self, permission: str) -> bool:
        """Quick check: is *permission* currently allowed by policy or prior approval?"""
        if self.policy.is_explicitly_denied(permission):
            return False
        if self.policy.is_explicitly_allowed(permission):
            return True
        # Check if there was a recent approval for this permission.
        for req in reversed(list(self._requests.values())):
            if req.permission == permission and req.status == EscalationStatus.APPROVED:
                return True
        return False

    def expire_stale(self) -> int:
        """Expire any pending requests past the policy timeout. Returns count expired."""
        now = time.time()
        count = 0
        for req in self._requests.values():
            if req.status == EscalationStatus.PENDING:
                if now - req.created_at > self.policy.request_timeout:
                    req.status = EscalationStatus.EXPIRED
                    req.resolved_at = now
                    req.resolver = "timeout"
                    count += 1
        return count

    @property
    def pending(self) -> list[EscalationRequest]:
        return [r for r in self._requests.values() if r.status == EscalationStatus.PENDING]

    @property
    def history(self) -> list[EscalationRequest]:
        return list(self._requests.values())
