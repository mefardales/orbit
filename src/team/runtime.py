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
from .state.tasks import list_tasks, _write_task
from .orchestrator import (
    AnyPhase,
    TeamPhase,
    TerminalPhase,
    is_terminal_phase,
    transition_phase,
    create_team_state,
    get_phase_instructions,
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
    dismiss_trust_prompt_if_present,
    build_worker_startup_command,
)
from .worker_bootstrap import (
    generate_initial_inbox,
    generate_shutdown_inbox,
    generate_trigger_message,
    generate_worker_overlay,
    write_team_worker_instructions_file,
    write_worker_role_instructions_file,
    remove_team_worker_instructions_file,
)
from .role_router import load_role_prompt, route_task_to_role


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

    def advance_phase(self, to: AnyPhase, reason: Optional[str] = None) -> bool:
        """Transition the team to the next phase.

        Updates the persisted phase state and returns True on success.
        Raises ValueError if the transition is invalid.
        """
        current = self._read_phase_state()
        if not current:
            return False

        # Build a minimal TeamState from persisted phase state so we can
        # validate the transition using orchestrator rules.
        from .orchestrator import TeamState, transition_phase as _tp
        state = TeamState(
            active=not is_terminal_phase(current.current_phase),
            phase=current.current_phase,  # type: ignore[arg-type]
            task_description=self.config.task,
            max_fix_attempts=current.max_fix_attempts,
            current_fix_attempt=current.current_fix_attempt,
        )

        next_state = _tp(state, to, reason)
        self._write_phase_state(TeamPhaseState(
            current_phase=next_state.phase,
            max_fix_attempts=next_state.max_fix_attempts,
            current_fix_attempt=next_state.current_fix_attempt,
            transitions=[t.to_dict() for t in next_state.phase_transitions],
        ))
        return True

    def request_shutdown(self) -> Dict[str, bool]:
        """Send shutdown requests to all workers."""
        results: Dict[str, bool] = {}
        for w in self.config.workers:
            inbox = generate_shutdown_inbox(self.sanitized_name, w.name)
            write_worker_inbox(self.sanitized_name, w.name, inbox, self.cwd)
            trigger = "Read your inbox. Shutdown requested. Wrap up and acknowledge."
            ok = send_to_worker(self.session_name, w.index, trigger, w.pane_id)
            results[w.name] = ok
        return results

    def stop_team(self, *, graceful: bool = True, timeout_ms: int = 30000) -> Dict[str, Any]:
        """Stop the team: optionally send shutdown signals, then tear down.

        Args:
            graceful: If True, send shutdown requests to workers and wait up
                      to timeout_ms for them to acknowledge before killing.
            timeout_ms: Maximum milliseconds to wait for graceful drain.

        Returns a dict summarising what was stopped and any errors.
        """
        result: Dict[str, Any] = {
            "team_name": self.team_name,
            "graceful": graceful,
            "shutdown_sent": {},
            "errors": [],
        }

        if graceful:
            try:
                result["shutdown_sent"] = self.request_shutdown()
            except Exception as exc:
                result["errors"].append(f"shutdown_request_error: {exc}")

            # Wait for all workers to reach an idle/done state or until timeout.
            deadline = time.monotonic() + (timeout_ms / 1000.0)
            while time.monotonic() < deadline:
                all_quiet = True
                for w in self.config.workers:
                    status = read_worker_status(self.sanitized_name, w.name, self.cwd)
                    alive = is_worker_alive(self.session_name, w.index, w.pane_id)
                    if alive and status.state not in ("idle", "done", "failed", "unknown"):
                        all_quiet = False
                        break
                if all_quiet:
                    break
                time.sleep(2.0)

        try:
            self.teardown()
        except Exception as exc:
            result["errors"].append(f"teardown_error: {exc}")

        return result

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

    # ── Task decomposition ────────────────────────────────────────────────────

    def decompose_prompt_to_tasks(
        self,
        prompt: str,
        roles: Optional[List[str]] = None,
    ) -> List[TeamTask]:
        """Decompose a prompt into per-worker tasks and write them to disk.

        Each worker gets a task routed to it via the RoleRouter. Tasks are
        persisted under .omx/state/team/<name>/tasks/ and assigned to workers
        round-robin by index.

        Args:
            prompt: The overall task description to decompose.
            roles: Optional list of explicit role names to use, one per worker.
                   Defaults to routing each worker independently via heuristics.

        Returns the list of created TeamTask objects.
        """
        from .state.tasks import _write_task
        from .orchestrator import TeamPhase

        workers = self.config.workers
        if not workers:
            return []

        phase_state = self._read_phase_state()
        current_phase: Optional[TeamPhase] = None
        if phase_state and not is_terminal_phase(phase_state.current_phase):
            current_phase = phase_state.current_phase  # type: ignore[assignment]

        tasks: List[TeamTask] = []
        now_iso = datetime.utcnow().isoformat() + "Z"
        next_task_id = self.config.next_task_id

        for i, worker in enumerate(workers):
            role = (roles[i] if roles and i < len(roles) else None) or worker.role

            # Use the role router to get the best role for this task slice.
            # For decomposition we give each worker a slice of the full prompt.
            routing = route_task_to_role(
                task_subject=prompt[:120],
                task_description=prompt,
                phase=current_phase,
                fallback_role=role or self.config.agent_type,
            )
            effective_role = routing.role if routing.confidence != "low" else (role or self.config.agent_type)

            task = TeamTask(
                id=str(next_task_id),
                subject=f"Worker {worker.name}: {prompt[:80]}",
                description=prompt,
                status="pending",
                role=effective_role,
                owner=worker.name,
                requires_code_change=True,
                created_at=now_iso,
            )
            _write_task(self.sanitized_name, str(next_task_id), self.cwd, task)

            # Track on worker info
            if str(next_task_id) not in worker.assigned_tasks:
                worker.assigned_tasks.append(str(next_task_id))
                write_worker_identity(self.sanitized_name, worker.name, worker, self.cwd)

            tasks.append(task)
            next_task_id += 1

        # Persist incremented task counter
        self.config.next_task_id = next_task_id
        self._persist_config()

        return tasks

    def _persist_config(self) -> None:
        config_path = (
            Path(self.cwd) / ".omx" / "state" / "team"
            / self.sanitized_name / "config.json"
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            "name": self.config.name,
            "task": self.config.task,
            "agent_type": self.config.agent_type,
            "worker_launch_mode": self.config.worker_launch_mode,
            "lifecycle_profile": self.config.lifecycle_profile,
            "worker_count": self.config.worker_count,
            "max_workers": self.config.max_workers,
            "workers": [w.to_dict() for w in self.config.workers],
            "created_at": self.config.created_at,
            "tmux_session": self.config.tmux_session,
            "next_task_id": self.config.next_task_id,
            "leader_cwd": self.config.leader_cwd,
            "leader_pane_id": self.config.leader_pane_id,
            "hud_pane_id": self.config.hud_pane_id,
            "next_worker_index": self.config.next_worker_index,
        }, indent=2), encoding="utf-8")

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
    # If True, start_team will also decompose the task and send worker triggers.
    auto_dispatch: bool = True
    # Timeout in ms to wait for each worker shell to be ready before sending inbox.
    ready_timeout_ms: int = 45000


