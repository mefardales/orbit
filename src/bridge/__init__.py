"""Bridge subsystem - communication bridge between components."""

from .connection import Connection, ConnectionPool, ConnectionState
from .protocol import BridgeMessage, BridgeResponse, MessageType, deserialize, serialize
from .transport import BridgeTransport, LocalTransport, RemoteTransport

__all__ = [
    "BridgeMessage",
    "BridgeResponse",
    "BridgeTransport",
    "Connection",
    "ConnectionPool",
    "ConnectionState",
    "LocalTransport",
    "MessageType",
    "RemoteTransport",
    "deserialize",
    "serialize",
]
