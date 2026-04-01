"""Git worktree management for team workers.

Provides planning, creation, validation, and rollback of git worktrees
used to isolate worker changes during team execution.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Union


# ── Worktree mode types ──────────────────────────────────────────────────────


@dataclass
class WorktreeModeDisabled:
    enabled: Literal[False] = False


@dataclass
class WorktreeModeDetached:
    enabled: Literal[True] = True
    detached: Literal[True] = True
    name: None = None


@dataclass
class WorktreeModeNamed:
    enabled: Literal[True] = True
    detached: Literal[False] = False
    name: str = ""


WorktreeMode = Union[WorktreeModeDisabled, WorktreeModeDetached, WorktreeModeNamed]

WorktreeScope = Literal["launch", "team", "autoresearch"]

BRANCH_IN_USE_PATTERN = re.compile(
    r"already checked out|already used by worktree|is already checked out", re.I
)


# ── Git worktree entry ───────────────────────────────────────────────────────


@dataclass
class GitWorktreeEntry:
    path: str
    head: str
    branch_ref: Optional[str]
    detached: bool


# ── Plan / result types ──────────────────────────────────────────────────────


@dataclass
class PlannedWorktreeTarget:
    enabled: Literal[True] = True
    scope: WorktreeScope = "team"
    repo_root: str = ""
    worktree_path: str = ""
    detached: bool = False
    base_ref: str = ""
    branch_name: Optional[str] = None


@dataclass
class EnsureWorktreeResult:
    enabled: Literal[True] = True
    repo_root: str = ""
    worktree_path: str = ""
    detached: bool = False
    branch_name: Optional[str] = None
    created: bool = False
    reused: bool = False
    created_branch: bool = False


# ── Git helpers ───────────────────────────────────────────────────────────────


def _run_git(repo_root: str, args: List[str]) -> str:
    """Run a git command and return trimmed stdout. Raises on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def is_git_repository(cwd: str) -> bool:
    """Check if a directory is inside a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _sanitize_path_token(value: str) -> str:
    """Sanitize a string for use as a path component."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "default"


def _branch_exists(repo_root: str, branch_name: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        cwd=repo_root,
        capture_output=True,
    )
    return result.returncode == 0


def _validate_branch_name(repo_root: str, branch_name: str) -> None:
    result = subprocess.run(
        ["git", "check-ref-format", "--branch", branch_name],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"Invalid worktree branch: {branch_name}")


def _is_worktree_dirty(worktree_path: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"worktree_status_failed:{worktree_path}")
    return bool(result.stdout.strip())


def list_worktrees(repo_root: str) -> List[GitWorktreeEntry]:
    """List all git worktrees for a repository (public interface).

    Runs ``git worktree list --porcelain`` and parses the output into
    :class:`GitWorktreeEntry` objects.  Returns an empty list when the
    repository has no extra worktrees or when ``git`` is unavailable.
    """
    return _list_worktrees(repo_root)