def start_team(
    options: StartTeamOptions,
    cwd: str,
) -> TeamRuntime:
    """Start a new team with the given configuration.

    Creates a tmux session, initialises workers, writes inbox files,
    bootstraps each worker with their task assignment, optionally waits
    for readiness, and returns a TeamRuntime handle for ongoing management.

    Raises RuntimeError if tmux is unavailable or session creation fails.
    """
    if not is_tmux_available():
        raise RuntimeError("tmux is not available; team mode requires tmux")

    sanitized = sanitize_team_name(options.team_name)
    worker_count = max(1, min(options.worker_count, options.max_workers))
    cwd_resolved = str(Path(cwd).resolve())

    # ── 1. Create tmux session ────────────────────────────────────────────────
    session = create_team_session(sanitized, cwd_resolved, worker_count)

    # ── 2. Build worker info list ──────────────────────────────────────────────
    workers: List[WorkerInfo] = []
    for i in range(worker_count):
        worker_name = f"worker-{i + 1}"
        role = options.agent_type

        # Explicit per-worker config overrides
        explicit_role_prompt: Optional[str] = None
        if options.workers and i < len(options.workers):
            wc = options.workers[i]
            role = wc.get("role", options.agent_type)

        # Load role prompt from prompts_dir if available
        role_prompt_content: Optional[str] = None
        if options.prompts_dir:
            role_prompt_content = load_role_prompt(role, options.prompts_dir)

        pane_id = session.worker_pane_ids[i] if i < len(session.worker_pane_ids) else None

        info = WorkerInfo(
            name=worker_name,
            index=i + 1,
            role=role,
            pane_id=pane_id,
            working_dir=cwd_resolved,
            assigned_tasks=[],
        )
        workers.append(info)

        # Persist identity before writing inbox so workers can self-identify
        write_worker_identity(sanitized, worker_name, info, cwd_resolved)

    # ── 3. Create team config ─────────────────────────────────────────────────
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
        leader_cwd=cwd_resolved,
        next_worker_index=worker_count + 1,
    )

    # ── 4. Write overlay / team instructions file ─────────────────────────────
    overlay = generate_worker_overlay(sanitized)
    instructions_path = write_team_worker_instructions_file(
        sanitized, cwd_resolved, overlay
    )

    # ── 5. Initialise phase state ─────────────────────────────────────────────
    phase_path = (
        Path(cwd_resolved) / ".omx" / "state" / "team" / sanitized / "phase.json"
    )
    phase_path.parent.mkdir(parents=True, exist_ok=True)
    phase_path.write_text(json.dumps({
        "current_phase": "team-plan",
        "max_fix_attempts": 3,
        "current_fix_attempt": 0,
        "transitions": [],
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }, indent=2), encoding="utf-8")

    # ── 6. Persist config ─────────────────────────────────────────────────────
    config_path = (
        Path(cwd_resolved) / ".omx" / "state" / "team" / sanitized / "config.json"
    )
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

    # ── 7. Build the runtime handle ───────────────────────────────────────────
    runtime = TeamRuntime(
        team_name=options.team_name,
        sanitized_name=sanitized,
        session_name=session.name,
        config=config,
        cwd=cwd_resolved,
    )

    # ── 8. Bootstrap workers with inbox + trigger ─────────────────────────────
    if options.auto_dispatch and options.task_description:
        # Decompose the task into per-worker assignments
        tasks = runtime.decompose_prompt_to_tasks(options.task_description)

        for i, worker in enumerate(workers):
            worker_tasks = [t for t in tasks if t.owner == worker.name]

            # Write per-worker role instructions if we have a role prompt
            role_prompt_content = None
            if options.prompts_dir:
                role_prompt_content = load_role_prompt(worker.role, options.prompts_dir)
                if role_prompt_content:
                    write_worker_role_instructions_file(
                        sanitized,
                        worker.name,
                        cwd_resolved,
                        instructions_path,
                        worker.role,
                        role_prompt_content,
                    )

            # Generate and write inbox content
            inbox_content = generate_initial_inbox(
                worker.name,
                sanitized,
                options.agent_type,
                worker_tasks,
                team_state_root=f"{cwd_resolved}/.omx/state",
                leader_cwd=cwd_resolved,
                worker_role=worker.role,
                role_prompt_content=role_prompt_content,
            )
            write_worker_inbox(sanitized, worker.name, inbox_content, cwd_resolved)

        # Wait for panes to show a prompt, then dismiss any trust prompts and send triggers
        for i, worker in enumerate(workers):
            pane_id = worker.pane_id
            worker_index = worker.index

            # Wait for the shell to be ready
            wait_for_worker_ready(
                session.name, worker_index, options.ready_timeout_ms, pane_id
            )
            dismiss_trust_prompt_if_present(session.name, worker_index, pane_id)

            # Send the trigger message to wake the worker
            trigger = generate_trigger_message(
                worker.name,
                sanitized,
                team_state_root=f"{cwd_resolved}/.omx/state",
            )
            send_to_worker(session.name, worker_index, trigger, pane_id)

    return runtime


# ── Module-level stop_team ────────────────────────────────────────────────────


def stop_team(
    runtime: TeamRuntime,
    *,
    graceful: bool = True,
    timeout_ms: int = 30000,
) -> Dict[str, Any]:
    """Stop a running team.

    Convenience wrapper around :meth:`TeamRuntime.stop_team` for callers
    that want a plain function rather than a method call.

    Args:
        runtime: The handle returned by :func:`start_team`.
        graceful: Send shutdown signals and wait for workers to drain first.
        timeout_ms: Maximum wait time in milliseconds before force-killing.

    Returns a summary dict with keys ``team_name``, ``graceful``,
    ``shutdown_sent`` (dict of worker -> bool), and ``errors`` (list of str).
    """
    return runtime.stop_team(graceful=graceful, timeout_ms=timeout_ms)
