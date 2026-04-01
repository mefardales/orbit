"""
MCP Server Bootstrap: lifecycle management for external MCP servers.

Starts external MCP servers as subprocesses, tracks their PIDs in
.orbit/state/mcp-pids.json, and cleans them up on exit.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from .registry import MCPRegistry, MCPServerConfig, get_registry

logger = logging.getLogger("orbit.mcp.server_bootstrap")

_PID_FILE = Path(".orbit") / "state" / "mcp-pids.json"
_HEALTH_CHECK_TIMEOUT = 5.0  # seconds to wait for a server to respond
_STARTUP_GRACE = 1.0  # seconds to allow after spawn before health check


def _pid_file_path() -> Path:
    return _PID_FILE


def _load_pid_map(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_pid_map(pid_map: Dict[str, int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pid_map, indent=2), encoding="utf-8")


def _process_alive(pid: int) -> bool:
    """Return True if the process with *pid* is alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


class MCPBootstrap:
    """Manages the lifecycle of external MCP server subprocesses.

    Usage:
        bootstrap = MCPBootstrap()
        proc = bootstrap.start_server(config)
        # ... do work ...
        bootstrap.stop_server("my-server")
    """

    def __init__(
        self,
        pid_file: Optional[Path] = None,
        registry: Optional[MCPRegistry] = None,
    ) -> None:
        self._pid_file = pid_file or _pid_file_path()
        self._registry = registry or get_registry()
        # name -> Popen handle for servers we started in this process
        self._procs: Dict[str, subprocess.Popen] = {}
        atexit.register(self.cleanup)

    # ── Start / stop / restart ───────────────────────────────────────────────

    def start_server(self, config: MCPServerConfig) -> subprocess.Popen:
        """Start an MCP server subprocess.

        If a server with that name is already tracked and alive, the existing
        handle is returned without spawning a new process.

        Args:
            config: The server configuration to start.

        Returns:
            The subprocess.Popen handle for the running server.
        """
        name = config.name

        # Check if we already manage this server in this process
        if name in self._procs:
            proc = self._procs[name]
            if proc.poll() is None:
                logger.debug("Server %r already running (pid=%d)", name, proc.pid)
                return proc
            # Process died — remove stale entry
            del self._procs[name]

        # Also check the PID file for orphaned processes from previous runs
        pid_map = _load_pid_map(self._pid_file)
        old_pid = pid_map.get(name)
        if old_pid and _process_alive(old_pid):
            logger.warning(
                "Server %r is already running as pid=%d (from a previous session). "
                "Stop it first or call restart_server().",
                name,
                old_pid,
            )

        env = {**os.environ, **config.env}
        cmd = [config.command] + config.args

        logger.info("Starting MCP server %r: %s", name, " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._procs[name] = proc

        # Persist PID
        pid_map[name] = proc.pid
        _save_pid_map(pid_map, self._pid_file)

        # Brief grace period before health check
        time.sleep(_STARTUP_GRACE)

        if not self.is_healthy(name):
            logger.warning("Server %r may not be healthy after startup", name)

        return proc

    def stop_server(self, name: str) -> bool:
        """Stop a managed MCP server by name.

        Sends SIGTERM first; if the process doesn't exit within 3 seconds,
        sends SIGKILL.

        Returns:
            True if the server was found and stopped, False otherwise.
        """
        proc = self._procs.pop(name, None)
        pid_map = _load_pid_map(self._pid_file)
        pid = pid_map.pop(name, None)

        if proc is None and (pid is None or not _process_alive(pid)):
            logger.debug("stop_server(%r): server not found or already stopped", name)
            _save_pid_map(pid_map, self._pid_file)
            return False

        target_proc = proc
        if target_proc is None and pid:
            # Try to kill by PID directly
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(3)
                if _process_alive(pid):
                    os.kill(pid, signal.SIGKILL)
            except OSError as exc:
                logger.warning("Failed to kill pid=%d for server %r: %s", pid, name, exc)
            _save_pid_map(pid_map, self._pid_file)
            return True

        # We have a Popen handle
        try:
            target_proc.terminate()
            try:
                target_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                target_proc.kill()
                target_proc.wait(timeout=2)
        except OSError as exc:
            logger.warning("Error stopping server %r: %s", name, exc)

        _save_pid_map(pid_map, self._pid_file)
        logger.info("Stopped MCP server %r", name)
        return True

    def restart_server(self, name: str) -> bool:
        """Restart a named MCP server.

        Looks up the config from the registry. Returns False if the server
        config is not found.
        """
        config = self._registry.get_server(name)
        if config is None:
            logger.error("restart_server(%r): no config found in registry", name)
            return False
        self.stop_server(name)
        self.start_server(config)
        return True

    # ── Health check ─────────────────────────────────────────────────────────

    def is_healthy(self, name: str) -> bool:
        """Check whether a managed server process is alive.

        This is a lightweight check — it verifies the process is still running
        (has not exited). A full JSON-RPC ping would require the MCPClient.
        """
        proc = self._procs.get(name)
        if proc is not None:
            return proc.poll() is None

        # Fall back to PID file
        pid_map = _load_pid_map(self._pid_file)
        pid = pid_map.get(name)
        if pid:
            return _process_alive(pid)

        return False

    # ── Queries ──────────────────────────────────────────────────────────────

    def list_running(self) -> List[str]:
        """Return names of servers that are currently alive."""
        running: List[str] = []
        for name, proc in list(self._procs.items()):
            if proc.poll() is None:
                running.append(name)
        return sorted(running)

    def get_pid(self, name: str) -> Optional[int]:
        """Return the PID of a running server, or None."""
        proc = self._procs.get(name)
        if proc is not None and proc.poll() is None:
            return proc.pid
        pid_map = _load_pid_map(self._pid_file)
        return pid_map.get(name)

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Kill all servers started by this bootstrap instance.

        Called automatically via atexit. Safe to call multiple times.
        """
        for name in list(self._procs.keys()):
            self.stop_server(name)
        logger.debug("MCPBootstrap cleanup complete")


# Module-level default bootstrap instance
_default_bootstrap = MCPBootstrap()


def get_bootstrap() -> MCPBootstrap:
    """Return the module-level default MCPBootstrap instance."""
    return _default_bootstrap
