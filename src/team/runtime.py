"""Team runtime lifecycle management.

Provides the high-level TeamRuntime handle for starting, monitoring,
and shutting down team sessions with coordinated workers.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state.types import (
    DEFAULT_MAX_WORKERS,
    TeamConfig,
    TeamEvent,
    TeamMonitorSnapshotState,
    TeamPhaseState,
    TeamTask,
    WorkerHeartbeat,
    WorkerInfo,
    WorkerStatus,
)
from .state.workers import (
    read_worker_heartbeat,
    read_worker_status,
    write_worker_identity,
    write_worker_inbox,
)
from .state.tasks import list_tasks
from .orchestrator import (
    AnyPhase,
    TeamPhase,
    TerminalPhase,
    is_terminal_phase,
)
from .tmux_session import (
    TeamSession,
    create_team_session,
    destroy_team_session,
    is_tmux_available,
    is_worker_alive,
    sanitize_team_name,
    send_to_worker,
    teardown_worker_panes,
    unregister_resize_hook,
    wait_for_worker_ready,
)
from .worker_bootstrap import (
    generate_initial_inbox,
    generate_shutdown_inbox,
    generate_trigger_message,
    generate_worker_overlay,
    write_team_worker_instructions_file,
    remove_team_worker_instructions_file,
)
from .role_router import load_role_prompt


# ── Team snapshot ─────────────────────────────────────────────────────────────


@dataclass
class TeamWorkerSnapshot:
    name: str
    alive: bool
    status: WorkerStatus
    heartbeat: Optional[WorkerHeartbeat]
    assigned_tasks: List[str]
    turns_without_progress: int = 0


@dataclass
class TeamTaskSummary:
    total: int = 0
    pending: int = 0
    blocked: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0
    items: List[TeamTask] = field(default_factory=list)


@dataclass
class TeamSnapshot:
    team_name: str = ""
    phase: AnyPhase = "team-plan"
    workers: List[TeamWorkerSnapshot] = field(default_factory=list)
    tasks: TeamTaskSummary = field(default_factory=TeamTaskSummary)
    all_tasks_terminal: bool = False
    dead_workers: List[str] = field(default_factory=list)
    non_reporting_workers: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# ── Team runtime handle ──────────────────────────────────────────────────────


class TeamRuntime:
    """Runtime handle returned by start_team.

    Provides methods to monitor team state, assign tasks, and shutdown.
    """

    def __init__(
        self,
        team_name: str,
        sanitized_name: str,
        session_name: str,
        config: TeamConfig,
        cwd: str,
    ):
        self.team_name = team_name
        self.sanitized_name = sanitized_name
        self.session_name = session_name
        self.config = config
        self.cwd = cwd

    @property
    def worker_count(self) -> int:
        return len(self.config.workers)

    def get_snapshot(self) -> TeamSnapshot:
        """Collect a point-in-time snapshot of the team state."""
        tasks = list_tasks(self.sanitized_name, self.cwd)
        task_summary = TeamTaskSummary(
            total=len(tasks),
            pending=sum(1 for t in tasks if t.status == "pending"),
            blocked=sum(1 for t in tasks if t.status == "blocked"),
            in_progress=sum(1 for t in tasks if t.status == "in_progress"),
            completed=sum(1 for t in tasks if t.status == "completed"),
            failed=sum(1 for t in tasks if t.status == "failed"),
            items=tasks,
        )

        worker_snapshots: List[TeamWorkerSnapshot] = []
        dead_workers: List[str] = []
        non_reporting: List[str] = []

        for w in self.config.workers:
            alive = is_worker_alive(self.session_name, w.index, w.pane_id)
            status = read_worker_status(self.sanitized_name, w.name, self.cwd)
            heartbeat = read_worker_heartbeat(self.sanitized_name, w.name, self.cwd)

            turns_without = 0
            if heartbeat and heartbeat.turn_count == 0:
                non_reporting.append(w.name)
            if not alive:
                dead_workers.append(w.name)

            worker_snapshots.append(TeamWorkerSnapshot(
                name=w.name,
                alive=alive,
                status=status,
                heartbeat=heartbeat,
                assigned_tasks=list(w.assigned_tasks),
                turns_without_progress=turns_without,
            ))

        all_terminal = all(
            t.status in ("completed", "failed") for t in tasks
        ) if tasks else False

        recommendations: List[str] = []
        if dead_workers:
            recommendations.append(
                f"Dead workers detected: {', '.join(dead_workers)}. Consider respawning."
            )
        if all_terminal and not dead_workers:
            recommendations.append("All tasks terminal. Team may be ready for shutdown.")
        if task_summary.failed > 0:
            recommendations.append(
                f"{task_summary.failed} task(s) failed. Review errors and consider re-dispatching."
            )

        phase_state = self._read_phase_state()

        return TeamSnapshot(
            team_name=self.team_name,
            phase=phase_state.current_phase if phase_state else "team-plan",
            workers=worker_snapshots,
            tasks=task_summary,
            all_tasks_terminal=all_terminal,
            dead_workers=dead_workers,
            non_reporting_workers=non_reporting,
            recommendations=recommendations,
        )

    def assign_task_to_worker(
        self,
        worker_name: str,
        task: TeamTask,
    ) -> bool:
        """Send a task to a worker via their inbox."""
        worker = next((w for w in self.config.workers if w.name == worker_name), None)
        if not worker:
            return False

        inbox = generate_initial_inbox(
            worker_name, self.sanitized_name, self.config.agent_type, [task],
        )
        write_worker_inbox(self.sanitized_name, worker_name, inbox, self.cwd)

        trigger = generate_trigger_message(worker_name, self.sanitized_name)
        return send_to_worker(
            self.session_name, worker.index, trigger, worker.pane_id
        )

    def request_shutdown(self) -> Dict[str, bool]:
        """Send shutdown requests to all workers."""
        results: Dict[str, bool] = {}
        for w in self.config.workers:
            inbox = generate_shutdown_inbox(self.sanitized_name, w.name)
            write_worker_inbox(self.sanitized_name, w.name, inbox, self.cwd)
            trigger = f"Read your inbox. Shutdown requested. Wrap up and acknowledge."
            ok = send_to_worker(self.session_name, w.index, trigger, w.pane_id)
            results[w.name] = ok
        return results

    def teardown(self) -> None:
        """Tear down the team session: kill worker panes and destroy session."""
        pane_ids = [w.pane_id for w in self.config.workers if w.pane_id]
        teardown_worker_panes(
            pane_ids,
            leader_pane_id=self.config.leader_pane_id,
            hud_pane_id=self.config.hud_pane_id,
        )
        unregister_resize_hook(
            self.config.resize_hook_name,
            self.config.resize_hook_target,
        )
        remove_team_worker_instructions_file(self.sanitized_name, self.cwd)
        destroy_team_session(self.session_name)

    def _read_phase_state(self) -> Optional[TeamPhaseState]:
        path = (
            Path(self.cwd) / ".omx" / "state" / "team"
            / self.sanitized_name / "phase.json"
        )
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TeamPhaseState(
                current_phase=data.get("current_phase", "team-plan"),
                max_fix_attempts=data.get("max_fix_attempts", 3),
                current_fix_attempt=data.get("current_fix_attempt", 0),
                transitions=data.get("transitions", []),
            )
        except (json.JSONDecodeError, OSError):
            return None

    def _write_phase_state(self, state: TeamPhaseState) -> None:
        path = (
            Path(self.cwd) / ".omx" / "state" / "team"
            / self.sanitized_name / "phase.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "current_phase": state.current_phase,
                "max_fix_attempts": state.max_fix_attempts,
                "current_fix_attempt": state.current_fix_attempt,
                "transitions": state.transitions,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }, indent=2),
            encoding="utf-8",
        )


# ── Team startup ──────────────────────────────────────────────────────────────


@dataclass
class StartTeamOptions:
    team_name: str = ""
    task_description: str = ""
    agent_type: str = "executor"
    worker_count: int = 2
    max_workers: int = DEFAULT_MAX_WORKERS
    workers: Optional[List[Dict[str, Any]]] = None
    prompts_dir: Optional[str] = None


def start_team(
    options: StartTeamOptions,
    cwd: str,
) -> TeamRuntime:
    """Start a new team with the given configuration.

    Creates a tmux session, initializes workers, writes inbox files,
    and returns a TeamRuntime handle for ongoing management.
    """
    if not is_tmux_available():
        raise RuntimeError("tmux is not available; team mode requires tmux")

    sanitized = sanitize_team_name(options.team_name)
    worker_count = max(1, min(options.worker_count, options.max_workers))

    # Create the tmux session
    session = create_team_session(sanitized, cwd, worker_count)

    # Build worker info list
    workers: List[WorkerInfo] = []
    for i in range(worker_count):
        worker_name = f"worker-{i + 1}"
        role = options.agent_type

        # Check for explicit worker config
        if options.workers and i < len(options.workers):
            wc = options.workers[i]
            role = wc.get("role", options.agent_type)

        # Try to load role prompt if prompts_dir given
        role_prompt = None
        if options.prompts_dir:
            role_prompt = load_role_prompt(role, options.prompts_dir)

        pane_id = session.worker_pane_ids[i] if i < len(session.worker_pane_ids) else None

        info = WorkerInfo(
            name=worker_name,
            index=i + 1,
            role=role,
            pane_id=pane_id,
            working_dir=cwd,
            assigned_tasks=[],
        )
        workers.append(info)
        write_worker_identity(sanitized, worker_name, info, cwd)

    # Create team config
    config = TeamConfig(
        name=sanitized,
        task=options.task_description,
        agent_type=options.agent_type,
        worker_count=worker_count,
        max_workers=options.max_workers,
        workers=workers,
        tmux_session=session.name,
        leader_pane_id=session.leader_pane_id,
        hud_pane_id=session.hud_pane_id,
        leader_cwd=cwd,
        next_worker_index=worker_count + 1,
    )

    # Persist config
    config_path = Path(cwd) / ".omx" / "state" / "team" / sanitized / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        "name": config.name,
        "task": config.task,
        "agent_type": config.agent_type,
        "worker_launch_mode": config.worker_launch_mode,
        "lifecycle_profile": config.lifecycle_profile,
        "worker_count": config.worker_count,
        "max_workers": config.max_workers,
        "workers": [w.to_dict() for w in config.workers],
        "created_at": config.created_at,
        "tmux_session": config.tmux_session,
        "next_task_id": config.next_task_id,
        "leader_cwd": config.leader_cwd,
        "leader_pane_id": config.leader_pane_id,
        "hud_pane_id": config.hud_pane_id,
        "next_worker_index": config.next_worker_index,
    }, indent=2), encoding="utf-8")

    # Write overlay / instructions
    overlay = generate_worker_overlay(sanitized)
    write_team_worker_instructions_file(sanitized, cwd, overlay)

    # Initialize phase state
    phase_path = Path(cwd) / ".omx" / "state" / "team" / sanitized / "phase.json"
    phase_path.write_text(json.dumps({
        "current_phase": "team-plan",
        "max_fix_attempts": 3,
        "current_fix_attempt": 0,
        "transitions": [],
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }, indent=2), encoding="utf-8")

    return TeamRuntime(
        team_name=options.team_name,
        sanitized_name=sanitized,
        session_name=session.name,
        config=config,
        cwd=cwd,
    )
