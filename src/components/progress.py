"""Progress bar component for terminal output."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field


@dataclass
class ProgressStyle:
    """Visual configuration for a progress bar."""
    width: int = 40
    fill_char: str = "█"
    empty_char: str = "░"
    left_bracket: str = ""
    right_bracket: str = ""
    show_percentage: bool = True
    show_count: bool = True
    show_rate: bool = True
    show_eta: bool = True


class ProgressBar:
    """Terminal progress bar with rate and ETA estimation."""

    def __init__(
        self,
        total: int = 100,
        description: str = "",
        style: ProgressStyle | None = None,
        stream: object | None = None,
    ) -> None:
        self.total = total
        self.description = description
        self.style = style or ProgressStyle()
        self._stream = stream or sys.stderr
        self._current = 0
        self._started_at = time.monotonic()
        self._finished = False

    def advance(self, n: int = 1) -> None:
        """Advance the progress bar by n steps."""
        self._current = min(self._current + n, self.total)
        self._render()
        if self._current >= self.total:
            self.complete()

    def set(self, value: int) -> None:
        """Set absolute progress value."""
        self._current = min(max(0, value), self.total)
        self._render()

    def complete(self) -> None:
        """Mark as completed."""
        if self._finished:
            return
        self._current = self.total
        self._finished = True
        self._render()
        self._write("\n")

    @property
    def fraction(self) -> float:
        if self.total == 0:
            return 1.0
        return self._current / self.total

    @property
    def percentage(self) -> float:
        return self.fraction * 100

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._started_at

    @property
    def rate(self) -> float:
        """Items per second."""
        elapsed = self.elapsed_seconds
        if elapsed == 0:
            return 0.0
        return self._current / elapsed

    @property
    def eta_seconds(self) -> float | None:
        """Estimated time to completion in seconds."""
        if self.rate == 0 or self._finished:
            return None
        remaining = self.total - self._current
        return remaining / self.rate

    def _render(self) -> None:
        s = self.style
        filled = int(s.width * self.fraction)
        bar = s.fill_char * filled + s.empty_char * (s.width - filled)

        parts: list[str] = []
        if self.description:
            parts.append(self.description)
        parts.append(f"{s.left_bracket}{bar}{s.right_bracket}")
        if s.show_percentage:
            parts.append(f"{self.percentage:5.1f}%")
        if s.show_count:
            parts.append(f"{self._current}/{self.total}")
        if s.show_rate and self._current > 0:
            parts.append(f"[{self.rate:.1f} it/s]")
        if s.show_eta and self.eta_seconds is not None:
            eta = self.eta_seconds
            if eta < 60:
                parts.append(f"ETA {eta:.0f}s")
            else:
                parts.append(f"ETA {eta / 60:.1f}m")

        line = " ".join(parts)
        self._write(f"\r\033[K{line}")

    def _write(self, text: str) -> None:
        if hasattr(self._stream, "write"):
            self._stream.write(text)  # type: ignore[union-attr]
            if hasattr(self._stream, "flush"):
                self._stream.flush()  # type: ignore[union-attr]

    def __enter__(self) -> ProgressBar:
        self._started_at = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        if not self._finished:
            self.complete()
