"""
AutoresearchRunner: Autonomous experimentation loop for the autoresearch mode.

Orchestrates the full research cycle:
    prepare → baseline → iterate (run_iteration → evaluate → decide) → finalize

Each iteration runs in a git worktree so candidate commits are fully isolated.
The ledger at .orbit/autoresearch/ledger.json is the canonical audit trail.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from .contracts import (
    AutoresearchEvaluatorResult,
    AutoresearchKeepPolicy,
    AutoresearchMissionContract,
    ContractError,
    load_autoresearch_mission_contract,
    parse_evaluator_result,
    slugify_mission_name,
)
from .runtime import (
    AutoresearchCandidateArtifact,
    AutoresearchDecisionStatus,
    AutoresearchEvaluationRecord,
    AutoresearchLedgerEntry,
    AutoresearchRunManifest,
    AutoresearchRunStatus,
    assert_reset_safe_worktree,
    build_autoresearch_run_tag,
    count_trailing_autoresearch_noops,
    decide_autoresearch_outcome,
    parse_autoresearch_candidate_artifact,
    prepare_autoresearch_runtime,
    process_autoresearch_candidate,
    run_autoresearch_evaluator,
    stop_autoresearch_runtime,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_CONSECUTIVE_NOOPS = 3
_LEDGER_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Ledger record that AutoresearchRunner writes directly
# (separate from runtime.AutoresearchLedgerEntry which is the low-level struct)
# ---------------------------------------------------------------------------


@dataclass
class ResearchDecisionRecord:
    """A single decision recorded in the runner's ledger.json."""

    iteration: int
    decision: AutoresearchDecisionStatus
    decision_reason: str
    candidate_status: str
    score: Optional[float]
    passed: Optional[bool]
    kept_commit: Optional[str]
    candidate_commit: Optional[str]
    base_commit: str
    notes: list[str]
    created_at: str


# ---------------------------------------------------------------------------
# Runner-level run manifest (stored in .orbit/autoresearch/)
# ---------------------------------------------------------------------------


@dataclass
class AutoresearchRunRecord:
    """Persistent run metadata stored in .orbit/autoresearch/run.json."""

    schema_version: int = _LEDGER_SCHEMA_VERSION
    run_id: str = ""
    mission_path: str = ""
    mission_slug: str = ""
    repo_root: str = ""
    worktree_path: str = ""
    baseline_commit: str = ""
    last_kept_commit: str = ""
    last_kept_score: Optional[float] = None
    status: AutoresearchRunStatus = "running"
    stop_reason: Optional[str] = None
    iteration: int = 0
    max_iterations: int = 10
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _autoresearch_dir(cwd: str) -> Path:
    return Path(cwd) / ".orbit" / "autoresearch"


def _candidates_dir(cwd: str) -> Path:
    return _autoresearch_dir(cwd) / "candidates"


def _ledger_path(cwd: str) -> Path:
    return _autoresearch_dir(cwd) / "ledger.json"


def _run_record_path(cwd: str) -> Path:
    return _autoresearch_dir(cwd) / "run.json"


def _ensure_dirs(cwd: str) -> None:
    _autoresearch_dir(cwd).mkdir(parents=True, exist_ok=True)
    _candidates_dir(cwd).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------


def _read_ledger(cwd: str) -> dict[str, Any]:
    path = _ledger_path(cwd)
    if not path.exists():
        return {
            "schema_version": _LEDGER_SCHEMA_VERSION,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "entries": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "schema_version": _LEDGER_SCHEMA_VERSION,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "entries": [],
        }


def _append_ledger_entry(cwd: str, record: ResearchDecisionRecord) -> None:
    ledger = _read_ledger(cwd)
    entries: list[Any] = ledger.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    entries.append(asdict(record))
    ledger["entries"] = entries
    ledger["updated_at"] = _now_iso()
    path = _ledger_path(cwd)
    path.write_text(_stable_json(ledger) + "\n", encoding="utf-8")


def _count_trailing_noops(cwd: str) -> int:
    ledger = _read_ledger(cwd)
    entries: list[dict[str, Any]] = ledger.get("entries", [])
    count = 0
    for entry in reversed(entries):
        if entry.get("decision") == "noop":
            count += 1
        else:
            break
    return count


