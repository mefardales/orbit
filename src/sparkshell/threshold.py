"""Line-count threshold logic for deciding raw vs summarized output."""

from __future__ import annotations

import os

DEFAULT_MAX_VISIBLE_LINES = 12


def read_line_threshold() -> int:
    raw = os.environ.get("PYCLAUDE_SPARKSHELL_LINES", "")
    try:
        val = int(raw.strip())
        return val if val > 0 else DEFAULT_MAX_VISIBLE_LINES
    except ValueError:
        return DEFAULT_MAX_VISIBLE_LINES


def count_visible_lines(data: bytes) -> int:
    if not data:
        return 0
    return len(data.decode("utf-8", errors="replace").splitlines())


def combined_visible_lines(stdout: bytes, stderr: bytes) -> int:
    return count_visible_lines(stdout) + count_visible_lines(stderr)
