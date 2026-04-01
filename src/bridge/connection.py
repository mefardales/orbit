"""Connection pool and connection management for the bridge."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """State of a bridge connection."""
    IDLE = "idle"
    ACTIVE = "active"
    DRAINING = "draining"
    CLOSED = "closed"


@dataclass
class Connection:
    """Represents a single connection in the pool."""
    conn_id: str
    endpoint: str
    state: ConnectionState = ConnectionState.IDLE
    created_at: float = field(default_factory=time.monotonic)
    last_used_at: float = field(default_factory=time.monotonic)
    request_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_used_at

    def mark_active(self) -> None:
        self.state = ConnectionState.ACTIVE
        self.last_used_at = time.monotonic()
        self.request_count += 1

    def mark_idle(self) -> None:
        self.state = ConnectionState.IDLE
        self.last_used_at = time.monotonic()

    def close(self) -> None:
        self.state = ConnectionState.CLOSED


class ConnectionPool:
    """Manages a pool of reusable connections."""

    def __init__(
        self,
        max_size: int = 10,
        max_idle_seconds: float = 300.0,
        max_age_seconds: float = 3600.0,
    ) -> None:
        self.max_size = max_size
        self.max_idle_seconds = max_idle_seconds
        self.max_age_seconds = max_age_seconds
        self._connections: dict[str, Connection] = {}
        self._counter = 0

    def acquire(self, endpoint: str) -> Connection:
        """Get an idle connection for the endpoint, or create a new one."""
        # Try to reuse an idle connection
        for conn in self._connections.values():
            if conn.endpoint == endpoint and conn.state == ConnectionState.IDLE:
                conn.mark_active()
                logger.debug("Reusing connection %s for %s", conn.conn_id, endpoint)
                return conn

        # Create new if under limit
        if len(self._connections) >= self.max_size:
            self._evict_idle()
            if len(self._connections) >= self.max_size:
                raise RuntimeError(f"Connection pool exhausted (max={self.max_size})")

        self._counter += 1
        conn_id = f"conn-{self._counter}"
        conn = Connection(conn_id=conn_id, endpoint=endpoint, state=ConnectionState.ACTIVE)
        self._connections[conn_id] = conn
        logger.debug("Created connection %s for %s", conn_id, endpoint)
        return conn

    def release(self, conn: Connection) -> None:
        """Return a connection to the pool."""
        if conn.conn_id in self._connections:
            conn.mark_idle()
            logger.debug("Released connection %s", conn.conn_id)

    def close(self, conn: Connection) -> None:
        """Close and remove a connection."""
        conn.close()
        self._connections.pop(conn.conn_id, None)

    def close_all(self) -> int:
        """Close all connections. Returns count closed."""
        count = len(self._connections)
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
        return count

    def _evict_idle(self) -> None:
        """Remove stale idle connections."""
        to_remove = []
        for cid, conn in self._connections.items():
            if conn.state == ConnectionState.IDLE and (
                conn.idle_seconds > self.max_idle_seconds
                or conn.age_seconds > self.max_age_seconds
            ):
                to_remove.append(cid)
        for cid in to_remove:
            self._connections[cid].close()
            del self._connections[cid]

    @property
    def size(self) -> int:
        return len(self._connections)

    @property
    def active_count(self) -> int:
        return sum(1 for c in self._connections.values() if c.state == ConnectionState.ACTIVE)

    @property
    def idle_count(self) -> int:
        return sum(1 for c in self._connections.values() if c.state == ConnectionState.IDLE)

    def stats(self) -> dict[str, Any]:
        return {
            "total": self.size,
            "active": self.active_count,
            "idle": self.idle_count,
            "max_size": self.max_size,
        }
