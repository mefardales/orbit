"""Authority lease management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import AuthoritySnapshot


class AuthorityError(Exception):
    """Error for authority lease operations."""

    def __init__(self, kind: str, message: str, current_owner: Optional[str] = None):
        super().__init__(message)
        self.kind = kind
        self.current_owner = current_owner

    @classmethod
    def already_held_by_other(cls, current_owner: str) -> AuthorityError:
        return cls("already_held", f"lease already held by {current_owner}", current_owner)

    @classmethod
    def owner_mismatch(cls, current_owner: str) -> AuthorityError:
        return cls("owner_mismatch", f"owner mismatch: lease held by {current_owner}", current_owner)

    @classmethod
    def not_held(cls) -> AuthorityError:
        return cls("not_held", "no lease currently held")


class AuthorityLease:
    """Manages a single authority lease with acquire/renew/release semantics."""

    def __init__(self):
        self._owner: Optional[str] = None
        self._lease_id: Optional[str] = None
        self._leased_until: Optional[str] = None
        self._stale: bool = False
        self._stale_reason: Optional[str] = None

    def acquire(self, owner: str, lease_id: str, leased_until: str) -> None:
        if self._owner is not None and self._owner != owner:
            raise AuthorityError.already_held_by_other(self._owner)
        self._owner = owner
        self._lease_id = lease_id
        self._leased_until = leased_until
        self._stale = False
        self._stale_reason = None

    def renew(self, owner: str, lease_id: str, leased_until: str) -> None:
        if self._owner is None:
            raise AuthorityError.not_held()
        if self._owner != owner:
            raise AuthorityError.owner_mismatch(self._owner)
        self._lease_id = lease_id
        self._leased_until = leased_until
        self._stale = False
        self._stale_reason = None

    def force_release(self) -> None:
        self._owner = None
        self._lease_id = None
        self._leased_until = None
        self._stale = False
        self._stale_reason = None

    def mark_stale(self, reason: str) -> None:
        self._stale = True
        self._stale_reason = reason

    def clear_stale(self) -> None:
        self._stale = False
        self._stale_reason = None

    def is_held(self) -> bool:
        return self._owner is not None

    def is_stale(self) -> bool:
        return self._stale

    def current_owner(self) -> Optional[str]:
        return self._owner

    def to_snapshot(self) -> AuthoritySnapshot:
        return AuthoritySnapshot(
            owner=self._owner,
            lease_id=self._lease_id,
            leased_until=self._leased_until,
            stale=self._stale,
            stale_reason=self._stale_reason,
        )
