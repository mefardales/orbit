"""Terminal spinner component for indicating progress."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
DOTS_FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
LINE_FRAMES = ["-", "\\", "|", "/"]


@dataclass
class SpinnerStyle:
    """Visual style for a spinner."""
    frames: list[str] = field(default_factory=lambda: list(SPINNER_FRAMES))
    interval_ms: float = 80.0
    prefix: str = ""
    suffix: str = ""
    done_char: str = "✓"
    fail_char: str = "✗"


class Spinner:
    """Animated terminal spinner with thread-based animation."""

    def __init__(
        self,
        message: str = "",
        style: SpinnerStyle | None = None,
        stream: object | None = None,
    ) -> None:
        self.message = message
        self.style = style or SpinnerStyle()
        self._stream = stream or sys.stderr
        self._running = False
        self._thread: threading.Thread | None = None
        self._frame_idx = 0
        self._lock = threading.Lock()
        self._final_message: str | None = None

    def start(self) -> Spinner:
        """Start the spinner animation."""
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def stop(self, final_message: str | None = None, success: bool = True) -> None:
        """Stop the spinner and show final state."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        char = self.style.done_char if success else self.style.fail_char
        msg = final_message or self.message
        self._clear_line()
        self._write(f"\r{char} {msg}\n")

    def update(self, message: str) -> None:
        """Update the spinner message while it's running."""
        with self._lock:
            self.message = message

    def fail(self, message: str | None = None) -> None:
        """Stop with failure indicator."""
        self.stop(final_message=message, success=False)

    def _animate(self) -> None:
        """Animation loop running in background thread."""
        while self._running:
            with self._lock:
                frame = self.style.frames[self._frame_idx % len(self.style.frames)]
                text = f"\r{self.style.prefix}{frame} {self.message}{self.style.suffix}"
            self._clear_line()
            self._write(text)
            self._frame_idx += 1
            time.sleep(self.style.interval_ms / 1000)

    def _write(self, text: str) -> None:
        if hasattr(self._stream, "write"):
            self._stream.write(text)  # type: ignore[union-attr]
            if hasattr(self._stream, "flush"):
                self._stream.flush()  # type: ignore[union-attr]

    def _clear_line(self) -> None:
        self._write("\r\033[K")

    def __enter__(self) -> Spinner:
        return self.start()

    def __exit__(self, exc_type: type | None, *args: object) -> None:
        if exc_type:
            self.fail()
        else:
            self.stop()

    @property
    def is_running(self) -> bool:
        return self._running
