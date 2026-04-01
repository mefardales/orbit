"""Tmux session management for team workers.

Provides creation, teardown, and interaction with tmux sessions
used to host worker processes in separate panes.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple


# ── Constants ─────────────────────────────────────────────────────────────────

INJECTION_MARKER = "[PYCLAUDE_TMUX_INJECT]"
TEAM_SESSION_PREFIX = "pyclaude-team-"

TeamWorkerCli = Literal["codex", "claude", "gemini"]
TeamWorkerLaunchMode = Literal["interactive", "prompt"]


# ── Session dataclass ─────────────────────────────────────────────────────────


@dataclass
class TeamSession:
    """Represents a tmux session for a team."""
    name: str  # tmux target in "session:window" form
    worker_count: int = 0
    cwd: str = ""
    worker_pane_ids: List[str] = field(default_factory=list)
    leader_pane_id: str = ""
    hud_pane_id: Optional[str] = None
    resize_hook_name: Optional[str] = None
    resize_hook_target: Optional[str] = None


@dataclass
class TmuxPaneInfo:
    pane_id: str
    current_command: str = ""
    start_command: str = ""


@dataclass
class WorkerProcessLaunchSpec:
    worker_cli: TeamWorkerCli = "claude"
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


# ── Tmux availability ────────────────────────────────────────────────────────


def is_tmux_available() -> bool:
    """Check if tmux is available on the system."""
    return shutil.which("tmux") is not None


def _run_tmux(args: List[str]) -> Tuple[bool, str]:
    """Run a tmux command. Returns (success, stdout_or_stderr)."""
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or f"tmux exited {result.returncode}"
    except FileNotFoundError:
        return False, "tmux not found"
    except OSError as e:
        return False, str(e)


# ── Session name helpers ──────────────────────────────────────────────────────


def sanitize_team_name(name: str) -> str:
    """Sanitize a team name for use in tmux session names."""
    sanitized = re.sub(r"[^a-z0-9-]", "-", name.lower())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized[:30] or "team"


def build_session_name(team_name: str) -> str:
    """Build a tmux session name from a team name."""
    return f"{TEAM_SESSION_PREFIX}{sanitize_team_name(team_name)}"


# ── Pane listing ──────────────────────────────────────────────────────────────


def list_panes(target: str) -> List[TmuxPaneInfo]:
    """List all panes in a tmux session/window."""
    ok, output = _run_tmux([
        "list-panes", "-t", target, "-F",
        "#{pane_id}\t#{pane_current_command}\t#{pane_start_command}",
    ])
    if not ok:
        return []

    panes: List[TmuxPaneInfo] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        pane_id = parts[0] if len(parts) > 0 else ""
        current_cmd = parts[1] if len(parts) > 1 else ""
        start_cmd = parts[2] if len(parts) > 2 else ""
        if pane_id.startswith("%"):
            panes.append(TmuxPaneInfo(
                pane_id=pane_id,
                current_command=current_cmd,
                start_command=start_cmd,
            ))
    return panes


# ── Session creation ──────────────────────────────────────────────────────────


def create_team_session(
    team_name: str,
    cwd: str,
    worker_count: int,
) -> TeamSession:
    """Create a new tmux session with the leader pane and worker panes.

    Returns a TeamSession with all pane IDs populated.
    """
    if not is_tmux_available():
        raise RuntimeError("tmux is not available")

    session_name = build_session_name(team_name)

    # Create the session with the leader pane
    ok, output = _run_tmux([
        "new-session", "-d", "-s", session_name,
        "-x", "220", "-y", "50",
        "-c", cwd,
        "-P", "-F", "#{pane_id}",
    ])
    if not ok:
        raise RuntimeError(f"Failed to create tmux session: {output}")

    leader_pane_id = output.strip().split("\n")[0].strip()
    target = f"{session_name}:0"

    # Create worker panes via split-window
    worker_pane_ids: List[str] = []
    split_target = leader_pane_id

    for i in range(worker_count):
        direction = "-h" if i == 0 else "-v"
        ok, pane_output = _run_tmux([
            "split-window", direction,
            "-t", split_target,
            "-d", "-P", "-F", "#{pane_id}",
            "-c", cwd,
        ])
        if not ok:
            # Clean up on failure
            _run_tmux(["kill-session", "-t", session_name])
            raise RuntimeError(f"Failed to create worker pane {i}: {pane_output}")

        pane_id = pane_output.strip().split("\n")[0].strip()
        worker_pane_ids.append(pane_id)
        split_target = pane_id

    # Apply tiled layout for even distribution
    if worker_count > 1:
        _run_tmux(["select-layout", "-t", target, "tiled"])

    return TeamSession(
        name=target,
        worker_count=worker_count,
        cwd=cwd,
        worker_pane_ids=worker_pane_ids,
        leader_pane_id=leader_pane_id,
    )


# ── Worker interaction ────────────────────────────────────────────────────────


def send_to_worker(
    session_name: str,
    worker_index: int,
    message: str,
    pane_id: Optional[str] = None,
    worker_cli: Optional[TeamWorkerCli] = None,
) -> bool:
    """Send a message to a worker pane via tmux send-keys."""
    target = pane_id or f"{session_name}:{worker_index}"
    # Escape special characters for tmux
    escaped = message.replace("\\", "\\\\").replace(";", "\\;")
    ok, _ = _run_tmux(["send-keys", "-t", target, escaped, "Enter"])
    return ok


def send_to_worker_stdin(
    session_name: str,
    worker_index: int,
    message: str,
    pane_id: Optional[str] = None,
) -> bool:
    """Send a message by piping to the worker's stdin."""
    target = pane_id or f"{session_name}:{worker_index}"
    ok, _ = _run_tmux([
        "send-keys", "-t", target, "-l", message,
    ])
    if ok:
        _run_tmux(["send-keys", "-t", target, "Enter"])
    return ok


