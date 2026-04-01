"""Bridge protocol - message serialization and deserialization."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageType(Enum):
    """Types of bridge messages."""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


@dataclass
class BridgeMessage:
    """A message transmitted across the bridge."""
    msg_type: MessageType
    payload: dict[str, Any]
    source: str = ""
    target: str = ""
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    headers: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["msg_type"] = self.msg_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BridgeMessage:
        data = dict(data)
        data["msg_type"] = MessageType(data["msg_type"])
        return cls(**data)

    def create_reply(self, payload: dict[str, Any]) -> BridgeMessage:
        return BridgeMessage(
            msg_type=MessageType.RESPONSE,
            payload=payload,
            source=self.target,
            target=self.source,
            correlation_id=self.message_id,
        )

    def create_error(self, error: str, code: int = 500) -> BridgeMessage:
        return BridgeMessage(
            msg_type=MessageType.ERROR,
            payload={"error": error, "code": code},
            source=self.target,
            target=self.source,
            correlation_id=self.message_id,
        )


@dataclass
class BridgeResponse:
    """Wraps a response with status information."""
    success: bool
    data: Any = None
    error: str | None = None
    status_code: int = 200
    duration_ms: float = 0.0

    @classmethod
    def ok(cls, data: Any = None) -> BridgeResponse:
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, status_code: int = 500) -> BridgeResponse:
        return cls(success=False, error=error, status_code=status_code)


def serialize(message: BridgeMessage) -> bytes:
    """Serialize a BridgeMessage to bytes."""
    return json.dumps(message.to_dict(), separators=(",", ":")).encode("utf-8")


def deserialize(data: bytes) -> BridgeMessage:
    """Deserialize bytes into a BridgeMessage."""
    parsed = json.loads(data.decode("utf-8"))
    return BridgeMessage.from_dict(parsed)


def make_heartbeat(source: str) -> BridgeMessage:
    """Create a heartbeat message."""
    return BridgeMessage(
        msg_type=MessageType.HEARTBEAT,
        payload={"alive": True},
        source=source,
    )
