"""
MCP server bootstrap and lifecycle management.

Provides the auto-start mechanism for MCP servers that communicate over
stdin/stdout (stdio transport). Handles signal-based graceful shutdown
and environment-variable gating.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Literal, Optional, Protocol

logger = logging.getLogger("orbit.mcp")

# ── Types ────────────────────────────────────────────────────────────────────

McpServerName = Literal["state", "memory", "code_intel", "trace", "team"]

SERVER_DISABLE_ENV: Dict[McpServerName, str] = {
    "state": "OMX_STATE_SERVER_DISABLE_AUTO_START",
    "memory": "OMX_MEMORY_SERVER_DISABLE_AUTO_START",
    "code_intel": "OMX_CODE_INTEL_SERVER_DISABLE_AUTO_START",
    "trace": "OMX_TRACE_SERVER_DISABLE_AUTO_START",
    "team": "OMX_TEAM_SERVER_DISABLE_AUTO_START",
}

GLOBAL_DISABLE_ENV = "OMX_MCP_SERVER_DISABLE_AUTO_START"


# ── MCP Tool / Result helpers ────────────────────────────────────────────────


@dataclass
class ToolDefinition:
    """Schema for an MCP tool exposed by a server."""

    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class TextContent:
    type: str = "text"
    text: str = ""


@dataclass
class ToolResult:
    content: List[TextContent] = field(default_factory=list)
    is_error: bool = False


def text_result(data: Any) -> ToolResult:
    """Wrap arbitrary data as a JSON text tool result."""
    return ToolResult(
        content=[TextContent(text=json.dumps(data, indent=2, default=str))]
    )


def error_result(msg: str) -> ToolResult:
    """Return an error tool result."""
    return ToolResult(
        content=[TextContent(text=json.dumps({"error": msg}))],
        is_error=True,
    )


# ── Transport abstraction ────────────────────────────────────────────────────


class StdioTransport:
    """Minimal stdio JSON-RPC transport for MCP servers.

    Reads newline-delimited JSON from stdin, writes responses to stdout.
    """

    def __init__(self) -> None:
        self._closed = False
        self.on_close: Optional[Callable[[], None]] = None

    async def read_message(self) -> Optional[Dict[str, Any]]:
        """Read one JSON message from stdin. Returns None on EOF."""
        loop = asyncio.get_event_loop()
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
        except (EOFError, OSError):
            return None
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON on stdin: %s", line[:200])
            return None

    def write_message(self, msg: Dict[str, Any]) -> None:
        """Write a JSON message to stdout."""
        if self._closed:
            return
        try:
            sys.stdout.write(json.dumps(msg) + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            self._closed = True

    def close(self) -> None:
        self._closed = True
        if self.on_close:
            self.on_close()


# ── Server protocol ──────────────────────────────────────────────────────────


class McpServer(Protocol):
    """Protocol that concrete MCP server implementations should satisfy."""

    async def list_tools(self) -> List[ToolDefinition]:
        ...

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        ...

    async def close(self) -> None:
        ...


# ── Bootstrap ────────────────────────────────────────────────────────────────


def should_auto_start_mcp_server(
    server: McpServerName,
    env: Optional[Dict[str, Optional[str]]] = None,
) -> bool:
    """Check whether the given MCP server should auto-start based on env vars."""
    if env is None:
        env = dict(os.environ)

    global_disabled = env.get(GLOBAL_DISABLE_ENV) == "1"
    server_disabled = env.get(SERVER_DISABLE_ENV[server]) == "1"
    return not global_disabled and not server_disabled


async def run_stdio_server(
    server_name: McpServerName,
    server: McpServer,
    transport: Optional[StdioTransport] = None,
) -> None:
    """Run an MCP server over stdio transport until shutdown.

    Handles SIGTERM/SIGINT for graceful shutdown.
    """
    if transport is None:
        transport = StdioTransport()

    shutting_down = False
    loop = asyncio.get_event_loop()

    async def shutdown() -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        try:
            await server.close()
        except Exception:
            logger.exception("[%s] shutdown failed", server_name)
        transport.close()

    # Register signal handlers (Unix only)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown()))
        except NotImplementedError:
            # Windows
            pass

    transport.on_close = lambda: asyncio.ensure_future(shutdown())

    logger.info("[%s] MCP server started", server_name)

    while not shutting_down:
        msg = await transport.read_message()
        if msg is None:
            await shutdown()
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        if method == "tools/list":
            tools = await server.list_tools()
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.input_schema,
                        }
                        for t in tools
                    ]
                },
            }
            transport.write_message(response)

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await server.call_tool(tool_name, arguments)
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": c.type, "text": c.text} for c in result.content],
                    **({"isError": True} if result.is_error else {}),
                },
            }
            transport.write_message(response)

        elif method == "shutdown":
            if msg_id is not None:
                transport.write_message({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            await shutdown()
            break


def auto_start_stdio_mcp_server(
    server_name: McpServerName,
    server: McpServer,
) -> None:
    """Auto-start an MCP server unless disabled by env vars.

    This is the main entry point for MCP server scripts.
    """
    if not should_auto_start_mcp_server(server_name):
        return

    try:
        asyncio.run(run_stdio_server(server_name, server))
    except KeyboardInterrupt:
        pass
