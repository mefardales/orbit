"""RemoteConnector - unified interface for remote connections."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from remote.protocols import ConnectionConfig, ConnectionProtocol
from remote.ssh import SSHConnection, CommandResult


class RemoteConnector:
    """Unified remote connection interface supporting SSH and Docker."""

    def __init__(self, config: ConnectionConfig) -> None:
        self.config = config
        self._ssh: Optional[SSHConnection] = None
        self._connected = False

    def connect(self) -> bool:
        """Establish the remote connection.

        Returns:
            True if connection was successful.
        """
        if self.config.protocol == ConnectionProtocol.LOCAL:
            self._connected = True
            return True

        if self.config.protocol == ConnectionProtocol.SSH:
            self._ssh = SSHConnection(self.config)
            self._connected = self._ssh.connect()
            return self._connected

        if self.config.protocol == ConnectionProtocol.DOCKER:
            return self._docker_connect()

        return False

    def _docker_connect(self) -> bool:
        """Test docker container connectivity."""
        name = self.config.container_name or self.config.host
        try:
            proc = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", name],
                capture_output=True, text=True, timeout=10,
            )
            self._connected = proc.returncode == 0 and "true" in proc.stdout.lower()
            return self._connected
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def disconnect(self) -> None:
        """Close the connection."""
        if self._ssh:
            self._ssh.disconnect()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> CommandResult:
        """Execute a command on the remote target.

        Args:
            command: Shell command to run.
            timeout: Timeout in seconds.
            cwd: Working directory on the remote.

        Returns:
            CommandResult with output and status.
        """
        if self.config.protocol == ConnectionProtocol.LOCAL:
            return self._local_execute(command, timeout, cwd)

        if self.config.protocol == ConnectionProtocol.DOCKER:
            return self._docker_execute(command, timeout, cwd)

        if self._ssh:
            return self._ssh.execute(command, timeout=timeout, cwd=cwd)

        return CommandResult(
            returncode=-1, stdout="", stderr="Not connected", command=command
        )

    def _local_execute(
        self, command: str, timeout: Optional[int], cwd: Optional[str]
    ) -> CommandResult:
        """Execute locally."""
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout or self.config.timeout_seconds,
                cwd=cwd,
            )
            return CommandResult(proc.returncode, proc.stdout, proc.stderr, command)
        except subprocess.TimeoutExpired:
            return CommandResult(-1, "", "Timed out", command)

    def _docker_execute(
        self, command: str, timeout: Optional[int], cwd: Optional[str]
    ) -> CommandResult:
        """Execute inside a docker container."""
        name = self.config.container_name or self.config.host
        args = ["docker", "exec"]
        if cwd:
            args.extend(["-w", cwd])
        for k, v in self.config.env.items():
            args.extend(["-e", f"{k}={v}"])
        args.extend([name, "sh", "-c", command])
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True,
                timeout=timeout or self.config.timeout_seconds,
            )
            return CommandResult(proc.returncode, proc.stdout, proc.stderr, command)
        except subprocess.TimeoutExpired:
            return CommandResult(-1, "", "Docker exec timed out", command)

    def transfer_file(
        self,
        local_path: Path,
        remote_path: str,
        upload: bool = True,
    ) -> CommandResult:
        """Transfer a file to/from the remote target.

        Args:
            local_path: Local file path.
            remote_path: Remote file path.
            upload: True for upload, False for download.

        Returns:
            CommandResult from the transfer.
        """
        if self.config.protocol == ConnectionProtocol.LOCAL:
            import shutil
            try:
                if upload:
                    shutil.copy2(str(local_path), remote_path)
                else:
                    shutil.copy2(remote_path, str(local_path))
                return CommandResult(0, "", "", f"cp {local_path} {remote_path}")
            except OSError as e:
                return CommandResult(1, "", str(e), "cp")

        if self.config.protocol == ConnectionProtocol.DOCKER:
            name = self.config.container_name or self.config.host
            if upload:
                args = ["docker", "cp", str(local_path), f"{name}:{remote_path}"]
            else:
                args = ["docker", "cp", f"{name}:{remote_path}", str(local_path)]
            try:
                proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
                return CommandResult(proc.returncode, proc.stdout, proc.stderr, " ".join(args))
            except subprocess.TimeoutExpired:
                return CommandResult(-1, "", "Docker cp timed out", " ".join(args))

        if self._ssh:
            return self._ssh.transfer_file(local_path, remote_path, upload)

        return CommandResult(-1, "", "Not connected", "transfer")