# ---------------------------------------------------------------------------
# Run record I/O
# ---------------------------------------------------------------------------


def _write_run_record(cwd: str, record: AutoresearchRunRecord) -> None:
    _ensure_dirs(cwd)
    record.updated_at = _now_iso()
    path = _run_record_path(cwd)
    path.write_text(_stable_json(asdict(record)) + "\n", encoding="utf-8")


def _read_run_record(cwd: str) -> Optional[AutoresearchRunRecord]:
    path = _run_record_path(cwd)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        allowed = set(AutoresearchRunRecord.__dataclass_fields__)
        return AutoresearchRunRecord(**{k: v for k, v in data.items() if k in allowed})
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Git worktree helpers
# ---------------------------------------------------------------------------


def _git(cwd: str, args: list[str], *, check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )


def _git_head_full(cwd: str) -> str:
    return _git(cwd, ["rev-parse", "HEAD"]).stdout.strip()


def _git_head_short(cwd: str) -> str:
    return _git(cwd, ["rev-parse", "--short=7", "HEAD"]).stdout.strip()


def _create_worktree(repo_root: str, worktree_path: str, branch_name: str) -> None:
    """Create a new git worktree on a new branch."""
    _git(repo_root, ["worktree", "add", "--no-checkout", worktree_path, "HEAD"])
    # Checkout so the worktree has files.
    _git(worktree_path, ["checkout", "-b", branch_name])


def _remove_worktree(repo_root: str, worktree_path: str) -> None:
    """Remove a git worktree, tolerating errors."""
    try:
        _git(repo_root, ["worktree", "remove", "--force", worktree_path], check=False)
    except (subprocess.SubprocessError, OSError):
        pass


def _worktree_exists(worktree_path: str) -> bool:
    return Path(worktree_path).is_dir()


# ---------------------------------------------------------------------------
# Candidate directory helpers
# ---------------------------------------------------------------------------


def _candidate_dir(cwd: str, iteration: int) -> Path:
    return _candidates_dir(cwd) / f"iteration-{iteration:04d}"


def _write_candidate_artifact(cwd: str, iteration: int, artifact: dict[str, Any]) -> str:
    """Write a candidate artifact JSON for the given iteration. Returns path."""
    d = _candidate_dir(cwd, iteration)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "candidate.json"
    path.write_text(_stable_json(artifact) + "\n", encoding="utf-8")
    return str(path)


