"""Connection protocol definitions and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ConnectionProtocol(Enum):
    """Supported remote connection protocols."""

    SSH = "ssh"
    DOCKER = "docker"
    LOCAL = "local"

    @property
    def default_port(self) -> Optional[int]:
        """Default port for this protocol, or None if not applicable."""
        return {
            ConnectionProtocol.SSH: 22,
            ConnectionProtocol.DOCKER: None,
            ConnectionProtocol.LOCAL: None,
        }[self]


@dataclass
class ConnectionConfig:
    """Configuration for a remote connection."""

    host: str
    protocol: ConnectionProtocol = ConnectionProtocol.SSH
    port: Optional[int] = None
    user: Optional[str] = None
    identity_file: Optional[Path] = None
    container_name: Optional[str] = None
    timeout_seconds: int = 30
    env: dict[str, str] = field(default_factory=dict)
    forward_agent: bool = False
    compression: bool = False
    extra_options: dict[str, str] = field(default_factory=dict)

    @property
    def effective_port(self) -> Optional[int]:
        """Return configured port or protocol default."""
        return self.port or self.protocol.default_port

    @property
    def connection_string(self) -> str:
        """Human-readable connection string."""
        if self.protocol == ConnectionProtocol.DOCKER:
            return f"docker://{self.container_name or self.host}"
        if self.protocol == ConnectionProtocol.LOCAL:
            return "local://"
        user_part = f"{self.user}@" if self.user else ""
        port_part = f":{self.effective_port}" if self.effective_port != 22 else ""
        return f"ssh://{user_part}{self.host}{port_part}"

    def to_dict(self) -> dict:
        """Serialize to a dict for JSON storage."""
        return {
            "host": self.host,
            "protocol": self.protocol.value,
            "port": self.port,
            "user": self.user,
            "identity_file": str(self.identity_file) if self.identity_file else None,
            "container_name": self.container_name,
            "timeout_seconds": self.timeout_seconds,
            "env": self.env,
            "forward_agent": self.forward_agent,
            "compression": self.compression,
            "extra_options": self.extra_options,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConnectionConfig:
        """Deserialize from a dict."""
        data = dict(data)
        data["protocol"] = ConnectionProtocol(data.get("protocol", "ssh"))
        if data.get("identity_file"):
            data["identity_file"] = Path(data["identity_file"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
