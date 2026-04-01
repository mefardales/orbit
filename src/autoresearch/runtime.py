"""
Autoresearch runtime module.

Ported from oh-my-codex src/autoresearch/runtime.ts.
Manages the lifecycle of autoresearch experiment runs: preparation,
candidate processing, evaluation, decision logic, and finalization.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from .contracts import (
    AutoresearchEvaluatorResult,
    AutoresearchKeepPolicy,
    AutoresearchMissionContract,
    ContractError,
    parse_evaluator_result,
)

# ---------------------------------------------------------------------------
# Status type aliases
# ---------------------------------------------------------------------------

AutoresearchCandidateStatus = Literal[
    "candidate", "noop", "abort", "interrupted"
]

AutoresearchDecisionStatus = Literal[
    "baseline", "keep", "discard", "ambiguous",
    "noop", "abort", "interrupted", "error",
]

AutoresearchRunStatus = Literal[
    "running", "stopped", "completed", "failed"
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PreparedAutoresearchRuntime:
    """Paths and identifiers for a fully prepared autoresearch run."""

    run_id: str = ""
    run_tag: str = ""
    run_dir: str = ""
    instructions_file: str = ""
    manifest_file: str = ""
    ledger_file: str = ""
    latest_evaluator_file: str = ""
    results_file: str = ""
    state_file: str = ""
    candidate_file: str = ""
    repo_root: str = ""
    worktree_path: str = ""
    task_description: str = ""


@dataclass
class AutoresearchEvaluationRecord:
    """Record of a single evaluator invocation."""

    command: str = ""
    ran_at: str = ""
    status: Literal["pass", "fail", "error"] = "error"
    pass_: Optional[bool] = None
    score: Optional[float] = None
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    parse_error: Optional[str] = None


@dataclass
class AutoresearchCandidateArtifact:
    """JSON contract defining a proposed change from the experiment worker."""

    status: AutoresearchCandidateStatus = "noop"
    candidate_commit: Optional[str] = None
    base_commit: str = ""
    description: str = ""
    notes: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class AutoresearchLedgerEntry:
    """Immutable iteration history entry."""

    iteration: int = 0
    kind: Literal["baseline", "iteration"] = "iteration"
    decision: AutoresearchDecisionStatus = "error"
    decision_reason: str = ""
    candidate_status: str = ""  # AutoresearchCandidateStatus | "baseline"
    base_commit: str = ""
    candidate_commit: Optional[str] = None
    kept_commit: str = ""
    keep_policy: AutoresearchKeepPolicy = "score_improvement"
    evaluator: Optional[AutoresearchEvaluationRecord] = None
    created_at: str = ""
    notes: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class AutoresearchRunManifest:
    """Comprehensive run state persisted as JSON."""

    schema_version: int = 1
    run_id: str = ""
    run_tag: str = ""
    mission_dir: str = ""
    mission_file: str = ""
    sandbox_file: str = ""
    repo_root: str = ""
    worktree_path: str = ""
    mission_slug: str = ""
    branch_name: str = ""
    baseline_commit: str = ""
    last_kept_commit: str = ""
    last_kept_score: Optional[float] = None
    latest_candidate_commit: Optional[str] = None
    results_file: str = ""
    instructions_file: str = ""
    manifest_file: str = ""
    ledger_file: str = ""
    latest_evaluator_file: str = ""
    candidate_file: str = ""
    evaluator: Any = None  # AutoresearchEvaluatorContract dict
    keep_policy: AutoresearchKeepPolicy = "score_improvement"
    status: AutoresearchRunStatus = "running"
    stop_reason: Optional[str] = None
    iteration: int = 0
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None


@dataclass
class _AutoresearchActiveRunState:
    schema_version: int = 1
    active: bool = False
    run_id: Optional[str] = None
    mission_slug: Optional[str] = None
    repo_root: str = ""
    worktree_path: Optional[str] = None
    status: str = "idle"  # AutoresearchRunStatus | "idle"
    updated_at: str = ""
    completed_at: Optional[str] = None


@dataclass
class _AutoresearchDecision:
    decision: AutoresearchDecisionStatus = "error"
    decision_reason: str = ""
    keep: bool = False
    evaluator: Optional[AutoresearchEvaluationRecord] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class _InstructionLedgerSummary:
    iteration: int = 0
    decision: AutoresearchDecisionStatus = "error"
    reason: str = ""
    kept_commit: str = ""
    candidate_commit: Optional[str] = None
    evaluator_status: Optional[str] = None
    evaluator_score: Optional[float] = None
    description: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RESULTS_HEADER = "iteration\tcommit\tpass\tscore\tstatus\tdescription\n"
_WORKTREE_EXCLUDES = ["results.tsv", "run.log", "node_modules", ".omx/"]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_autoresearch_run_tag(date: Optional[datetime] = None) -> str:
    """Build a compact ISO-style run tag, e.g. ``20260401T123456Z``."""
    dt = date or datetime.now(timezone.utc)
    iso = dt.strftime("%Y%m%dT%H%M%SZ")
    return iso


def _build_run_id(mission_slug: str, run_tag: str) -> str:
    return f"{mission_slug}-{run_tag.lower()}"


def _active_run_state_file(project_root: str) -> str:
    return str(Path(project_root) / ".omx" / "state" / "autoresearch-state.json")


def _trim_content(value: str, max_len: int = 4000) -> str:
    trimmed = value.strip()
    if len(trimmed) <= max_len:
        return trimmed
    return trimmed[:max_len] + "\n..."


def _read_git(repo_path: str, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed") from exc


def _try_resolve_git_commit(worktree_path: str, ref: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    resolved = (result.stdout or "").strip()
    return resolved or None


def _read_git_short_head(worktree_path: str) -> str:
    return _read_git(worktree_path, ["rev-parse", "--short=7", "HEAD"])


def _read_git_full_head(worktree_path: str) -> str:
    return _read_git(worktree_path, ["rev-parse", "HEAD"])


def _require_git_success(worktree_path: str, args: list[str]) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    raise RuntimeError(
        (result.stderr or "").strip() or f"git {' '.join(args)} failed"
    )


def _git_status_lines(worktree_path: str) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or "").strip()
            or f"git status failed for {worktree_path}"
        )
    return [
        line.rstrip()
        for line in (result.stdout or "").split("\n")
        if line.strip()
    ]


def _is_allowed_runtime_dirty_line(line: str) -> bool:
    trimmed = line.strip()
    if len(trimmed) < 4:
        return False
    path = trimmed[3:].strip()
    if not trimmed.startswith("?? "):
        return False
    for exclude in _WORKTREE_EXCLUDES:
        if exclude.endswith("/"):
            if path.startswith(exclude) or path == exclude[:-1]:
                return True
        elif path == exclude:
            return True
    return False


def assert_reset_safe_worktree(worktree_path: str) -> None:
    """Verify the worktree has no uncommitted changes outside runtime dirs."""
    lines = _git_status_lines(worktree_path)
    blocking = [l for l in lines if not _is_allowed_runtime_dirty_line(l)]
    if not blocking:
        return
    raise RuntimeError(
        f"autoresearch_reset_requires_clean_worktree:{worktree_path}:"
        f"{' | '.join(blocking)}"
    )


async def _ensure_parent_dir(file_path: str) -> None:
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)


async def _write_json_file(file_path: str, value: Any) -> None:
    await _ensure_parent_dir(file_path)
    Path(file_path).write_text(
        json.dumps(value, indent=2) + "\n", encoding="utf-8"
    )


async def _read_json_file(file_path: str) -> Any:
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Active run state
# ---------------------------------------------------------------------------


async def _read_active_run_state(
    project_root: str,
) -> Optional[_AutoresearchActiveRunState]:
    f = _active_run_state_file(project_root)
    if not Path(f).exists():
        return None
    data = await _read_json_file(f)
    return _AutoresearchActiveRunState(**{
        k: v for k, v in data.items()
        if k in _AutoresearchActiveRunState.__dataclass_fields__
    })


async def _write_active_run_state(
    project_root: str, value: _AutoresearchActiveRunState
) -> None:
    from dataclasses import asdict
    await _write_json_file(
        _active_run_state_file(project_root), asdict(value)
    )


async def _assert_lock_available(project_root: str) -> None:
    state = await _read_active_run_state(project_root)
    if state and state.active and state.run_id:
        raise RuntimeError(
            f"autoresearch_active_run_exists:{state.run_id}"
        )


async def _activate_run(manifest: AutoresearchRunManifest) -> None:
    await _write_active_run_state(
        manifest.repo_root,
        _AutoresearchActiveRunState(
            active=True,
            run_id=manifest.run_id,
            mission_slug=manifest.mission_slug,
            repo_root=manifest.repo_root,
            worktree_path=manifest.worktree_path,
            status=manifest.status,
            updated_at=_now_iso(),
        ),
    )


async def _deactivate_run(manifest: AutoresearchRunManifest) -> None:
    previous = await _read_active_run_state(manifest.repo_root)
    await _write_active_run_state(
        manifest.repo_root,
        _AutoresearchActiveRunState(
            active=False,
            run_id=(previous.run_id if previous else None) or manifest.run_id,
            mission_slug=(
                (previous.mission_slug if previous else None)
                or manifest.mission_slug
            ),
            repo_root=manifest.repo_root,
            worktree_path=(
                (previous.worktree_path if previous else None)
                or manifest.worktree_path
            ),
            status=manifest.status,
            updated_at=_now_iso(),
            completed_at=_now_iso(),
        ),
    )


# ---------------------------------------------------------------------------
# Results file helpers
# ---------------------------------------------------------------------------


def _result_pass_value(value: Optional[bool]) -> str:
    return "" if value is None else str(value)


def _result_score_value(value: Optional[float]) -> str:
    return str(value) if isinstance(value, (int, float)) else ""


async def _init_results_file(results_file: str) -> None:
    if Path(results_file).exists():
        return
    await _ensure_parent_dir(results_file)
    Path(results_file).write_text(_RESULTS_HEADER, encoding="utf-8")


async def _append_results_row(
    results_file: str,
    *,
    iteration: int,
    commit: str,
    pass_: Optional[bool] = None,
    score: Optional[float] = None,
    status: AutoresearchDecisionStatus,
    description: str,
) -> None:
    existing = (
        Path(results_file).read_text(encoding="utf-8")
        if Path(results_file).exists()
        else _RESULTS_HEADER
    )
    row = (
        f"{iteration}\t{commit}\t{_result_pass_value(pass_)}\t"
        f"{_result_score_value(score)}\t{status}\t{description}\n"
    )
    Path(results_file).write_text(existing + row, encoding="utf-8")


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------


async def _append_ledger_entry(
    ledger_file: str, entry: AutoresearchLedgerEntry
) -> None:
    from dataclasses import asdict

    if Path(ledger_file).exists():
        parsed = await _read_json_file(ledger_file)
    else:
        parsed = {"schema_version": 1, "entries": []}

    entries = parsed.get("entries", [])
    if not isinstance(entries, list):
        entries = []

    entries.append(asdict(entry))
    parsed["entries"] = entries
    parsed.setdefault("created_at", _now_iso())
    parsed["updated_at"] = _now_iso()
    await _write_json_file(ledger_file, parsed)


async def _read_ledger_entries(
    ledger_file: str,
) -> list[dict[str, Any]]:
    if not Path(ledger_file).exists():
        return []
    parsed = await _read_json_file(ledger_file)
    entries = parsed.get("entries", [])
    return entries if isinstance(entries, list) else []


async def count_trailing_autoresearch_noops(ledger_file: str) -> int:
    """Count consecutive noop decisions at the end of the ledger."""
    entries = await _read_ledger_entries(ledger_file)
    count = 0
    for entry in reversed(entries):
        if entry.get("kind") != "iteration" or entry.get("decision") != "noop":
            break
        count += 1
    return count


# ---------------------------------------------------------------------------
# Instruction generation
# ---------------------------------------------------------------------------


def _format_instruction_summary(
    entries: list[dict[str, Any]], max_entries: int = 3
) -> list[dict[str, Any]]:
    return [
        {
            "iteration": e.get("iteration"),
            "decision": e.get("decision"),
            "reason": _trim_content(e.get("decision_reason", ""), 160),
            "kept_commit": e.get("kept_commit"),
            "candidate_commit": e.get("candidate_commit"),
            "evaluator_status": (e.get("evaluator") or {}).get("status"),
            "evaluator_score": (
                (e.get("evaluator") or {}).get("score")
                if isinstance((e.get("evaluator") or {}).get("score"), (int, float))
                else None
            ),
            "description": _trim_content(e.get("description", ""), 120),
        }
        for e in entries[-max_entries:]
    ]


async def _build_instruction_context(
    manifest: AutoresearchRunManifest,
) -> tuple[Optional[str], list[dict[str, Any]]]:
    entries = await _read_ledger_entries(manifest.ledger_file)
    previous = entries[-1] if entries else None
    previous_outcome = (
        f"{previous['decision']}:{_trim_content(previous.get('decision_reason', ''), 160)}"
        if previous
        else None
    )
    return previous_outcome, _format_instruction_summary(entries)


def build_autoresearch_instructions(
    contract: AutoresearchMissionContract,
    *,
    run_id: str,
    iteration: int,
    baseline_commit: str,
    last_kept_commit: str,
    last_kept_score: Optional[float] = None,
    results_file: str,
    candidate_file: str,
    keep_policy: AutoresearchKeepPolicy,
    previous_iteration_outcome: Optional[str] = None,
    recent_ledger_summary: Optional[list[dict[str, Any]]] = None,
) -> str:
    """Build the full instruction document for an experiment worker session."""
    state_snapshot = json.dumps(
        {
            "iteration": iteration,
            "baseline_commit": baseline_commit,
            "last_kept_commit": last_kept_commit,
            "last_kept_score": last_kept_score,
            "previous_iteration_outcome": previous_iteration_outcome or "none yet",
            "recent_ledger_summary": recent_ledger_summary or [],
            "keep_policy": keep_policy,
        },
        indent=2,
    )
    score_str = str(last_kept_score) if isinstance(last_kept_score, (int, float)) else "n/a"
    body = contract.sandbox.body or contract.sandbox_content

    lines = [
        "# OMX Autoresearch Supervisor Instructions",
        "",
        f"Run ID: {run_id}",
        f"Mission directory: {contract.mission_dir}",
        f"Mission file: {contract.mission_file}",
        f"Sandbox file: {contract.sandbox_file}",
        f"Mission slug: {contract.mission_slug}",
        f"Iteration: {iteration}",
        f"Baseline commit: {baseline_commit}",
        f"Last kept commit: {last_kept_commit}",
        f"Last kept score: {score_str}",
        f"Results file: {results_file}",
        f"Candidate artifact: {candidate_file}",
        f"Keep policy: {keep_policy}",
        "",
        "Iteration state snapshot:",
        "```json",
        state_snapshot,
        "```",
        "",
        "Operate as a thin autoresearch experiment worker for exactly one experiment cycle.",
        "Do not loop forever inside this session. Make at most one candidate commit, then write the candidate artifact JSON and exit.",
        "",
        "Candidate artifact contract:",
        "- Write JSON to the exact candidate artifact path above.",
        "- status: candidate | noop | abort | interrupted",
        "- candidate_commit: string | null",
        "- base_commit: current base commit before your edits",
        "- for status=candidate, candidate_commit must resolve in git and match the worktree HEAD commit when you exit",
        "- base_commit must still match the last kept commit provided above",
        "- description: short one-line summary",
        "- notes: array of short strings",
        "- created_at: ISO timestamp",
        "",
        "Supervisor semantics after you exit:",
        "- status=candidate => evaluator runs, then supervisor keeps or discards and may reset the worktree",
        "- status=noop => supervisor logs a noop iteration and relaunches",
        "- status=abort => supervisor stops the run",
        "- status=interrupted => supervisor inspects worktree safety before deciding how to proceed",
        "",
        "Evaluator contract:",
        f"- command: {contract.sandbox.evaluator.command}",
        "- format: json",
        "- required output field: pass (boolean)",
        "- optional output field: score (number)",
        "",
        "Mission content:",
        "```md",
        _trim_content(contract.mission_content),
        "```",
        "",
        "Sandbox policy:",
        "```md",
        _trim_content(body),
        "```",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evaluator execution
# ---------------------------------------------------------------------------


async def run_autoresearch_evaluator(
    contract: AutoresearchMissionContract,
    worktree_path: str,
    ledger_file: Optional[str] = None,
    latest_evaluator_file: Optional[str] = None,
) -> AutoresearchEvaluationRecord:
    """Run the evaluator command and return a structured record."""
    ran_at = _now_iso()
    result = subprocess.run(
        contract.sandbox.evaluator.command,
        cwd=worktree_path,
        capture_output=True,
        text=True,
        shell=True,
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        record = AutoresearchEvaluationRecord(
            command=contract.sandbox.evaluator.command,
            ran_at=ran_at,
            status="error",
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    else:
        try:
            parsed = parse_evaluator_result(stdout)
            record = AutoresearchEvaluationRecord(
                command=contract.sandbox.evaluator.command,
                ran_at=ran_at,
                status="pass" if parsed.pass_ else "fail",
                pass_=parsed.pass_,
                score=parsed.score,
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        except Exception as e:
            record = AutoresearchEvaluationRecord(
                command=contract.sandbox.evaluator.command,
                ran_at=ran_at,
                status="error",
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                parse_error=str(e),
            )

    if latest_evaluator_file:
        from dataclasses import asdict
        await _write_json_file(latest_evaluator_file, asdict(record))
    if ledger_file:
        await _append_ledger_entry(
            ledger_file,
            AutoresearchLedgerEntry(
                iteration=-1,
                kind="iteration",
                decision=(
                    "error" if record.status == "error"
                    else "keep" if record.status == "pass"
                    else "discard"
                ),
                decision_reason="raw evaluator record",
                candidate_status="candidate",
                base_commit=_read_git_short_head(worktree_path),
                candidate_commit=None,
                kept_commit=_read_git_short_head(worktree_path),
                keep_policy=contract.sandbox.evaluator.keep_policy or "score_improvement",
                evaluator=record,
                created_at=_now_iso(),
                notes=["raw evaluator invocation"],
                description="raw evaluator record",
            ),
        )
    return record


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def decide_autoresearch_outcome(
    manifest: AutoresearchRunManifest,
    candidate: AutoresearchCandidateArtifact,
    evaluation: Optional[AutoresearchEvaluationRecord],
) -> _AutoresearchDecision:
    """Apply keep-policy logic to decide whether to keep or discard a candidate."""
    if candidate.status == "abort":
        return _AutoresearchDecision(
            decision="abort",
            decision_reason="candidate requested abort",
            keep=False,
            notes=["run stopped by candidate artifact"],
        )
    if candidate.status == "noop":
        return _AutoresearchDecision(
            decision="noop",
            decision_reason="candidate reported noop",
            keep=False,
            notes=["no code change was proposed"],
        )
    if candidate.status == "interrupted":
        return _AutoresearchDecision(
            decision="interrupted",
            decision_reason="candidate session was interrupted",
            keep=False,
            notes=["supervisor should inspect worktree cleanliness before continuing"],
        )

    if not evaluation or evaluation.status == "error":
        return _AutoresearchDecision(
            decision="discard",
            decision_reason="evaluator error",
            keep=False,
            evaluator=evaluation,
            notes=["candidate discarded because evaluator errored or crashed"],
        )
    if not evaluation.pass_:
        return _AutoresearchDecision(
            decision="discard",
            decision_reason="evaluator reported failure",
            keep=False,
            evaluator=evaluation,
            notes=["candidate discarded because evaluator pass=false"],
        )

    if manifest.keep_policy == "pass_only":
        return _AutoresearchDecision(
            decision="keep",
            decision_reason="pass_only keep policy accepted evaluator pass=true",
            keep=True,
            evaluator=evaluation,
            notes=["candidate kept because sandbox opted into pass_only policy"],
        )

    # score_improvement policy
    prev = manifest.last_kept_score
    curr = evaluation.score
    if not (isinstance(prev, (int, float)) and isinstance(curr, (int, float))):
        return _AutoresearchDecision(
            decision="ambiguous",
            decision_reason="evaluator pass without comparable score",
            keep=False,
            evaluator=evaluation,
            notes=[
                "candidate discarded because score_improvement policy "
                "requires comparable numeric scores"
            ],
        )
    if curr > prev:  # type: ignore[operator]
        return _AutoresearchDecision(
            decision="keep",
            decision_reason="score improved over last kept score",
            keep=True,
            evaluator=evaluation,
            notes=["candidate kept because evaluator score increased"],
        )
    return _AutoresearchDecision(
        decision="discard",
        decision_reason="score did not improve",
        keep=False,
        evaluator=evaluation,
        notes=[
            "candidate discarded because evaluator score was not better "
            "than the kept baseline"
        ],
    )


# ---------------------------------------------------------------------------
# Candidate parsing
# ---------------------------------------------------------------------------


def parse_autoresearch_candidate_artifact(
    raw: str,
) -> AutoresearchCandidateArtifact:
    """Parse and validate a candidate artifact JSON string."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("autoresearch candidate artifact must be valid JSON")

    if not isinstance(parsed, dict):
        raise RuntimeError("autoresearch candidate artifact must be a JSON object")

    status = parsed.get("status")
    if status not in ("candidate", "noop", "abort", "interrupted"):
        raise RuntimeError(
            "autoresearch candidate artifact status must be "
            "candidate|noop|abort|interrupted"
        )

    cc = parsed.get("candidate_commit")
    if cc is not None and not isinstance(cc, str):
        raise RuntimeError(
            "autoresearch candidate artifact candidate_commit must be string|null"
        )

    bc = parsed.get("base_commit")
    if not isinstance(bc, str) or not bc.strip():
        raise RuntimeError(
            "autoresearch candidate artifact base_commit is required"
        )

    desc = parsed.get("description")
    if not isinstance(desc, str):
        raise RuntimeError(
            "autoresearch candidate artifact description is required"
        )

    notes = parsed.get("notes")
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        raise RuntimeError(
            "autoresearch candidate artifact notes must be a string array"
        )

    created_at = parsed.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        raise RuntimeError(
            "autoresearch candidate artifact created_at is required"
        )

    return AutoresearchCandidateArtifact(
        status=status,
        candidate_commit=cc,
        base_commit=bc,
        description=desc,
        notes=notes,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


async def _load_run_manifest(
    project_root: str, run_id: str
) -> AutoresearchRunManifest:
    manifest_file = str(
        Path(project_root) / ".omx" / "logs" / "autoresearch" / run_id / "manifest.json"
    )
    if not Path(manifest_file).exists():
        raise RuntimeError(f"autoresearch_resume_manifest_missing:{run_id}")
    data = await _read_json_file(manifest_file)
    return AutoresearchRunManifest(**{
        k: v for k, v in data.items()
        if k in AutoresearchRunManifest.__dataclass_fields__
    })


async def _write_run_manifest(manifest: AutoresearchRunManifest) -> None:
    from dataclasses import asdict
    manifest.updated_at = _now_iso()
    await _write_json_file(manifest.manifest_file, asdict(manifest))


async def _write_instructions_file(
    contract: AutoresearchMissionContract,
    manifest: AutoresearchRunManifest,
) -> None:
    prev_outcome, summary = await _build_instruction_context(manifest)
    content = build_autoresearch_instructions(
        contract,
        run_id=manifest.run_id,
        iteration=manifest.iteration + 1,
        baseline_commit=manifest.baseline_commit,
        last_kept_commit=manifest.last_kept_commit,
        last_kept_score=manifest.last_kept_score,
        results_file=manifest.results_file,
        candidate_file=manifest.candidate_file,
        keep_policy=manifest.keep_policy,
        previous_iteration_outcome=prev_outcome,
        recent_ledger_summary=summary,
    )
    await _ensure_parent_dir(manifest.instructions_file)
    Path(manifest.instructions_file).write_text(
        content + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Recording helpers
# ---------------------------------------------------------------------------


async def _record_iteration(
    manifest: AutoresearchRunManifest,
    *,
    status: AutoresearchDecisionStatus,
    decision_reason: str,
    description: str,
    candidate_status: str,
    base_commit: str,
    candidate_commit: Optional[str],
    kept_commit: Optional[str] = None,
    evaluator: Optional[AutoresearchEvaluationRecord] = None,
    notes: list[str],
    created_at: Optional[str] = None,
) -> None:
    commit = _read_git_short_head(manifest.worktree_path)
    await _append_results_row(
        manifest.results_file,
        iteration=manifest.iteration,
        commit=commit,
        pass_=evaluator.pass_ if evaluator else None,
        score=evaluator.score if evaluator else None,
        status=status,
        description=description,
    )
    await _append_ledger_entry(
        manifest.ledger_file,
        AutoresearchLedgerEntry(
            iteration=manifest.iteration,
            kind="iteration",
            decision=status,
            decision_reason=decision_reason,
            candidate_status=candidate_status,
            base_commit=base_commit,
            candidate_commit=candidate_commit,
            kept_commit=kept_commit or manifest.last_kept_commit,
            keep_policy=manifest.keep_policy,
            evaluator=evaluator,
            created_at=created_at or _now_iso(),
            notes=notes,
            description=description,
        ),
    )


# ---------------------------------------------------------------------------
# Baseline seeding
# ---------------------------------------------------------------------------


async def _seed_baseline(
    contract: AutoresearchMissionContract,
    manifest: AutoresearchRunManifest,
) -> AutoresearchEvaluationRecord:
    from dataclasses import asdict

    evaluation = await run_autoresearch_evaluator(contract, manifest.worktree_path)
    await _write_json_file(manifest.latest_evaluator_file, asdict(evaluation))
    await _append_results_row(
        manifest.results_file,
        iteration=0,
        commit=_read_git_short_head(manifest.worktree_path),
        pass_=evaluation.pass_,
        score=evaluation.score,
        status="error" if evaluation.status == "error" else "baseline",
        description="initial baseline evaluation",
    )
    await _append_ledger_entry(
        manifest.ledger_file,
        AutoresearchLedgerEntry(
            iteration=0,
            kind="baseline",
            decision="error" if evaluation.status == "error" else "baseline",
            decision_reason=(
                "baseline evaluator error"
                if evaluation.status == "error"
                else "baseline established"
            ),
            candidate_status="baseline",
            base_commit=manifest.baseline_commit,
            candidate_commit=None,
            kept_commit=manifest.last_kept_commit,
            keep_policy=manifest.keep_policy,
            evaluator=evaluation,
            created_at=_now_iso(),
            notes=["baseline row is always recorded"],
            description="initial baseline evaluation",
        ),
    )
    if evaluation.pass_ and isinstance(evaluation.score, (int, float)):
        manifest.last_kept_score = evaluation.score
    else:
        manifest.last_kept_score = None
    await _write_run_manifest(manifest)
    await _write_instructions_file(contract, manifest)
    return evaluation


# ---------------------------------------------------------------------------
# Run finalization
# ---------------------------------------------------------------------------


async def _finalize_run(
    manifest: AutoresearchRunManifest,
    project_root: str,
    *,
    status: AutoresearchRunStatus,
    stop_reason: str,
) -> None:
    manifest.status = status
    manifest.stop_reason = stop_reason
    manifest.completed_at = _now_iso()
    await _write_run_manifest(manifest)
    await _deactivate_run(manifest)


def _reset_to_last_kept(manifest: AutoresearchRunManifest) -> None:
    assert_reset_safe_worktree(manifest.worktree_path)
    _require_git_success(
        manifest.worktree_path, ["reset", "--hard", manifest.last_kept_commit]
    )


# ---------------------------------------------------------------------------
# Candidate validation
# ---------------------------------------------------------------------------


def _validate_candidate(
    manifest: AutoresearchRunManifest,
    candidate: AutoresearchCandidateArtifact,
) -> AutoresearchCandidateArtifact | str:
    """Returns updated candidate on success, or error reason string."""
    resolved_base = _try_resolve_git_commit(
        manifest.worktree_path, candidate.base_commit
    )
    if not resolved_base:
        return f"candidate base_commit does not resolve in git: {candidate.base_commit}"
    if resolved_base != manifest.last_kept_commit:
        return (
            f"candidate base_commit {resolved_base} does not match "
            f"last kept commit {manifest.last_kept_commit}"
        )

    if candidate.status != "candidate":
        return AutoresearchCandidateArtifact(
            status=candidate.status,
            candidate_commit=candidate.candidate_commit,
            base_commit=resolved_base,
            description=candidate.description,
            notes=candidate.notes,
            created_at=candidate.created_at,
        )

    if not candidate.candidate_commit:
        return "candidate status requires a non-null candidate_commit"

    resolved_cc = _try_resolve_git_commit(
        manifest.worktree_path, candidate.candidate_commit
    )
    if not resolved_cc:
        return f"candidate_commit does not resolve in git: {candidate.candidate_commit}"

    head = _read_git_full_head(manifest.worktree_path)
    if resolved_cc != head:
        return (
            f"candidate_commit {resolved_cc} does not match "
            f"worktree HEAD {head}"
        )

    return AutoresearchCandidateArtifact(
        status=candidate.status,
        candidate_commit=resolved_cc,
        base_commit=resolved_base,
        description=candidate.description,
        notes=candidate.notes,
        created_at=candidate.created_at,
    )


# ---------------------------------------------------------------------------
# Public high-level functions
# ---------------------------------------------------------------------------


async def prepare_autoresearch_runtime(
    contract: AutoresearchMissionContract,
    project_root: str,
    worktree_path: str,
    *,
    run_tag: Optional[str] = None,
) -> PreparedAutoresearchRuntime:
    """Prepare a new autoresearch run: create manifest, seed baseline, etc."""
    await _assert_lock_available(project_root)
    assert_reset_safe_worktree(worktree_path)

    tag = run_tag or build_autoresearch_run_tag()
    run_id = _build_run_id(contract.mission_slug, tag)
    baseline_commit = _read_git_short_head(worktree_path)
    branch_name = _read_git(
        worktree_path, ["symbolic-ref", "--quiet", "--short", "HEAD"]
    )
    run_dir = str(
        Path(project_root) / ".omx" / "logs" / "autoresearch" / run_id
    )
    state_file = _active_run_state_file(project_root)
    instructions_file = str(Path(run_dir) / "bootstrap-instructions.md")
    manifest_file = str(Path(run_dir) / "manifest.json")
    ledger_file = str(Path(run_dir) / "iteration-ledger.json")
    latest_evaluator_file = str(Path(run_dir) / "latest-evaluator-result.json")
    candidate_file = str(Path(run_dir) / "candidate.json")
    results_file = str(Path(worktree_path) / "results.tsv")
    task_description = (
        f"autoresearch {contract.mission_relative_dir} ({run_id})"
    )
    keep_policy: AutoresearchKeepPolicy = (
        contract.sandbox.evaluator.keep_policy or "score_improvement"
    )

    Path(run_dir).mkdir(parents=True, exist_ok=True)
    await _init_results_file(results_file)
    await _write_json_file(
        candidate_file,
        {
            "status": "noop",
            "candidate_commit": None,
            "base_commit": baseline_commit,
            "description": "not-yet-written",
            "notes": [
                "candidate artifact will be overwritten by the launched session"
            ],
            "created_at": _now_iso(),
        },
    )

    from dataclasses import asdict

    evaluator_dict = asdict(contract.sandbox.evaluator)

    manifest = AutoresearchRunManifest(
        run_id=run_id,
        run_tag=tag,
        mission_dir=contract.mission_dir,
        mission_file=contract.mission_file,
        sandbox_file=contract.sandbox_file,
        repo_root=project_root,
        worktree_path=worktree_path,
        mission_slug=contract.mission_slug,
        branch_name=branch_name,
        baseline_commit=baseline_commit,
        last_kept_commit=_read_git_full_head(worktree_path),
        last_kept_score=None,
        latest_candidate_commit=None,
        results_file=results_file,
        instructions_file=instructions_file,
        manifest_file=manifest_file,
        ledger_file=ledger_file,
        latest_evaluator_file=latest_evaluator_file,
        candidate_file=candidate_file,
        evaluator=evaluator_dict,
        keep_policy=keep_policy,
        status="running",
        stop_reason=None,
        iteration=0,
        created_at=_now_iso(),
        updated_at=_now_iso(),
        completed_at=None,
    )

    await _write_instructions_file(contract, manifest)
    await _write_run_manifest(manifest)
    await _write_json_file(
        ledger_file,
        {
            "schema_version": 1,
            "run_id": run_id,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "entries": [],
        },
    )
    await _write_json_file(
        latest_evaluator_file,
        {"run_id": run_id, "status": "not-yet-run", "updated_at": _now_iso()},
    )
    await _activate_run(manifest)
    await _seed_baseline(contract, manifest)

    return PreparedAutoresearchRuntime(
        run_id=run_id,
        run_tag=tag,
        run_dir=run_dir,
        instructions_file=instructions_file,
        manifest_file=manifest_file,
        ledger_file=ledger_file,
        latest_evaluator_file=latest_evaluator_file,
        results_file=results_file,
        state_file=state_file,
        candidate_file=candidate_file,
        repo_root=project_root,
        worktree_path=worktree_path,
        task_description=task_description,
    )


async def resume_autoresearch_runtime(
    project_root: str, run_id: str
) -> PreparedAutoresearchRuntime:
    """Resume an existing autoresearch run."""
    await _assert_lock_available(project_root)
    manifest = await _load_run_manifest(project_root, run_id)

    if manifest.status != "running":
        raise RuntimeError(f"autoresearch_resume_terminal_run:{run_id}")
    if not Path(manifest.worktree_path).exists():
        raise RuntimeError(
            f"autoresearch_resume_missing_worktree:{manifest.worktree_path}"
        )

    assert_reset_safe_worktree(manifest.worktree_path)
    await _activate_run(manifest)

    return PreparedAutoresearchRuntime(
        run_id=manifest.run_id,
        run_tag=manifest.run_tag,
        run_dir=str(Path(manifest.manifest_file).parent),
        instructions_file=manifest.instructions_file,
        manifest_file=manifest.manifest_file,
        ledger_file=manifest.ledger_file,
        latest_evaluator_file=manifest.latest_evaluator_file,
        results_file=manifest.results_file,
        state_file=_active_run_state_file(project_root),
        candidate_file=manifest.candidate_file,
        repo_root=manifest.repo_root,
        worktree_path=manifest.worktree_path,
        task_description=f"autoresearch resume {run_id}",
    )


async def process_autoresearch_candidate(
    contract: AutoresearchMissionContract,
    manifest: AutoresearchRunManifest,
    project_root: str,
) -> AutoresearchDecisionStatus:
    """Process a candidate artifact: validate, evaluate, decide, record."""
    from dataclasses import asdict

    manifest.iteration += 1

    # Read candidate
    try:
        raw = Path(manifest.candidate_file).read_text(encoding="utf-8")
        candidate = parse_autoresearch_candidate_artifact(raw)
    except Exception as e:
        # fail iteration
        try:
            commit = _read_git_short_head(manifest.worktree_path)
        except Exception:
            commit = manifest.baseline_commit
        await _append_results_row(
            manifest.results_file,
            iteration=manifest.iteration,
            commit=commit,
            status="error",
            description="candidate validation failed",
        )
        await _finalize_run(
            manifest, project_root, status="failed", stop_reason=str(e)
        )
        return "error"

    # Validate
    validation = _validate_candidate(manifest, candidate)
    if isinstance(validation, str):
        try:
            commit = _read_git_short_head(manifest.worktree_path)
        except Exception:
            commit = manifest.baseline_commit
        await _append_results_row(
            manifest.results_file,
            iteration=manifest.iteration,
            commit=commit,
            status="error",
            description=candidate.description or "candidate validation failed",
        )
        await _finalize_run(
            manifest, project_root, status="failed", stop_reason=validation
        )
        return "error"

    candidate = validation
    manifest.latest_candidate_commit = candidate.candidate_commit

    # Non-candidate statuses (abort, noop, interrupted)
    if candidate.status != "candidate":
        shared = dict(
            description=candidate.description,
            candidate_status=candidate.status,
            base_commit=candidate.base_commit,
            candidate_commit=candidate.candidate_commit,
            notes=candidate.notes,
        )
        if candidate.status == "abort":
            await _record_iteration(
                manifest,
                status="abort",
                decision_reason="candidate requested abort",
                **shared,
            )
            await _finalize_run(
                manifest, project_root,
                status="stopped", stop_reason="candidate abort",
            )
            return "abort"
        if candidate.status == "interrupted":
            try:
                assert_reset_safe_worktree(manifest.worktree_path)
            except Exception:
                await _finalize_run(
                    manifest, project_root,
                    status="failed",
                    stop_reason="interrupted dirty worktree requires operator intervention",
                )
                return "error"
            await _record_iteration(
                manifest,
                status="interrupted",
                decision_reason="candidate session interrupted cleanly",
                **shared,
            )
            await _write_run_manifest(manifest)
            await _write_instructions_file(contract, manifest)
            return "interrupted"
        # noop
        await _record_iteration(
            manifest,
            status="noop",
            decision_reason="candidate reported noop",
            **shared,
        )
        await _write_run_manifest(manifest)
        await _write_instructions_file(contract, manifest)
        return "noop"

    # Evaluate
    evaluation = await run_autoresearch_evaluator(
        contract, manifest.worktree_path
    )
    await _write_json_file(manifest.latest_evaluator_file, asdict(evaluation))

    decision = decide_autoresearch_outcome(manifest, candidate, evaluation)
    if decision.keep:
        manifest.last_kept_commit = _read_git_full_head(manifest.worktree_path)
        if isinstance(evaluation.score, (int, float)):
            manifest.last_kept_score = evaluation.score
    else:
        _reset_to_last_kept(manifest)

    await _record_iteration(
        manifest,
        status=decision.decision,
        decision_reason=decision.decision_reason,
        description=candidate.description,
        candidate_status=candidate.status,
        base_commit=candidate.base_commit,
        candidate_commit=candidate.candidate_commit,
        evaluator=evaluation,
        notes=[*candidate.notes, *decision.notes],
    )
    await _write_run_manifest(manifest)
    await _write_instructions_file(contract, manifest)
    return decision.decision


async def finalize_autoresearch_run_state(
    project_root: str,
    run_id: str,
    *,
    status: AutoresearchRunStatus,
    stop_reason: str,
) -> None:
    """Finalize a run by setting terminal status."""
    manifest = await _load_run_manifest(project_root, run_id)
    if manifest.status != "running":
        return
    await _finalize_run(
        manifest, project_root, status=status, stop_reason=stop_reason
    )


async def stop_autoresearch_runtime(project_root: str) -> None:
    """Stop the currently active autoresearch run, if any."""
    state = await _read_active_run_state(project_root)
    if not state or not state.active:
        return
    run_id = state.run_id
    if run_id:
        await finalize_autoresearch_run_state(
            project_root, run_id, status="stopped", stop_reason="operator stop"
        )