def is_worker_alive(
    session_name: str,
    worker_index: int,
    pane_id: Optional[str] = None,
) -> bool:
    """Check if a worker pane is still active."""
    target = pane_id or f"{session_name}:{worker_index}"
    ok, output = _run_tmux([
        "list-panes", "-t", target.split(":")[0], "-F", "#{pane_id} #{pane_dead}",
    ])
    if not ok:
        return False
    check_id = pane_id or target
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == check_id:
            return parts[1] != "1"
    return False


def get_worker_pane_pid(
    session_name: str,
    worker_index: int,
    pane_id: Optional[str] = None,
) -> Optional[int]:
    """Get the PID of the process running in a worker pane."""
    target = pane_id or f"{session_name}:{worker_index}"
    ok, output = _run_tmux([
        "display-message", "-t", target, "-p", "#{pane_pid}",
    ])
    if not ok:
        return None
    try:
        return int(output.strip())
    except ValueError:
        return None


# ── Worker readiness ──────────────────────────────────────────────────────────


def wait_for_worker_ready(
    session_name: str,
    worker_index: int,
    timeout_ms: int = 45000,
    pane_id: Optional[str] = None,
) -> bool:
    """Wait for a worker pane to be ready (showing a prompt or idle state).

    Polls the pane content periodically until timeout.
    """
    target = pane_id or f"{session_name}:{worker_index}"
    deadline = time.monotonic() + (timeout_ms / 1000.0)

    while time.monotonic() < deadline:
        ok, output = _run_tmux([
            "capture-pane", "-t", target, "-p", "-J",
        ])
        if ok:
            content = output.strip()
            # Look for common readiness indicators
            if any(indicator in content.lower() for indicator in [
                "$", ">", "ready", "initialized", "waiting",
            ]):
                return True
        time.sleep(1.0)

    return False


def dismiss_trust_prompt_if_present(
    session_name: str,
    worker_index: int,
    pane_id: Optional[str] = None,
) -> bool:
    """Dismiss a trust/permission prompt if present in the worker pane."""
    target = pane_id or f"{session_name}:{worker_index}"
    ok, output = _run_tmux([
        "capture-pane", "-t", target, "-p", "-J",
    ])
    if not ok:
        return False

    content = output.lower()
    if "trust" in content or "permission" in content or "allow" in content:
        _run_tmux(["send-keys", "-t", target, "y", "Enter"])
        time.sleep(1.0)
        return True
    return False


# ── Build startup command ─────────────────────────────────────────────────────


def build_worker_startup_command(
    team_name: str,
    worker_index: int,
    launch_args: List[str],
    cwd: str,
    extra_env: Optional[Dict[str, str]] = None,
    worker_cli: TeamWorkerCli = "claude",
) -> str:
    """Build the shell command string to start a worker in a tmux pane."""
    env_parts: List[str] = []
    if extra_env:
        for k, v in extra_env.items():
            env_parts.append(f"export {k}={_shell_quote(v)}")

    env_prefix = " && ".join(env_parts) + " && " if env_parts else ""
    args_str = " ".join(_shell_quote(a) for a in launch_args)

    return f"{env_prefix}cd {_shell_quote(cwd)} && {worker_cli} {args_str}"


def _shell_quote(s: str) -> str:
    """Quote a string for safe shell use."""
    if not s:
        return "''"
    if re.match(r"^[a-zA-Z0-9._/=-]+$", s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ── Teardown ──────────────────────────────────────────────────────────────────


def teardown_worker_panes(
    pane_ids: List[str],
    leader_pane_id: Optional[str] = None,
    hud_pane_id: Optional[str] = None,
) -> None:
    """Kill worker panes, preserving leader and HUD panes."""
    protected = {leader_pane_id, hud_pane_id} - {None}
    for pane_id in pane_ids:
        if pane_id in protected:
            continue
        _run_tmux(["kill-pane", "-t", pane_id])


def kill_worker_by_pane_id(pane_id: str) -> bool:
    """Kill a specific tmux pane."""
    ok, _ = _run_tmux(["kill-pane", "-t", pane_id])
    return ok


def destroy_team_session(session_name: str) -> bool:
    """Destroy an entire tmux session."""
    base = session_name.split(":")[0]
    ok, _ = _run_tmux(["kill-session", "-t", base])
    return ok


def unregister_resize_hook(hook_name: Optional[str], target: Optional[str]) -> None:
    """Unregister a tmux resize hook if set."""
    if not hook_name or not target:
        return
    _run_tmux([
        "set-hook", "-t", target, "-u", hook_name,
    ])


def list_team_sessions() -> List[str]:
    """List all active team tmux sessions."""
    ok, output = _run_tmux(["list-sessions", "-F", "#{session_name}"])
    if not ok:
        return []
    return [
        name for name in output.splitlines()
        if name.strip().startswith(TEAM_SESSION_PREFIX)
    ]
