"""
tmux Session Detection for Notifications

Detects the current tmux session name and pane ID for inclusion
in notification payloads.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Optional

TMUX_PANE_TARGET_RE = re.compile(r"^%\d+$")
DEFAULT_CAPTURE_LINES = 12
MAX_CAPTURE_LINES = 2000


def _should_use_pid_fallback() -> bool:
    return os.environ.get("OMX_TMUX_PID_FALLBACK") == "1"


def get_current_tmux_session() -> Optional[str]:
    """
    Get the current tmux session name.
    Checks $TMUX env first, then falls back to PID-based detection.
    """
    if os.environ.get("TMUX"):
        try:
            tmux_pane_target = os.environ.get("TMUX_PANE")
            pane_target_safe = (
                tmux_pane_target
                if tmux_pane_target and TMUX_PANE_TARGET_RE.match(tmux_pane_target)
                else None
            )
            if pane_target_safe:
                cmd = f"tmux display-message -p -t {pane_target_safe} '#S'"
            else:
                cmd = "tmux display-message -p '#S'"

            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=3,
            )
            session_name = result.stdout.strip()
            if session_name:
                return session_name
        except Exception:
            pass

    if not _should_use_pid_fallback():
        return None

    return _detect_tmux_session_by_pid()


def _detect_tmux_session_by_pid() -> Optional[str]:
    """Detect tmux session by walking the process tree."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{session_name}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        output = result.stdout.strip()
        if not output:
            return None

        pane_pids: dict[int, str] = {}
        for line in output.split("\n"):
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                try:
                    pid = int(parts[0])
                    pane_pids[pid] = parts[1]
                except ValueError:
                    continue

        if not pane_pids:
            return None

        current_pid = os.getpid()
        visited: set[int] = set()
        while current_pid > 1 and current_pid not in visited:
            visited.add(current_pid)

            if current_pid in pane_pids:
                return pane_pids[current_pid]

            try:
                ppid_result = subprocess.run(
                    ["ps", "-o", "ppid=", "-p", str(current_pid)],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                ppid = int(ppid_result.stdout.strip())
                if ppid <= 1:
                    break
                current_pid = ppid
            except Exception:
                break

        return None
    except Exception:
        return None


def get_team_tmux_sessions(team_name: str) -> list[str]:
    """List active omx-team tmux sessions for a given team."""
    sanitized = re.sub(r"[^a-zA-Z0-9-]", "", team_name)
    if not sanitized:
        return []

    prefix = f"omx-team-{sanitized}"
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return [
            s
            for s in result.stdout.strip().split("\n")
            if s == prefix or s.startswith(f"{prefix}-")
        ]
    except Exception:
        return []


def capture_tmux_pane(pane_id: Optional[str] = None, lines: int = 12) -> Optional[str]:
    """
    Capture the last N lines of output from a tmux pane.
    Returns None if capture fails or tmux is not available.
    """
    target = pane_id or os.environ.get("TMUX_PANE")
    if not target:
        return None
    if not os.environ.get("TMUX") and not pane_id:
        return None
    if not TMUX_PANE_TARGET_RE.match(target):
        return None

    safe_lines = int(lines) if isinstance(lines, (int, float)) else DEFAULT_CAPTURE_LINES
    clamped_lines = max(1, min(MAX_CAPTURE_LINES, safe_lines))

    try:
        result = subprocess.run(
            [
                "tmux", "capture-pane", "-p",
                "-t", target,
                "-S", str(-clamped_lines),
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        output = result.stdout.strip()
        return output or None
    except Exception:
        return None


def format_tmux_info() -> Optional[str]:
    """Format tmux session info for human-readable display."""
    session = get_current_tmux_session()
    if not session:
        return None
    return f"tmux: {session}"


def get_current_tmux_pane_id() -> Optional[str]:
    """
    Get the current tmux pane ID (e.g., "%0").
    Tries $TMUX_PANE env var first, then tmux display-message.
    """
    # Fast path: $TMUX_PANE is set
    env_pane = os.environ.get("TMUX_PANE")
    if os.environ.get("TMUX") and env_pane and re.match(r"^%\d+$", env_pane):
        return env_pane

    # Try tmux display-message if $TMUX is set
    if os.environ.get("TMUX"):
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{pane_id}"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            pane_id = result.stdout.strip()
            if pane_id and re.match(r"^%\d+$", pane_id):
                return pane_id
        except Exception:
            pass

    if not _should_use_pid_fallback():
        return None

    return _detect_tmux_pane_by_pid()


def _detect_tmux_pane_by_pid() -> Optional[str]:
    """Detect tmux pane ID by walking the process tree."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{pane_id}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        output = result.stdout.strip()
        if not output:
            return None

        pane_pids: dict[int, str] = {}
        for line in output.split("\n"):
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                try:
                    pid = int(parts[0])
                    pane_pids[pid] = parts[1]
                except ValueError:
                    continue

        if not pane_pids:
            return None

        current_pid = os.getpid()
        visited: set[int] = set()
        while current_pid > 1 and current_pid not in visited:
            visited.add(current_pid)
            if current_pid in pane_pids:
                return pane_pids[current_pid]
            try:
                ppid_result = subprocess.run(
                    ["ps", "-o", "ppid=", "-p", str(current_pid)],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                ppid = int(ppid_result.stdout.strip())
                if ppid <= 1:
                    break
                current_pid = ppid
            except Exception:
                break

        return None
    except Exception:
        return None