def _read_candidate_artifact(cwd: str, iteration: int) -> Optional[dict[str, Any]]:
    path = _candidate_dir(cwd, iteration) / "candidate.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_eval_result(cwd: str, iteration: int, result: dict[str, Any]) -> None:
    d = _candidate_dir(cwd, iteration)
    d.mkdir(parents=True, exist_ok=True)
    (d / "eval-result.json").write_text(_stable_json(result) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def _run_evaluator_command(command: str, cwd: str, timeout: int = 120) -> AutoresearchEvaluationRecord:
    """Run the evaluator shell command and return a structured record."""
    ran_at = _now_iso()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return AutoresearchEvaluationRecord(
            command=command,
            ran_at=ran_at,
            status="error",
            exit_code=None,
            stderr="evaluator timed out",
            parse_error=f"timeout after {timeout}s",
        )
    except OSError as exc:
        return AutoresearchEvaluationRecord(
            command=command,
            ran_at=ran_at,
            status="error",
            exit_code=None,
            stderr=str(exc),
            parse_error=str(exc),
        )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        return AutoresearchEvaluationRecord(
            command=command,
            ran_at=ran_at,
            status="error",
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    try:
        parsed = parse_evaluator_result(stdout)
        return AutoresearchEvaluationRecord(
            command=command,
            ran_at=ran_at,
            status="pass" if parsed.pass_ else "fail",
            pass_=parsed.pass_,
            score=parsed.score,
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception as exc:
        return AutoresearchEvaluationRecord(
            command=command,
            ran_at=ran_at,
            status="error",
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            parse_error=str(exc),
        )


# ---------------------------------------------------------------------------
# Decision logic (stand-alone, no manifest dependency)
# ---------------------------------------------------------------------------


@dataclass
class _Decision:
    decision: AutoresearchDecisionStatus
    decision_reason: str
    keep: bool
    notes: list[str] = field(default_factory=list)


def _decide(
    record: AutoresearchRunRecord,
    eval_record: AutoresearchEvaluationRecord,
    keep_policy: AutoresearchKeepPolicy,
) -> _Decision:
    if eval_record.status == "error":
        return _Decision(
            decision="discard",
            decision_reason="evaluator error — cannot assess candidate",
            keep=False,
            notes=["candidate discarded due to evaluator error"],
        )
    if not eval_record.pass_:
        return _Decision(
            decision="discard",
            decision_reason="evaluator pass=false",
            keep=False,
            notes=["candidate discarded because evaluator reported failure"],
        )

    if keep_policy == "pass_only":
        return _Decision(
            decision="keep",
            decision_reason="pass_only policy: evaluator pass=true",
            keep=True,
            notes=["candidate kept under pass_only policy"],
        )

    # score_improvement
    prev = record.last_kept_score
    curr = eval_record.score
    if not (isinstance(prev, (int, float)) and isinstance(curr, (int, float))):
        return _Decision(
            decision="ambiguous",
            decision_reason="score_improvement policy requires comparable numeric scores",
            keep=False,
            notes=["candidate discarded — scores not comparable"],
        )
    if curr > prev:
        return _Decision(
            decision="keep",
            decision_reason=f"score improved: {prev} → {curr}",
            keep=True,
            notes=[f"score improved from {prev} to {curr}"],
        )
    return _Decision(
        decision="discard",
        decision_reason=f"score did not improve: {curr} <= {prev}",
        keep=False,
        notes=[f"score {curr} did not beat previous {prev}"],
    )


# ---------------------------------------------------------------------------
# AutoresearchRunner
# ---------------------------------------------------------------------------


class AutoresearchRunner:
    """
    Orchestrates the autonomous research experimentation loop.

    Usage:
        runner = AutoresearchRunner(cwd="/path/to/repo")
        await runner.prepare("/path/to/mission")
        result = await runner.run(max_iterations=5)

    Each candidate runs in a git worktree so the main branch is never directly
    mutated mid-iteration.  The ledger at .orbit/autoresearch/ledger.json is
    the canonical audit trail.

    Abort conditions:
    - ``max_iterations`` reached.
    - 3 consecutive noop decisions.
    - A candidate requests abort.
    - An unrecoverable runtime error.
    """

    def __init__(self, cwd: str) -> None:
        """
        Args:
            cwd: Repository root directory.
        """
        self._cwd = str(Path(cwd).resolve())
        self._contract: Optional[AutoresearchMissionContract] = None
        self._record: Optional[AutoresearchRunRecord] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def prepare(self, mission_path: str) -> AutoresearchRunRecord:
        """
        Load the mission contract and create the run directory structure.

        Args:
            mission_path: Path to a directory containing mission.md and sandbox.md.

        Returns:
            AutoresearchRunRecord describing the prepared run.
        """
        _ensure_dirs(self._cwd)

        self._contract = await load_autoresearch_mission_contract(mission_path)
        contract = self._contract

        run_tag = build_autoresearch_run_tag()
        run_id = f"{contract.mission_slug}-{run_tag.lower()}"
        baseline_commit = _git_head_full(contract.repo_root)

        record = AutoresearchRunRecord(
            run_id=run_id,
            mission_path=str(Path(mission_path).resolve()),
            mission_slug=contract.mission_slug,
            repo_root=contract.repo_root,
            worktree_path="",  # set when worktree is created
            baseline_commit=baseline_commit,
            last_kept_commit=baseline_commit,
            last_kept_score=None,
            status="running",
            stop_reason=None,
            iteration=0,
            max_iterations=10,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

        _write_run_record(self._cwd, record)
        self._record = record

        # Initialise ledger.
        ledger = {
            "schema_version": _LEDGER_SCHEMA_VERSION,
            "run_id": run_id,
            "mission_slug": contract.mission_slug,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "entries": [],
        }
        _ledger_path(self._cwd).write_text(_stable_json(ledger) + "\n", encoding="utf-8")

        return record

    async def establish_baseline(self) -> AutoresearchEvaluationRecord:
        """
        Run the evaluator against the current (unmodified) repo state to
        establish a baseline score before any iterations.

        Returns:
            Evaluation record for the baseline.
        """
        record = self._require_record()
        contract = self._require_contract()
        eval_record = _run_evaluator_command(
            contract.sandbox.evaluator.command, contract.repo_root
        )

        if eval_record.pass_ and isinstance(eval_record.score, (int, float)):
            record.last_kept_score = eval_record.score

        _append_ledger_entry(
            self._cwd,
            ResearchDecisionRecord(
                iteration=0,
                decision="baseline" if eval_record.status != "error" else "error",  # type: ignore[arg-type]
                decision_reason="baseline established" if eval_record.status != "error" else "baseline evaluator error",
                candidate_status="baseline",
                score=eval_record.score,
                passed=eval_record.pass_,
                kept_commit=record.last_kept_commit,
                candidate_commit=None,
                base_commit=record.baseline_commit,
                notes=["baseline row always recorded"],
                created_at=_now_iso(),
            ),
        )
        _write_run_record(self._cwd, record)
        return eval_record

    async def run_iteration(self, iteration_num: int) -> dict[str, Any]:
        """
        Execute one research iteration:
        1. Reset worktree to last-kept commit.
        2. Write instructions file for the iteration.
        3. Return metadata the caller can use to launch a worker agent session.

        In a fully automated pipeline the caller launches an agent session that
        reads the instructions and writes a candidate artifact, then calls
        process_candidate() when the session finishes.

        Args:
            iteration_num: 1-based iteration index.

        Returns:
            dict with keys: iteration, instructions_file, candidate_file,
                            last_kept_commit, baseline_commit.
        """
        record = self._require_record()
        contract = self._require_contract()

        record.iteration = iteration_num
        d = _candidate_dir(self._cwd, iteration_num)
        d.mkdir(parents=True, exist_ok=True)

        instructions_file = str(d / "instructions.md")
        candidate_file = str(d / "candidate.json")

        # Write a default (noop) candidate placeholder so the file always exists.
        _write_candidate_artifact(self._cwd, iteration_num, {
            "status": "noop",
            "candidate_commit": None,
            "base_commit": record.last_kept_commit,
            "description": "not-yet-written",
            "notes": ["placeholder — agent session overwrites this"],
            "created_at": _now_iso(),
        })

        # Build and write instructions.
        from .runtime import build_autoresearch_instructions
        instructions = build_autoresearch_instructions(
            contract,
            run_id=record.run_id,
            iteration=iteration_num,
            baseline_commit=record.baseline_commit,
            last_kept_commit=record.last_kept_commit,
            last_kept_score=record.last_kept_score,
            results_file=str(_autoresearch_dir(self._cwd) / "results.tsv"),
            candidate_file=candidate_file,
            keep_policy=contract.sandbox.evaluator.keep_policy or "score_improvement",
        )
        Path(instructions_file).write_text(instructions + "\n", encoding="utf-8")
        _write_run_record(self._cwd, record)

        return {
            "iteration": iteration_num,
            "instructions_file": instructions_file,
            "candidate_file": candidate_file,
            "last_kept_commit": record.last_kept_commit,
            "baseline_commit": record.baseline_commit,
        }

    async def process_candidate(self, iteration_num: int) -> AutoresearchDecisionStatus:
        """
        Process the candidate artifact written by an agent worker for *iteration_num*.

        Reads .orbit/autoresearch/candidates/iteration-NNNN/candidate.json,
        validates it, runs the evaluator if it's a real candidate, decides
        keep/discard, resets worktree if discarded, and records in the ledger.

        Args:
            iteration_num: Iteration index (matches run_iteration call).

        Returns:
            Decision status string.
        """
        record = self._require_record()
        contract = self._require_contract()
        keep_policy: AutoresearchKeepPolicy = (
            contract.sandbox.evaluator.keep_policy or "score_improvement"
        )

        raw_artifact = _read_candidate_artifact(self._cwd, iteration_num)
        if raw_artifact is None:
            _append_ledger_entry(self._cwd, ResearchDecisionRecord(
                iteration=iteration_num,
                decision="error",
                decision_reason="candidate artifact missing",
                candidate_status="missing",
                score=None,
                passed=None,
                kept_commit=record.last_kept_commit,
                candidate_commit=None,
                base_commit=record.last_kept_commit,
                notes=["candidate.json not found"],
                created_at=_now_iso(),
            ))
            return "error"

        try:
            candidate = parse_autoresearch_candidate_artifact(
                json.dumps(raw_artifact)
            )
        except RuntimeError as exc:
            _append_ledger_entry(self._cwd, ResearchDecisionRecord(
                iteration=iteration_num,
                decision="error",
                decision_reason=str(exc),
                candidate_status="invalid",
                score=None,
                passed=None,
                kept_commit=record.last_kept_commit,
                candidate_commit=None,
                base_commit=record.last_kept_commit,
                notes=["candidate artifact failed validation"],
                created_at=_now_iso(),
            ))
            return "error"

        # Short-circuit non-candidate statuses.
        if candidate.status == "abort":
            _append_ledger_entry(self._cwd, ResearchDecisionRecord(
                iteration=iteration_num,
                decision="abort",
                decision_reason="candidate requested abort",
                candidate_status="abort",
                score=None,
                passed=None,
                kept_commit=record.last_kept_commit,
                candidate_commit=None,
                base_commit=candidate.base_commit,
                notes=candidate.notes,
                created_at=_now_iso(),
            ))
            record.status = "stopped"
            record.stop_reason = "candidate abort"
            record.completed_at = _now_iso()
            _write_run_record(self._cwd, record)
            return "abort"

        if candidate.status == "noop":
            _append_ledger_entry(self._cwd, ResearchDecisionRecord(
                iteration=iteration_num,
                decision="noop",
                decision_reason="candidate reported noop",
                candidate_status="noop",
                score=None,
                passed=None,
                kept_commit=record.last_kept_commit,
                candidate_commit=None,
                base_commit=candidate.base_commit,
                notes=candidate.notes,
                created_at=_now_iso(),
            ))
            return "noop"

        if candidate.status == "interrupted":
            _append_ledger_entry(self._cwd, ResearchDecisionRecord(
                iteration=iteration_num,
                decision="interrupted",
                decision_reason="candidate session interrupted",
                candidate_status="interrupted",
                score=None,
                passed=None,
                kept_commit=record.last_kept_commit,
                candidate_commit=None,
                base_commit=candidate.base_commit,
                notes=candidate.notes,
                created_at=_now_iso(),
            ))
            return "interrupted"

        # Real candidate — evaluate.
        worktree = record.worktree_path or contract.repo_root
        eval_record = _run_evaluator_command(contract.sandbox.evaluator.command, worktree)
        _write_eval_result(self._cwd, iteration_num, asdict(eval_record))

        decision = _decide(record, eval_record, keep_policy)

        if decision.keep:
            if candidate.candidate_commit:
                record.last_kept_commit = candidate.candidate_commit
            if isinstance(eval_record.score, (int, float)):
                record.last_kept_score = eval_record.score
        else:
            # Reset worktree to last-kept if a worktree is active.
            if record.worktree_path and _worktree_exists(record.worktree_path):
                try:
                    assert_reset_safe_worktree(record.worktree_path)
                    _git(record.worktree_path, ["reset", "--hard", record.last_kept_commit], check=False)
                except (RuntimeError, subprocess.SubprocessError):
                    pass  # best-effort reset

        _append_ledger_entry(self._cwd, ResearchDecisionRecord(
            iteration=iteration_num,
            decision=decision.decision,
            decision_reason=decision.decision_reason,
            candidate_status=candidate.status,
            score=eval_record.score,
            passed=eval_record.pass_,
            kept_commit=record.last_kept_commit,
            candidate_commit=candidate.candidate_commit,
            base_commit=candidate.base_commit,
            notes=[*candidate.notes, *decision.notes],
            created_at=_now_iso(),
        ))
        _write_run_record(self._cwd, record)
        return decision.decision

    async def evaluate(self, candidate: Optional[dict[str, Any]] = None, worktree: Optional[str] = None) -> AutoresearchEvaluationRecord:
        """
        Run the evaluator command and return the structured result.

        Args:
            candidate: Optional candidate artifact dict (unused, for API parity).
            worktree: Override the directory in which to run the evaluator.
                      Defaults to the worktree_path from the run record, or
                      the repo root if no worktree is set.

        Returns:
            AutoresearchEvaluationRecord with pass/fail/score.
        """
        record = self._require_record()
        contract = self._require_contract()
        eval_dir = worktree or record.worktree_path or contract.repo_root
        return _run_evaluator_command(contract.sandbox.evaluator.command, eval_dir)

    def decide(
        self,
        eval_result: AutoresearchEvaluationRecord,
        keep_policy: Optional[AutoresearchKeepPolicy] = None,
    ) -> _Decision:
        """
        Apply keep-policy logic and return a decision.

        Args:
            eval_result: Evaluation record from evaluate().
            keep_policy: Override keep policy. Falls back to contract setting.

        Returns:
            _Decision with .decision, .keep, .decision_reason, .notes.
        """
        record = self._require_record()
        contract = self._require_contract()
        policy: AutoresearchKeepPolicy = (
            keep_policy
            or contract.sandbox.evaluator.keep_policy
            or "score_improvement"
        )
        return _decide(record, eval_result, policy)

    async def run(self, max_iterations: int = 10) -> AutoresearchRunRecord:
        """
        Execute the full research loop.

        Flow:
            prepare (must have been called first) →
            establish_baseline →
            for each iteration:
                run_iteration → (external agent writes candidate) → process_candidate
                abort if consecutive noops >= 3 or decision == 'abort'
            finalize

        In this synchronous-friendly implementation, the "agent worker" step is
        simulated by leaving the candidate artifact as-is (noop).  In a real
        pipeline, an agent session should be launched between run_iteration() and
        process_candidate().

        Args:
            max_iterations: Maximum number of experiment iterations.

        Returns:
            Final AutoresearchRunRecord.
        """
        record = self._require_record()
        record.max_iterations = max_iterations
        _write_run_record(self._cwd, record)

        # Baseline.
        await self.establish_baseline()

        for i in range(1, max_iterations + 1):
            if record.status != "running":
                break

            await self.run_iteration(i)
            decision = await self.process_candidate(i)

            if decision == "abort":
                record.status = "stopped"
                record.stop_reason = "candidate abort"
                break

            if decision == "error":
                record.status = "failed"
                record.stop_reason = "unrecoverable error in candidate processing"
                break

            trailing_noops = _count_trailing_noops(self._cwd)
            if trailing_noops >= _MAX_CONSECUTIVE_NOOPS:
                record.status = "stopped"
                record.stop_reason = f"abort: {trailing_noops} consecutive noops"
                break

        if record.status == "running":
            record.status = "completed"
            record.stop_reason = f"max_iterations ({max_iterations}) reached"

        record.completed_at = _now_iso()
        _write_run_record(self._cwd, record)
        return record

    def get_ledger(self) -> list[dict[str, Any]]:
        """Return all ledger entries for the current run."""
        ledger = _read_ledger(self._cwd)
        return ledger.get("entries", [])

    def get_record(self) -> Optional[AutoresearchRunRecord]:
        """Return the current run record (or None if prepare() not called)."""
        return self._record or _read_run_record(self._cwd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_record(self) -> AutoresearchRunRecord:
        if self._record is None:
            self._record = _read_run_record(self._cwd)
        if self._record is None:
            raise RuntimeError(
                "autoresearch_not_prepared: call prepare() before running."
            )
        return self._record

    def _require_contract(self) -> AutoresearchMissionContract:
        if self._contract is None:
            raise RuntimeError(
                "autoresearch_not_prepared: call prepare() before running."
            )
        return self._contract
