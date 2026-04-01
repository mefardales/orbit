"""Dynamic worker scaling for team mode.

Provides scale_up (add workers mid-session) and scale_down (drain + remove idle workers).
Gated behind the ORBIT_TEAM_SCALING_ENABLED environment variable.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .state.types import (
    TeamConfig,
    TeamTask,
    WorkerInfo,
    WorkerStatus,
)
from .state.workers import (
    read_worker_status,
    write_worker_status,
    write_worker_identity,
    write_worker_inbox,
)
from .state.tasks import list_tasks
from .tmux_session import (
    TeamWorkerCli,
    is_tmux_available,
    sanitize_team_name,
    send_to_worker,
    is_worker_alive,
    get_worker_pane_pid,
    wait_for_worker_ready,
    dismiss_trust_prompt_if_present,
    teardown_worker_panes,
    build_worker_startup_command,
    _run_tmux,
)
from .worker_bootstrap import (
    generate_initial_inbox,
    generate_trigger_message,
)
from .role_router import load_role_prompt
from .worktree import (
    WorktreeMode,
    WorktreeModeDisabled,
    WorktreeModeDetached,
    WorktreeModeNamed,
    EnsureWorktreeResult,
    ensure_worktree,
    plan_worktree_target,
    rollback_provisioned_worktrees,
)


# ── Environment gate ──────────────────────────────────────────────────────────

SCALING_ENABLED_ENV = "ORBIT_TEAM_SCALING_ENABLED"


def is_scaling_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    """Check if dynamic scaling is enabled via environment variable."""
    env = env or dict(os.environ)
    raw = env.get(SCALING_ENABLED_ENV, "")
    return raw.strip().lower() in ("1", "true", "yes", "on", "enabled")


def _assert_scaling_enabled(env: Optional[Dict[str, str]] = None) -> None:
    if not is_scaling_enabled(env):
        raise RuntimeError(
            f"Dynamic scaling is disabled. Set {SCALING_ENABLED_ENV}=1 to enable."
        )


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class ScaleUpResult:
    ok: bool = True
    added_workers: List[WorkerInfo] = field(default_factory=list)
    new_worker_count: int = 0
    next_worker_index: int = 0


@dataclass
class ScaleDownResult:
    ok: bool = True
    removed_workers: List[str] = field(default_factory=list)
    new_worker_count: int = 0


@dataclass
class ScaleError:
    ok: bool = False
    error: str = ""


# ── Scale Up ──────────────────────────────────────────────────────────────────


def scale_up(
    team_name: str,
    count: int,
    agent_type: str,
    tasks: List[Dict[str, Any]],
    cwd: str,
    config: TeamConfig,
    env: Optional[Dict[str, str]] = None,
) -> Union[ScaleUpResult, ScaleError]:
    """Add workers to a running team mid-session.

    Validates capacity, creates new tmux panes, and bootstraps workers.
    """
    _assert_scaling_enabled(env)

    if not isinstance(count, int) or count < 1:
        return ScaleError(error=f"count must be a positive integer (got {count})")

    if not is_tmux_available():
        return ScaleError(error="tmux is not available")

    sanitized = sanitize_team_name(team_name)
    leader_cwd = str(Path(cwd).resolve())

    max_workers = config.max_workers
    current_count = len(config.workers)
    if current_count + count > max_workers:
        return ScaleError(
            error=f"Cannot add {count} workers: would exceed max_workers "
                  f"({current_count} + {count} > {max_workers})"
        )

    session_name = config.tmux_session
    next_index = config.next_worker_index or (current_count + 1)
    added_workers: List[WorkerInfo] = []

    persisted_tasks = list_tasks(sanitized, leader_cwd)

    for i in range(count):
        worker_index = next_index
        next_index += 1
        worker_name = f"worker-{worker_index}"

        # Create worker directory
        worker_dir = Path(leader_cwd) / ".omx" / "state" / "team" / sanitized / "workers" / worker_name
        worker_dir.mkdir(parents=True, exist_ok=True)

        # Determine worker role from task assignments
        worker_task_roles = [
            t.role for t in persisted_tasks
            if t.owner == worker_name and t.role
        ]
        unique_roles = set(worker_task_roles)
        worker_role = worker_task_roles[0] if len(unique_roles) == 1 else agent_type

        # Build startup command
        extra_env: Dict[str, str] = {}
        cmd = build_worker_startup_command(
            sanitized, worker_index, [], leader_cwd, extra_env
        )

        # Create tmux pane
        split_target = (
            config.workers[-1].pane_id if config.workers else config.leader_pane_id
        ) or ""
        split_direction = "-h" if split_target == (config.leader_pane_id or "") else "-v"

        ok, pane_output = _run_tmux([
            "split-window", split_direction,
            "-t", split_target, "-d", "-P", "-F", "#{pane_id}",
            "-c", leader_cwd, cmd,
        ])
        if not ok:
            # Rollback added workers on failure
            for w in added_workers:
                if w.pane_id:
                    _run_tmux(["kill-pane", "-t", w.pane_id])
                idx = next((j for j, ww in enumerate(config.workers) if ww.name == w.name), None)
                if idx is not None:
                    config.workers.pop(idx)
            return ScaleError(error=f"Failed to create tmux pane for {worker_name}: {pane_output}")

        pane_id = pane_output.strip().split("\n")[0].strip()
        if not pane_id or not pane_id.startswith("%"):
            return ScaleError(error=f"Failed to capture pane ID for {worker_name}")

        pane_pid = get_worker_pane_pid(session_name, worker_index, pane_id)

        worker_info = WorkerInfo(
            name=worker_name,
            index=worker_index,
            role=worker_role,
            assigned_tasks=[],
            pid=pane_pid,
            pane_id=pane_id,
            working_dir=leader_cwd,
        )

        write_worker_identity(sanitized, worker_name, worker_info, leader_cwd)

        # Wait for readiness
        timeout_ms = _resolve_ready_timeout(env or dict(os.environ))
        wait_for_worker_ready(session_name, worker_index, timeout_ms, pane_id)

        # Generate, persist, and trigger inbox
        worker_tasks = [t for t in persisted_tasks if t.owner == worker_name]
        inbox = generate_initial_inbox(
            worker_name, sanitized, agent_type, worker_tasks,
            team_state_root=f"{leader_cwd}/.omx/state",
            leader_cwd=leader_cwd,
            worker_role=worker_role,
        )
        write_worker_inbox(sanitized, worker_name, inbox, leader_cwd)

        dismiss_trust_prompt_if_present(session_name, worker_index, pane_id)
        trigger = generate_trigger_message(
            worker_name, sanitized,
            team_state_root=f"{leader_cwd}/.omx/state",
        )
        send_to_worker(session_name, worker_index, trigger, pane_id)

        added_workers.append(worker_info)
        config.workers.append(worker_info)
        config.worker_count = len(config.workers)
        config.next_worker_index = next_index

    return ScaleUpResult(
        ok=True,
        added_workers=added_workers,
        new_worker_count=config.worker_count,
        next_worker_index=next_index,
    )


# ── Scale Down ────────────────────────────────────────────────────────────────


@dataclass
class ScaleDownOptions:
    worker_names: Optional[List[str]] = None
    count: Optional[int] = None
    force: bool = False
    drain_timeout_ms: int = 30000


def scale_down(
    team_name: str,
    cwd: str,
    config: TeamConfig,
    options: Optional[ScaleDownOptions] = None,
    env: Optional[Dict[str, str]] = None,
) -> Union[ScaleDownResult, ScaleError]:
    """Remove workers from a running team.

    Sets targeted workers to 'draining' status, waits for them to finish
    current work (or force kills), then removes tmux panes and updates config.
    """
    _assert_scaling_enabled(env)
    opts = options or ScaleDownOptions()

    sanitized = sanitize_team_name(team_name)
    leader_cwd = str(Path(cwd).resolve())
    force = opts.force
    drain_timeout_ms = opts.drain_timeout_ms

    # Determine which workers to remove
    target_workers: List[WorkerInfo]
    if opts.worker_names:
        target_workers = []
        for name in opts.worker_names:
            w = next((w for w in config.workers if w.name == name), None)
            if not w:
                return ScaleError(error=f"Worker {name} not found in team {sanitized}")
            target_workers.append(w)
    else:
        count = opts.count or 1
        if not isinstance(count, int) or count < 1:
            return ScaleError(error=f"count must be a positive integer (got {count})")

        idle_workers: List[WorkerInfo] = []
        for w in config.workers:
            status = read_worker_status(sanitized, w.name, leader_cwd)
            if status.state in ("idle", "done", "unknown"):
                idle_workers.append(w)

        if len(idle_workers) < count and not force:
            return ScaleError(
                error=f"Not enough idle workers to remove: found {len(idle_workers)}, "
                      f"requested {count}. Use force=True to remove busy workers."
            )

        target_workers = idle_workers[:count]
        if force and len(target_workers) < count:
            remaining = count - len(target_workers)
            target_names = {w.name for w in target_workers}
            non_idle = [w for w in config.workers if w.name not in target_names]
            target_workers.extend(non_idle[:remaining])

    if not target_workers:
        return ScaleError(error="No workers selected for removal")

    if len(config.workers) - len(target_workers) < 1:
        return ScaleError(error="Cannot remove all workers -- at least 1 must remain")

    session_name = config.tmux_session
    removed_names: List[str] = []

    # Phase 1: Set workers to draining
    for w in target_workers:
        draining = WorkerStatus(
            state="draining",
            reason="scale_down requested by leader",
        )
        write_worker_status(sanitized, w.name, draining, leader_cwd)

    # Phase 2: Wait for drain or timeout
    if not force:
        deadline = time.monotonic() + (drain_timeout_ms / 1000.0)
        while time.monotonic() < deadline:
            all_drained = True
            for w in target_workers:
                status = read_worker_status(sanitized, w.name, leader_cwd)
                alive = is_worker_alive(session_name, w.index, w.pane_id)
                if status.state not in ("idle", "done", "draining") and alive:
                    all_drained = False
                    break
            if all_drained:
                break
            time.sleep(2.0)

    # Phase 3: Kill tmux panes
    pane_ids = [w.pane_id for w in target_workers if w.pane_id]
    teardown_worker_panes(
        pane_ids,
        leader_pane_id=config.leader_pane_id,
        hud_pane_id=config.hud_pane_id,
    )

    for w in target_workers:
        removed_names.append(w.name)

    # Phase 4: Update config
    removed_set = set(removed_names)
    config.workers = [w for w in config.workers if w.name not in removed_set]
    config.worker_count = len(config.workers)

    return ScaleDownResult(
        ok=True,
        removed_workers=removed_names,
        new_worker_count=config.worker_count,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_ready_timeout(env: Dict[str, str]) -> int:
    raw = env.get("ORBIT_TEAM_READY_TIMEOUT_MS", "")
    try:
        parsed = int(raw)
        if parsed >= 5000:
            return parsed
    except (ValueError, TypeError):
        pass
    return 45000
