"""Bridge transport layer - abstract and concrete transports."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Callable

from .connection import ConnectionPool
from .protocol import BridgeMessage, BridgeResponse, MessageType, deserialize, serialize

logger = logging.getLogger(__name__)


class BridgeTransport(ABC):
    """Abstract base class for bridge transports."""

    @abstractmethod
    def send(self, message: BridgeMessage) -> BridgeResponse:
        """Send a message and return the response."""
        ...

    @abstractmethod
    def connect(self, endpoint: str) -> None:
        """Establish connection to the given endpoint."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the current endpoint."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether the transport is currently connected."""
        ...


class LocalTransport(BridgeTransport):
    """In-process transport using direct function calls."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[BridgeMessage], BridgeResponse]] = {}
        self._connected = False
        self._endpoint: str = ""
        self._message_log: list[BridgeMessage] = []

    def register_handler(self, target: str, handler: Callable[[BridgeMessage], BridgeResponse]) -> None:
        self._handlers[target] = handler

    def connect(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._connected = True
        logger.info("LocalTransport connected to %s", endpoint)

    def disconnect(self) -> None:
        self._connected = False
        self._endpoint = ""

    def is_connected(self) -> bool:
        return self._connected

    def send(self, message: BridgeMessage) -> BridgeResponse:
        if not self._connected:
            return BridgeResponse.fail("Not connected", status_code=503)
        self._message_log.append(message)
        handler = self._handlers.get(message.target)
        if handler is None:
            return BridgeResponse.fail(f"No handler for target: {message.target}", status_code=404)
        try:
            return handler(message)
        except Exception as exc:
            logger.error("LocalTransport handler error: %s", exc)
            return BridgeResponse.fail(str(exc))


class RemoteTransport(BridgeTransport):
    """Network-based transport using serialized messages over a connection pool."""

    def __init__(self, pool: ConnectionPool | None = None) -> None:
        self._pool = pool or ConnectionPool()
        self._connected = False
        self._endpoint: str = ""
        self._subscribers: dict[MessageType, list[Callable[[BridgeMessage], None]]] = defaultdict(list)

    def connect(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._connected = True
        logger.info("RemoteTransport connected to %s", endpoint)

    def disconnect(self) -> None:
        self._pool.close_all()
        self._connected = False
        self._endpoint = ""

    def is_connected(self) -> bool:
        return self._connected

    def subscribe(self, msg_type: MessageType, callback: Callable[[BridgeMessage], None]) -> None:
        """Subscribe to messages of a given type."""
        self._subscribers[msg_type].append(callback)

    def send(self, message: BridgeMessage) -> BridgeResponse:
        if not self._connected:
            return BridgeResponse.fail("Not connected", status_code=503)

        try:
            conn = self._pool.acquire(self._endpoint)
            payload = serialize(message)
            # Simulate sending and receiving over the connection
            # In a real implementation, this would do network I/O
            response_data = self._simulate_send(payload)
            self._pool.release(conn)

            if response_data is None:
                return BridgeResponse.fail("No response received", status_code=504)

            response_msg = deserialize(response_data)
            self._notify_subscribers(response_msg)
            return BridgeResponse.ok(response_msg.payload)
        except Exception as exc:
            logger.error("RemoteTransport send error: %s", exc)
            return BridgeResponse.fail(str(exc))

    def _simulate_send(self, payload: bytes) -> bytes | None:
        """Placeholder for actual network send. Returns echo response."""
        msg = deserialize(payload)
        reply = msg.create_reply({"echo": True, "received": msg.payload})
        return serialize(reply)

    def _notify_subscribers(self, message: BridgeMessage) -> None:
        for callback in self._subscribers.get(message.msg_type, []):
            try:
                callback(message)
            except Exception as exc:
                logger.warning("Subscriber error: %s", exc)

    @property
    def pool_stats(self) -> dict[str, Any]:
        return self._pool.stats()
