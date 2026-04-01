"""
MCP Client: JSON-RPC over stdio communication with external MCP servers.

Provides tool listing and tool invocation against running MCP server
subprocesses managed by MCPBootstrap.
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .server_bootstrap import MCPBootstrap, get_bootstrap
from .registry import MCPRegistry, get_registry

logger = logging.getLogger("orbit.mcp.client")

_DEFAULT_TIMEOUT = 10.0  # seconds per JSON-RPC call


class MCPError(Exception):
    """Raised when an MCP server returns an error or communication fails."""

    def __init__(self, message: str, code: Optional[int] = None, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


@dataclass
class ToolInfo:
    """Metadata about a tool exposed by an MCP server."""

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)


class _ServerIO:
    """Wraps a running Popen handle for synchronous JSON-RPC request/response.

    Each call sends a request on stdin and reads one matching response from
    stdout. A background reader thread drains stdout into a queue so we never
    block the process pipe.
    """

    def __init__(self, proc: subprocess.Popen, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._proc = proc
        self._timeout = timeout
        self._msg_id: int = 0
        self._responses: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._dead = False

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        try:
            for raw_line in self._proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._responses.put(msg)
                except json.JSONDecodeError:
                    logger.warning("MCPClient: unparseable stdout line: %s", line[:200])
        except (OSError, ValueError):
            pass
        finally:
            self._dead = True

    def call(self, method: str, params: Dict[str, Any]) -> Any:
        """Send a JSON-RPC request and return the result payload.

        Raises MCPError on JSON-RPC errors, timeouts, or dead process.
        """
        if self._dead or self._proc.poll() is not None:
            raise MCPError("Server process is not running")

        self._msg_id += 1
        msg_id = self._msg_id
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }

        assert self._proc.stdin is not None
        try:
            payload = (json.dumps(request) + "\n").encode("utf-8")
            self._proc.stdin.write(payload)
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError(f"Failed to write to server stdin: {exc}") from exc

        # Wait for the matching response
        deadline = time.monotonic() + self._timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPError(f"Timed out waiting for response to method={method!r} (id={msg_id})")
            try:
                msg = self._responses.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if self._dead or self._proc.poll() is not None:
                    raise MCPError("Server process died while waiting for response")
                continue

            if msg.get("id") != msg_id:
                # Not ours — put back and retry (simplified: log and skip)
                logger.debug("MCPClient: received response for id=%s, expected %s", msg.get("id"), msg_id)
                continue

            if "error" in msg:
                err = msg["error"]
                raise MCPError(
                    err.get("message", "Unknown server error"),
                    code=err.get("code"),
                    data=err.get("data"),
                )

            return msg.get("result")


class MCPClient:
    """High-level MCP client that communicates with named external servers.

    The client resolves server names through the MCPBootstrap instance and
    opens per-server IO channels on demand, caching them for reuse.
    """

    def __init__(
        self,
        bootstrap: Optional[MCPBootstrap] = None,
        registry: Optional[MCPRegistry] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._bootstrap = bootstrap or get_bootstrap()
        self._registry = registry or get_registry()
        self._timeout = timeout
        self._channels: Dict[str, _ServerIO] = {}

    # ── Internal: channel management ─────────────────────────────────────────

    def _get_channel(self, server_name: str) -> _ServerIO:
        """Return a live _ServerIO for the named server, (re)starting if needed."""
        chan = self._channels.get(server_name)
        if chan is not None and not chan._dead and chan._proc.poll() is None:
            return chan

        # Need to start or restart the server
        config = self._registry.get_server(server_name)
        if config is None:
            raise MCPError(f"No MCP server registered with name {server_name!r}")
        if not config.enabled:
            raise MCPError(f"MCP server {server_name!r} is disabled")

        proc = self._bootstrap.start_server(config)
        chan = _ServerIO(proc, timeout=self._timeout)
        self._channels[server_name] = chan
        return chan

    # ── Public API ───────────────────────────────────────────────────────────

    def list_tools(self, server_name: str) -> List[ToolInfo]:
        """Return the list of tools exposed by the named MCP server.

        Args:
            server_name: The name of the server as registered in MCPRegistry.

        Returns:
            A list of ToolInfo objects.

        Raises:
            MCPError: on communication failure, timeout, or server error.
        """
        chan = self._get_channel(server_name)
        result = chan.call("tools/list", {})
        tools_raw = result.get("tools", []) if isinstance(result, dict) else []
        out: List[ToolInfo] = []
        for t in tools_raw:
            if not isinstance(t, dict):
                continue
            out.append(
                ToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
            )
        return out

    def call_tool(self, server_name: str, tool_name: str, args: Dict[str, Any]) -> Any:
        """Invoke a tool on the named MCP server.

        Args:
            server_name: The server to communicate with.
            tool_name:   The tool to invoke on the server.
            args:        Arguments to pass to the tool.

        Returns:
            The tool result (parsed from the JSON-RPC response).

        Raises:
            MCPError: on communication failure, timeout, or tool error.
        """
        chan = self._get_channel(server_name)
        result = chan.call("tools/call", {"name": tool_name, "arguments": args})

        if not isinstance(result, dict):
            return result

        if result.get("isError"):
            content = result.get("content", [])
            messages = [c.get("text", "") for c in content if isinstance(c, dict)]
            raise MCPError(f"Tool {tool_name!r} returned an error: {'; '.join(messages)}")

        # Return the content array or, if there's only one text item, its text
        content = result.get("content", [])
        if len(content) == 1 and isinstance(content[0], dict) and content[0].get("type") == "text":
            text = content[0]["text"]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text

        return content

    def close(self, server_name: str) -> None:
        """Send a shutdown request and remove the channel for the named server."""
        chan = self._channels.pop(server_name, None)
        if chan is None:
            return
        try:
            chan.call("shutdown", {})
        except MCPError:
            pass

    def close_all(self) -> None:
        """Close all open server channels."""
        for name in list(self._channels.keys()):
            self.close(name)


# Module-level default client
_default_client = MCPClient()


def get_client() -> MCPClient:
    """Return the module-level default MCPClient instance."""
    return _default_client
