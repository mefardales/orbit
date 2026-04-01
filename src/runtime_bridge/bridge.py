"""Runtime bridge: connect to, execute on, and stream from a runtime process."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


class BridgeState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result of a single execution request."""

    request_id: str
    output: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.error is None


@dataclass
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 9100
    connect_timeout: float = 10.0
    execute_timeout: float = 60.0
    health_interval: float = 15.0
    reconnect_attempts: int = 3
    reconnect_delay: float = 2.0


class RuntimeBridge:
    """Manages a connection to a runtime process for command execution."""

    def __init__(self, config: Optional[BridgeConfig] = None) -> None:
        self.config = config or BridgeConfig()
        self._state = BridgeState.DISCONNECTED
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_counter = 0
        self._last_health: Optional[float] = None
        self._on_state_change: Optional[Callable[[BridgeState], None]] = None

    @property
    def state(self) -> BridgeState:
        return self._state

    def _set_state(self, new: BridgeState) -> None:
        old = self._state
        self._state = new
        if self._on_state_change and old != new:
            self._on_state_change(new)
        logger.debug("Bridge state: %s -> %s", old.value, new.value)

    # -- lifecycle -------------------------------------------------------------

    async def connect(self) -> bool:
        """Establish a TCP connection to the runtime process."""
        self._set_state(BridgeState.CONNECTING)
        for attempt in range(1, self.config.reconnect_attempts + 1):
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.config.host, self.config.port),
                    timeout=self.config.connect_timeout,
                )
                self._set_state(BridgeState.CONNECTED)
                self._last_health = time.monotonic()
                logger.info(
                    "Connected to runtime at %s:%d",
                    self.config.host,
                    self.config.port,
                )
                return True
            except (OSError, asyncio.TimeoutError) as exc:
                logger.warning(
                    "Connect attempt %d/%d failed: %s",
                    attempt,
                    self.config.reconnect_attempts,
                    exc,
                )
                if attempt < self.config.reconnect_attempts:
                    await asyncio.sleep(self.config.reconnect_delay)
        self._set_state(BridgeState.ERROR)
        return False

    async def disconnect(self) -> None:
        """Close the connection gracefully."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        self._set_state(BridgeState.DISCONNECTED)
        logger.info("Disconnected from runtime")

    # -- execution -------------------------------------------------------------

    def _next_id(self) -> str:
        self._request_counter += 1
        return f"req-{self._request_counter}"

    async def execute(self, command: str, *, timeout: Optional[float] = None) -> ExecutionResult:
        """Execute *command* and wait for the full result."""
        if self._state != BridgeState.CONNECTED:
            return ExecutionResult(request_id="n/a", exit_code=-1, error="Not connected")

        req_id = self._next_id()
        effective_timeout = timeout or self.config.execute_timeout
        payload = json.dumps({"id": req_id, "type": "exec", "command": command}) + "\n"

        assert self._writer is not None and self._reader is not None
        t0 = time.monotonic()
        try:
            self._writer.write(payload.encode())
            await self._writer.drain()
            raw = await asyncio.wait_for(
                self._reader.readline(), timeout=effective_timeout
            )
            elapsed = (time.monotonic() - t0) * 1000
            data = json.loads(raw)
            return ExecutionResult(
                request_id=req_id,
                output=data.get("output", ""),
                exit_code=data.get("exit_code", 0),
                duration_ms=round(elapsed, 2),
                error=data.get("error"),
            )
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - t0) * 1000
            return ExecutionResult(
                request_id=req_id,
                exit_code=-1,
                duration_ms=round(elapsed, 2),
                error="Execution timed out",
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            self._set_state(BridgeState.ERROR)
            return ExecutionResult(
                request_id=req_id,
                exit_code=-1,
                duration_ms=round(elapsed, 2),
                error=str(exc),
            )

    async def stream_execute(self, command: str) -> AsyncIterator[str]:
        """Execute *command* and yield output chunks as they arrive."""
        if self._state != BridgeState.CONNECTED:
            yield f"[error] Not connected\n"
            return

        req_id = self._next_id()
        payload = json.dumps({"id": req_id, "type": "stream", "command": command}) + "\n"

        assert self._writer is not None and self._reader is not None
        self._writer.write(payload.encode())
        await self._writer.drain()

        while True:
            try:
                raw = await asyncio.wait_for(
                    self._reader.readline(), timeout=self.config.execute_timeout
                )
            except asyncio.TimeoutError:
                yield "[error] Stream timed out\n"
                return

            if not raw:
                return  # EOF
            data = json.loads(raw)
            if data.get("type") == "chunk":
                yield data.get("data", "")
            elif data.get("type") == "done":
                return

    # -- health ----------------------------------------------------------------

    async def health_check(self) -> bool:
        """Send a health-check ping and return ``True`` if the runtime is alive."""
        if self._state != BridgeState.CONNECTED:
            return False

        req_id = self._next_id()
        payload = json.dumps({"id": req_id, "type": "ping"}) + "\n"

        assert self._writer is not None and self._reader is not None
        try:
            self._writer.write(payload.encode())
            await self._writer.drain()
            raw = await asyncio.wait_for(self._reader.readline(), timeout=5.0)
            data = json.loads(raw)
            alive = data.get("type") == "pong"
            if alive:
                self._last_health = time.monotonic()
            return alive
        except Exception:
            self._set_state(BridgeState.ERROR)
            return False
