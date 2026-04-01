"""Remote connection management subsystem."""

from remote.connector import RemoteConnector
from remote.ssh import SSHConnection
from remote.protocols import ConnectionProtocol, ConnectionConfig

__all__ = ["RemoteConnector", "SSHConnection", "ConnectionProtocol", "ConnectionConfig"]
