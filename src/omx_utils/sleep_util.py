"""Sleep utilities."""
from __future__ import annotations
import asyncio
import time

def sleep_ms(ms: int) -> None:
    time.sleep(ms / 1000.0)

async def async_sleep_ms(ms: int) -> None:
    await asyncio.sleep(ms / 1000.0)
