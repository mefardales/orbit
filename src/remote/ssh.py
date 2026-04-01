"""SSH connection implementation wrapping subprocess."""

from __future__ import annotations

import subprocess
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .protocols import ConnectionConfig


@dataclass
class CommandResult:
    """Result of a remote command execution."""

    returncode: int
    stdout: str
    stderr: str
    command: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class SSHConnection:
    """SSH connection wrapping subprocess ssh/scp calls."""

    def __init__(self, config: ConnectionConfig) -> None:
        self.config = config
        self._connected = False

    def _build_ssh_args(self) -> list[str]:
        """Build base SSH command arguments."""
        args = ["ssh"]
        if self.config.effective_port and self.config.effective_port != 22:
            args.extend(["-p", str(self.config.effective_port)])
        if self.config.identity_file:
            args.extend(["-i", str(self.config.identity_file)])
        if self.config.forward_agent:
            args.append("-A")
        if self.config.compression:
            args.append("-C")
        args.extend(["-o", f"ConnectTimeout={self.config.timeout_seconds}"])
        args.extend(["-o", "StrictHostKeyChecking=accept-new"])
        args.extend(["-o", "BatchMode=yes"])
        for key, val in self.config.extra_options.items():
            args.extend(["-o", f"{key}={val}"])
        return args

    def _target(self) -> str:
        """Build user@host target string."""
        if self.config.user:
            return f"{self.config.user}@{self.config.host}"
        return self.config.host

    def test_connection(self) -> bool:
        """Test if the SSH connection works."""
        try:
            result = self.execute("echo ok", timeout=10)
            self._connected = result.success and "ok" in result.stdout
            return self._connected
        except (subprocess.TimeoutExpired, OSError):
            return False

    def connect(self) -> bool:
        """Verify connectivity. Returns True if reachable."""
        return self.test_connection()

    def disconnect(self) -> None:
        """Mark connection as closed."""
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
        """Execute a command on the remote host via SSH.

        Args:
            command: Shell command to execute remotely.
            timeout: Override timeout in seconds.
            cwd: Remote working directory (prepends cd).

        Returns:
            CommandResult with stdout, stderr, and returncode.
        """
        if cwd:
            command = f"cd {shlex.quote(cwd)} && {command}"

        # Prepend environment variables
        env_prefix = " ".join(
            f"{k}={shlex.quote(v)}" for k, v in self.config.env.items()
        )
        if env_prefix:
            command = f"{env_prefix} {command}"

        args = self._build_ssh_args() + [self._target(), command]
        effective_timeout = timeout or self.config.timeout_seconds

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            return CommandResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=command,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {effective_timeout}s",
                command=command,
            )

    def transfer_file(
        self,
        local_path: Path,
        remote_path: str,
        upload: bool = True,
    ) -> CommandResult:
        """Transfer a file via scp.

        Args:
            local_path: Local file path.
            remote_path: Remote file path.
            upload: True to upload local->remote, False to download.

        Returns:
            CommandResult from the scp command.
        """
        args = ["scp", "-o", "BatchMode=yes"]
        if self.config.effective_port and self.config.effective_port != 22:
            args.extend(["-P", str(self.config.effective_port)])
        if self.config.identity_file:
            args.extend(["-i", str(self.config.identity_file)])
        if self.config.compression:
            args.append("-C")

        remote_target = f"{self._target()}:{remote_path}"
        if upload:
            args.extend([str(local_path), remote_target])
        else:
            args.extend([remote_target, str(local_path)])

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
            return CommandResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=" ".join(args),
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr="SCP transfer timed out",
                command=" ".join(args),
            )
