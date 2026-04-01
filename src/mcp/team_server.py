"""
Team Runner MCP Server.

Provides tools for spawning and managing background worker teams
via subprocess. Jobs are tracked in-memory and persisted to disk
under ~/.omx/team-jobs/ for resilience across MCP restarts.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .bootstrap import (
    McpServer,
    ToolDefinition,
    ToolResult,
    auto_start_stdio_mcp_server,
    error_result,
    text_result,
)

# ── Validation ───────────────────────────────────────────────────────────────

JOB_ID_RE = re.compile(r"^omx-[a-z0-9]{1,12}$")


def _validate_job_id(job_id: str) -> str:
    if not JOB_ID_RE.match(job_id):
        raise ValueError(f"Invalid job_id: {job_id}")
    return job_id


# ── Job state ────────────────────────────────────────────────────────────────


@dataclass
class TeamJob:
    status: str = "running"  # running | completed | failed | timeout
    result: Optional[str] = None
    stderr: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    pid: Optional[int] = None
    pane_ids: Optional[List[str]] = None
    leader_pane_id: Optional[str] = None
    team_name: Optional[str] = None
    cwd: Optional[str] = None
    cleaned_up_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TeamJob":
        return cls(
            status=d.get("status", "running"),
            result=d.get("result"),
            stderr=d.get("stderr"),
            started_at=d.get("started_at", d.get("startedAt", time.time())),
            pid=d.get("pid"),
            pane_ids=d.get("pane_ids", d.get("paneIds")),
            leader_pane_id=d.get("leader_pane_id", d.get("leaderPaneId")),
            team_name=d.get("team_name", d.get("teamName")),
            cwd=d.get("cwd"),
            cleaned_up_at=d.get("cleaned_up_at", d.get("cleanedUpAt")),
        )


def _jobs_dir() -> Path:
    d = Path.home() / ".omx" / "team-jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _persist_job(job_id: str, job: TeamJob) -> None:
    try:
        path = _jobs_dir() / f"{job_id}.json"
        path.write_text(json.dumps(job.to_dict()), "utf-8")
    except OSError:
        pass


def _load_job(job_id: str) -> Optional[TeamJob]:
    try:
        path = _jobs_dir() / f"{job_id}.json"
        if not path.exists():
            return None
        return TeamJob.from_dict(json.loads(path.read_text("utf-8")))
    except (json.JSONDecodeError, OSError):
        return None


def _load_pane_ids(job_id: str) -> Optional[Dict[str, Any]]:
    try:
        path = _jobs_dir() / f"{job_id}-panes.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text("utf-8"))
        pane_ids = [p for p in (data.get("paneIds") or []) if isinstance(p, str) and p.strip().startswith("%")]
        leader = data.get("leaderPaneId", "")
        leader = leader.strip() if isinstance(leader, str) and leader.strip().startswith("%") else ""
        return {"paneIds": pane_ids, "leaderPaneId": leader}
    except (json.JSONDecodeError, OSError):
        return None


def _parse_json_from_stdout(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if not text:
        return {"text": text}
    try:
        return {"parsed": json.loads(text), "text": text}
    except json.JSONDecodeError:
        for line in reversed(text.split("\n")):
            line = line.strip()
            if not line:
                continue
            try:
                return {"parsed": json.loads(line), "text": line}
            except json.JSONDecodeError:
                continue
    return {"text": text}


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── Kill worker panes via tmux ───────────────────────────────────────────────


def _kill_worker_panes(
    pane_ids: List[str],
    leader_pane_id: str = "",
    grace_ms: int = 10_000,
    hud_pane_id: str = "",
) -> Dict[str, Any]:
    """Send SIGTERM then SIGKILL to worker panes, excluding leader and HUD."""
    excluded_leader = 0
    excluded_hud = 0
    excluded_invalid = 0
    attempted = 0
    succeeded = 0
    failed = 0

    targets: List[str] = []
    for pid in pane_ids:
        pid = pid.strip()
        if not pid.startswith("%"):
            excluded_invalid += 1
            continue
        if pid == leader_pane_id:
            excluded_leader += 1
            continue
        if pid == hud_pane_id:
            excluded_hud += 1
            continue
        targets.append(pid)

    for pane_id in targets:
        attempted += 1
        try:
            # Send C-c first (graceful)
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "C-c", ""],
                capture_output=True,
                timeout=5,
            )
            time.sleep(min(grace_ms / 1000.0, 2.0))
            # Kill the pane
            result = subprocess.run(
                ["tmux", "kill-pane", "-t", pane_id],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                succeeded += 1
            else:
                failed += 1
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            failed += 1

    return {
        "excluded": {"leader": excluded_leader, "hud": excluded_hud, "invalid": excluded_invalid},
        "kill": {"attempted": attempted, "succeeded": succeeded, "failed": failed},
    }


# ── MCP Server ───────────────────────────────────────────────────────────────

# In-memory job registry
_jobs: Dict[str, TeamJob] = {}


class TeamServer:
    """MCP server for spawning and managing worker teams."""

    async def list_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="omx_run_team_start",
                description="Spawn CLI workers in the background. Returns jobId immediately.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "teamName": {"type": "string"},
                        "agentTypes": {"type": "array", "items": {"type": "string"}},
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "subject": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["subject", "description"],
                            },
                        },
                        "cwd": {"type": "string"},
                    },
                    "required": ["teamName", "agentTypes", "tasks", "cwd"],
                },
            ),
            ToolDefinition(
                name="omx_run_team_status",
                description="Non-blocking status check for a background job.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                    },
                    "required": ["job_id"],
                },
            ),
            ToolDefinition(
                name="omx_run_team_wait",
                description="Block until a background job reaches terminal state or times out. Uses exponential backoff.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "timeout_ms": {"type": "number"},
                        "nudge_delay_ms": {"type": "number"},
                        "nudge_max_count": {"type": "number"},
                        "nudge_message": {"type": "string"},
                        "wake_on": {"type": "string", "enum": ["terminal", "event"]},
                        "after_event_id": {"type": "string"},
                    },
                    "required": ["job_id"],
                },
            ),
            ToolDefinition(
                name="omx_run_team_cleanup",
                description="Kill all worker panes for a job without touching the leader pane.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "grace_ms": {"type": "number"},
                    },
                    "required": ["job_id"],
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        a = arguments or {}

        try:
            if name == "omx_run_team_start":
                team_name = a.get("teamName", "")
                agent_types = a.get("agentTypes", [])
                tasks = a.get("tasks", [])
                input_cwd = a.get("cwd", "")

                if not team_name or not agent_types or not tasks or not input_cwd:
                    return error_result("teamName, agentTypes, tasks, and cwd are required")

                # Generate job ID
                job_id = f"omx-{int(time.time()):x}"[-13:]  # keep short
                if not JOB_ID_RE.match(job_id):
                    job_id = f"omx-{int(time.time()) % 0xFFFFFF:06x}"

                job = TeamJob(
                    started_at=time.time(),
                    team_name=team_name,
                    cwd=input_cwd,
                )

                # Spawn worker process
                env = {**os.environ, "OMX_JOB_ID": job_id, "OMX_JOBS_DIR": str(_jobs_dir())}
                payload = json.dumps({"teamName": team_name, "agentTypes": agent_types, "tasks": tasks, "cwd": input_cwd})

                try:
                    proc = subprocess.Popen(
                        ["node", str(Path(__file__).parent.parent / "team" / "runtime-cli.js")],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                    )
                    job.pid = proc.pid
                    if proc.stdin:
                        proc.stdin.write(payload.encode("utf-8"))
                        proc.stdin.close()
                except FileNotFoundError:
                    # If node runtime isn't available, still register the job
                    # but mark it as needing an alternative runner
                    job.status = "failed"
                    job.stderr = "Worker runtime not available (node not found)"

                _jobs[job_id] = job
                _persist_job(job_id, job)

                return text_result({
                    "jobId": job_id,
                    "pid": job.pid,
                    "message": "Team started. Poll with omx_run_team_status.",
                })

            elif name == "omx_run_team_status":
                job_id = _validate_job_id(a.get("job_id", ""))
                job = _jobs.get(job_id) or _load_job(job_id)
                if not job:
                    return text_result({"error": f"No job found: {job_id}"})

                elapsed = f"{(time.time() - job.started_at):.1f}"
                out: Dict[str, Any] = {"jobId": job_id, "status": job.status, "elapsedSeconds": elapsed}

                # Check if process is still alive and update status
                if job.status == "running" and job.pid:
                    if not _is_pid_alive(job.pid):
                        job.status = "failed"
                        if not job.result:
                            job.result = json.dumps({"error": "Process no longer alive"})
                        _persist_job(job_id, job)
                        out["status"] = job.status

                if job.result:
                    try:
                        out["result"] = json.loads(job.result)
                    except (json.JSONDecodeError, TypeError):
                        out["result"] = job.result
                if job.stderr:
                    out["stderr"] = job.stderr

                return text_result(out)

            elif name == "omx_run_team_wait":
                job_id = _validate_job_id(a.get("job_id", ""))
                timeout_ms = min(a.get("timeout_ms", 300_000), 3_600_000)
                deadline = time.time() + timeout_ms / 1000.0
                poll_delay = 0.5

                import asyncio

                while time.time() < deadline:
                    job = _jobs.get(job_id) or _load_job(job_id)
                    if not job:
                        return text_result({"error": f"No job found: {job_id}"})

                    # Detect orphan PID
                    if job.status == "running" and job.pid and not _is_pid_alive(job.pid):
                        job.status = "failed"
                        if not job.result:
                            job.result = json.dumps({"error": "Process no longer alive (MCP restart?)"})
                        _persist_job(job_id, job)

                    if job.status != "running":
                        elapsed = f"{(time.time() - job.started_at):.1f}"
                        out: Dict[str, Any] = {"jobId": job_id, "status": job.status, "elapsedSeconds": elapsed}
                        if job.result:
                            try:
                                out["result"] = json.loads(job.result)
                            except (json.JSONDecodeError, TypeError):
                                out["result"] = job.result
                        if job.stderr:
                            out["stderr"] = job.stderr
                        return text_result(out)

                    await asyncio.sleep(poll_delay)
                    poll_delay = min(poll_delay * 1.5, 2.0)

                # Timeout
                elapsed = f"{(timeout_ms / 1000):.0f}"
                return text_result({
                    "error": f"Timed out waiting for job {job_id} after {elapsed}s -- workers still running",
                    "jobId": job_id,
                    "status": "running",
                })

            elif name == "omx_run_team_cleanup":
                job_id = _validate_job_id(a.get("job_id", ""))
                grace_ms = a.get("grace_ms", 10_000)
                job = _jobs.get(job_id) or _load_job(job_id)
                if not job:
                    return text_result({"error": f"Job {job_id} not found"})

                # Resolve pane IDs from disk
                panes = _load_pane_ids(job_id)
                pane_ids = panes["paneIds"] if panes else (job.pane_ids or [])
                leader = (panes["leaderPaneId"] if panes else job.leader_pane_id) or ""

                if not pane_ids:
                    return text_result({
                        "job_id": job_id,
                        "status": "noop",
                        "message": "No pane IDs recorded for this job -- nothing to clean up.",
                    })

                summary = _kill_worker_panes(pane_ids, leader, grace_ms)
                cleaned_at = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
                job.cleaned_up_at = cleaned_at
                _persist_job(job_id, job)

                return text_result({
                    "job_id": job_id,
                    "status": "cleaned" if summary["kill"]["attempted"] > 0 else "noop",
                    "kill": summary["kill"],
                    "excluded": summary["excluded"],
                    "grace_ms": grace_ms,
                    "cleaned_up_at": cleaned_at,
                })

            return error_result(f"Unknown tool: {name}")

        except Exception as e:
            return error_result(str(e))

    async def close(self) -> None:
        _jobs.clear()


def main() -> None:
    auto_start_stdio_mcp_server("team", TeamServer())


if __name__ == "__main__":
    main()
