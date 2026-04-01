"""Error types for sparkshell."""

from __future__ import annotations

import errno


class SparkshellError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind

    @classmethod
    def invalid_args(cls, message: str) -> SparkshellError:
        return cls("invalid_args", message)

    @classmethod
    def io_error(cls, exc: OSError) -> SparkshellError:
        return cls("io", str(exc))

    @classmethod
    def summary_timeout(cls, timeout_ms: int) -> SparkshellError:
        return cls("summary_timeout", f"codex summary timed out after {timeout_ms}ms")

    @classmethod
    def summary_bridge(cls, message: str) -> SparkshellError:
        return cls("summary_bridge", message)

    def raw_exit_code(self) -> int:
        if self.kind == "invalid_args":
            return 2
        if self.kind == "io":
            return 1
        return 1