def _list_worktrees(repo_root: str) -> List[GitWorktreeEntry]:
    """List all git worktrees for a repository."""
    raw = _run_git(repo_root, ["worktree", "list", "--porcelain"])
    if not raw:
        return []

    entries: List[GitWorktreeEntry] = []
    for chunk in re.split(r"\n\n+", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        wt_line = next((l for l in lines if l.startswith("worktree ")), None)
        head_line = next((l for l in lines if l.startswith("HEAD ")), None)
        branch_line = next((l for l in lines if l.startswith("branch ")), None)
        if not wt_line or not head_line:
            continue

        entries.append(GitWorktreeEntry(
            path=str(Path(wt_line[len("worktree "):]).resolve()),
            head=head_line[len("HEAD "):].strip(),
            branch_ref=branch_line[len("branch "):].strip() if branch_line else None,
            detached="detached" in lines or not branch_line,
        ))

    return entries


def _find_worktree_by_path(entries: List[GitWorktreeEntry], path: str) -> Optional[GitWorktreeEntry]:
    resolved = str(Path(path).resolve())
    for entry in entries:
        if str(Path(entry.path).resolve()) == resolved:
            return entry
    return None


def _has_branch_in_use(entries: List[GitWorktreeEntry], branch_name: str, worktree_path: str) -> bool:
    expected_ref = f"refs/heads/{branch_name}"
    resolved = str(Path(worktree_path).resolve())
    return any(
        e.branch_ref == expected_ref and str(Path(e.path).resolve()) != resolved
        for e in entries
    )


# ── Workspace validation ─────────────────────────────────────────────────────


def read_workspace_status_lines(cwd: str) -> List[str]:
    """Read git status lines for workspace cleanliness checks."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"workspace_status_failed:{cwd}")
    return [line.rstrip() for line in result.stdout.splitlines() if line.strip()]


def assert_clean_leader_workspace(cwd: str) -> None:
    """Raise if the leader workspace has uncommitted changes."""
    lines = read_workspace_status_lines(cwd)
    if lines:
        preview = " | ".join(lines[:8])
        raise RuntimeError(
            f"leader_workspace_dirty_for_worktrees:{Path(cwd).resolve()}:"
            f"{preview}:commit_or_stash_before_team"
        )


# ── Worktree planning ────────────────────────────────────────────────────────


def _resolve_branch_name(
    scope: WorktreeScope,
    mode: WorktreeMode,
    worker_name: Optional[str] = None,
    worktree_tag: Optional[str] = None,
) -> Optional[str]:
    if not mode.enabled or mode.detached:
        return None
    assert isinstance(mode, WorktreeModeNamed)

    if scope == "launch":
        return mode.name
    if scope == "autoresearch":
        tag = _sanitize_path_token(worktree_tag or "run")
        return f"autoresearch/{_sanitize_path_token(mode.name)}/{tag}"

    # team scope
    if not worker_name or not worker_name.strip():
        raise ValueError("team_worktree_worker_name_required")
    return f"{mode.name}/{worker_name}"


def _resolve_worktree_path(
    scope: WorktreeScope,
    mode: WorktreeMode,
    repo_root: str,
    team_name: Optional[str] = None,
    worker_name: Optional[str] = None,
    worktree_tag: Optional[str] = None,
) -> str:
    parent = Path(repo_root).parent
    bucket = f"{Path(repo_root).name}.omx-worktrees"

    if scope == "launch":
        if not mode.enabled or mode.detached:
            return str(parent / bucket / "launch-detached")
        assert isinstance(mode, WorktreeModeNamed)
        return str(parent / bucket / f"launch-{_sanitize_path_token(mode.name)}")

    if scope == "autoresearch":
        if not mode.enabled or mode.detached:
            raise ValueError("autoresearch_worktree_requires_named_mode")
        assert isinstance(mode, WorktreeModeNamed)
        tag = _sanitize_path_token(worktree_tag or "run")
        return str(
            Path(repo_root) / ".omx" / "worktrees"
            / f"autoresearch-{_sanitize_path_token(mode.name)}-{tag}"
        )

    # team scope
    tn = _sanitize_path_token(team_name or "team")
    wn = _sanitize_path_token(worker_name or "worker")
    return str(Path(repo_root) / ".omx" / "team" / tn / "worktrees" / wn)


def plan_worktree_target(
    cwd: str,
    scope: WorktreeScope,
    mode: WorktreeMode,
    team_name: Optional[str] = None,
    worker_name: Optional[str] = None,
    worktree_tag: Optional[str] = None,
) -> Union[PlannedWorktreeTarget, WorktreeModeDisabled]:
    """Plan a worktree target without creating it."""
    if not mode.enabled:
        return WorktreeModeDisabled()

    repo_root = _run_git(cwd, ["rev-parse", "--show-toplevel"])
    base_ref = _run_git(repo_root, ["rev-parse", "HEAD"])
    branch_name = _resolve_branch_name(scope, mode, worker_name, worktree_tag)

    if branch_name:
        _validate_branch_name(repo_root, branch_name)

    return PlannedWorktreeTarget(
        scope=scope,
        repo_root=repo_root,
        worktree_path=_resolve_worktree_path(
            scope, mode, repo_root, team_name, worker_name, worktree_tag
        ),
        detached=mode.detached if hasattr(mode, "detached") else False,
        base_ref=base_ref,
        branch_name=branch_name,
    )


# ── Worktree creation ────────────────────────────────────────────────────────


def ensure_worktree(
    plan: Union[PlannedWorktreeTarget, WorktreeModeDisabled],
) -> Union[EnsureWorktreeResult, WorktreeModeDisabled]:
    """Create or reuse a worktree based on the plan."""
    if isinstance(plan, WorktreeModeDisabled) or not plan.enabled:
        return WorktreeModeDisabled()

    all_worktrees = _list_worktrees(plan.repo_root)
    existing = _find_worktree_by_path(all_worktrees, plan.worktree_path)

    if existing:
        if plan.detached:
            if not existing.detached or existing.head != plan.base_ref:
                raise RuntimeError(f"worktree_target_mismatch:{plan.worktree_path}")
        elif existing.branch_ref != (f"refs/heads/{plan.branch_name}" if plan.branch_name else None):
            raise RuntimeError(f"worktree_target_mismatch:{plan.worktree_path}")

        if _is_worktree_dirty(plan.worktree_path):
            raise RuntimeError(f"worktree_dirty:{plan.worktree_path}")

        return EnsureWorktreeResult(
            repo_root=plan.repo_root,
            worktree_path=str(Path(plan.worktree_path).resolve()),
            detached=plan.detached,
            branch_name=plan.branch_name,
            created=False,
            reused=True,
            created_branch=False,
        )

    wt_path = Path(plan.worktree_path)
    if wt_path.exists():
        raise RuntimeError(f"worktree_path_conflict:{plan.worktree_path}")

    if plan.branch_name and _has_branch_in_use(all_worktrees, plan.branch_name, plan.worktree_path):
        raise RuntimeError(f"branch_in_use:{plan.branch_name}")

    wt_path.parent.mkdir(parents=True, exist_ok=True)
    branch_existed = _branch_exists(plan.repo_root, plan.branch_name) if plan.branch_name else False

    add_args = ["worktree", "add"]
    if plan.detached:
        add_args.extend(["--detach", plan.worktree_path, plan.base_ref])
    elif branch_existed:
        add_args.extend([plan.worktree_path, plan.branch_name])  # type: ignore[arg-type]
    else:
        add_args.extend(["-b", plan.branch_name, plan.worktree_path, plan.base_ref])  # type: ignore[arg-type]

    result = subprocess.run(
        ["git", *add_args],
        cwd=plan.repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if plan.branch_name and BRANCH_IN_USE_PATTERN.search(stderr):
            raise RuntimeError(f"branch_in_use:{plan.branch_name}")
        raise RuntimeError(stderr or f"worktree_add_failed:{' '.join(add_args)}")

    return EnsureWorktreeResult(
        repo_root=plan.repo_root,
        worktree_path=str(Path(plan.worktree_path).resolve()),
        detached=plan.detached,
        branch_name=plan.branch_name,
        created=True,
        reused=False,
        created_branch=bool(plan.branch_name and not branch_existed),
    )


# ── Worktree rollback ────────────────────────────────────────────────────────


def rollback_provisioned_worktrees(
    results: List[Union[EnsureWorktreeResult, WorktreeModeDisabled]],
    skip_branch_deletion: bool = False,
) -> None:
    """Roll back worktrees that were created during provisioning."""
    created = [
        r for r in results
        if isinstance(r, EnsureWorktreeResult) and r.enabled and r.created
    ]
    created.reverse()

    errors: List[str] = []

    for wt in created:
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", wt.worktree_path],
                cwd=wt.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            errors.append(f"remove:{wt.worktree_path}:{e.stderr.strip()}")
            continue

        if skip_branch_deletion:
            continue
        if not wt.created_branch or not wt.branch_name:
            continue

        all_wts = _list_worktrees(wt.repo_root)
        if _has_branch_in_use(all_wts, wt.branch_name, wt.worktree_path):
            continue

        try:
            subprocess.run(
                ["git", "branch", "-D", wt.branch_name],
                cwd=wt.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            if _branch_exists(wt.repo_root, wt.branch_name):
                errors.append(f"delete_branch:{wt.branch_name}:{e.stderr.strip()}")

    if errors:
        raise RuntimeError(f"worktree_rollback_failed:{' | '.join(errors)}")


# ── Parse worktree mode from CLI args ────────────────────────────────────────


def parse_worktree_mode(args: List[str]) -> Tuple[WorktreeMode, List[str]]:
    """Parse --worktree / -w flags from argument list.

    Returns (mode, remaining_args).
    """
    mode: WorktreeMode = WorktreeModeDisabled()
    remaining: List[str] = []
    i = 0

    while i < len(args):
        arg = args[i]

        if arg in ("--worktree", "-w"):
            nxt = args[i + 1] if i + 1 < len(args) else None
            if nxt and not nxt.startswith("-") and ":" not in nxt:
                mode = WorktreeModeNamed(name=nxt)
                i += 2
            else:
                mode = WorktreeModeDetached()
                i += 1
            continue

        if arg.startswith("--worktree="):
            value = arg[len("--worktree="):].strip()
            mode = WorktreeModeNamed(name=value) if value else WorktreeModeDetached()
            i += 1
            continue

        if arg.startswith("-w="):
            value = arg[3:].strip()
            mode = WorktreeModeNamed(name=value) if value else WorktreeModeDetached()
            i += 1
            continue

        if arg.startswith("-w") and len(arg) > 2:
            value = arg[2:].strip()
            mode = WorktreeModeNamed(name=value) if value else WorktreeModeDetached()
            i += 1
            continue

        remaining.append(arg)
        i += 1

    return mode, remaining
