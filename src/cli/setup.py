"""Orbit setup pipeline - orchestrated 8-step installation.

Supports user scope (~/.orbit/) and project scope (./.orbit/).
Mirrors the oh-my-codex install pipeline pattern.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .constants import EXIT_ERROR, EXIT_OK

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORBIT_DIR_NAME = ".orbit"
ORBIT_SUBDIRS = ("prompts", "skills", "state", "backups", "agents")

Scope = Literal["user", "project"]

# ANSI codes (only emitted when stdout is a tty)
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _c(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


# ---------------------------------------------------------------------------
# Step result tracking
# ---------------------------------------------------------------------------

StepStatus = Literal["ok", "skip", "warn", "fail"]


@dataclass
class StepResult:
    step: int
    name: str
    status: StepStatus
    detail: str = ""
    items_installed: int = 0
    items_skipped: int = 0
    items_updated: int = 0


@dataclass
class SetupReport:
    scope: Scope
    orbit_dir: Path
    steps: list[StepResult] = field(default_factory=list)
    dry_run: bool = False

    @property
    def success(self) -> bool:
        return all(s.status != "fail" for s in self.steps)

    def add(self, result: StepResult) -> None:
        self.steps.append(result)

    def print_summary(self) -> None:
        width = 60
        print(f"\n{_c('Orbit Setup Summary', _BOLD)}")
        print(f"  Scope: {self.scope}  |  Dir: {self.orbit_dir}")
        if self.dry_run:
            print(f"  {_c('[DRY RUN - no changes written]', _YELLOW)}")
        print()
        for s in self.steps:
            if s.status == "ok":
                icon = _c("[OK]  ", _GREEN)
            elif s.status == "skip":
                icon = _c("[SKIP]", _DIM)
            elif s.status == "warn":
                icon = _c("[WARN]", _YELLOW)
            else:
                icon = _c("[FAIL]", _RED)
            line = f"  {icon} Step {s.step}: {s.name}"
            if s.items_installed or s.items_updated or s.items_skipped:
                counts: list[str] = []
                if s.items_installed:
                    counts.append(f"{s.items_installed} installed")
                if s.items_updated:
                    counts.append(f"{s.items_updated} updated")
                if s.items_skipped:
                    counts.append(f"{s.items_skipped} unchanged")
                line += f"  ({', '.join(counts)})"
            print(line)
            if s.detail:
                print(f"         {_c(s.detail, _DIM)}")
        total_ok = sum(1 for s in self.steps if s.status == "ok")
        total = len(self.steps)
        verdict = _c("All steps passed.", _GREEN) if self.success else _c("Some steps failed.", _RED)
        print(f"\n  {total_ok}/{total} steps passed. {verdict}\n")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pkg_root() -> Path:
    """Return the project package root (two levels above this file's src/)."""
    return Path(__file__).resolve().parent.parent.parent


def _file_hash(path: Path) -> str:
    """SHA-256 of a file's content, used for change detection."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _backup(src: Path, backups_dir: Path, dry_run: bool) -> Path:
    """Create a timestamped backup of src before overwriting it."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = backups_dir / f"{src.name}.{ts}.bak"
    if not dry_run:
        shutil.copy2(src, dst)
    return dst


def _install_file(
    src: Path,
    dst: Path,
    backups_dir: Path,
    dry_run: bool,
) -> Literal["installed", "updated", "skipped"]:
    """Copy src to dst.

    Returns:
      'installed' - dst did not exist, newly created
      'updated'   - dst existed but content differed, backed up and replaced
      'skipped'   - dst existed and content is identical
    """
    if dst.exists():
        if _file_hash(src) == _file_hash(dst):
            return "skipped"
        if not dry_run:
            _backup(dst, backups_dir, dry_run=False)
            shutil.copy2(src, dst)
        return "updated"
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return "installed"


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def _step1_create_directories(orbit_dir: Path, dry_run: bool) -> StepResult:
    """Create ~/.orbit/ and all required subdirectories."""
    created = 0
    for sub in ("", *ORBIT_SUBDIRS):
        d = orbit_dir / sub if sub else orbit_dir
        if not d.exists():
            if not dry_run:
                d.mkdir(parents=True, exist_ok=True)
            created += 1
    return StepResult(
        step=1,
        name="Directory creation",
        status="ok",
        detail=f"{orbit_dir}",
        items_installed=created,
        items_skipped=len(ORBIT_SUBDIRS) + 1 - created,
    )


def _step2_sync_prompts(orbit_dir: Path, pkg_root: Path, dry_run: bool) -> StepResult:
    """Copy .md prompt files from prompts/ into ~/.orbit/prompts/."""
    src_dir = pkg_root / "prompts"
    dst_dir = orbit_dir / "prompts"
    if not src_dir.is_dir():
        return StepResult(step=2, name="Prompt syncing", status="warn",
                          detail=f"No prompts/ directory found at {src_dir}")

    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = orbit_dir / "backups"

    installed = updated = skipped = 0
    for md_file in sorted(src_dir.glob("*.md")):
        result = _install_file(md_file, dst_dir / md_file.name, backups_dir, dry_run)
        if result == "installed":
            installed += 1
        elif result == "updated":
            updated += 1
        else:
            skipped += 1

    total = installed + updated + skipped
    return StepResult(
        step=2,
        name="Prompt syncing",
        status="ok",
        detail=f"{total} prompt files processed",
        items_installed=installed,
        items_updated=updated,
        items_skipped=skipped,
    )


def _step3_install_skills(orbit_dir: Path, pkg_root: Path, dry_run: bool) -> StepResult:
    """Validate and install skill manifests from skills/ to ~/.orbit/skills/."""
    src_dir = pkg_root / "skills"
    dst_dir = orbit_dir / "skills"
    if not src_dir.is_dir():
        return StepResult(step=3, name="Skill installation", status="warn",
                          detail=f"No skills/ directory found at {src_dir}")

    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = orbit_dir / "backups"

    installed = updated = skipped = invalid = 0
    for skill_dir in sorted(src_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            invalid += 1
            continue

        dst_skill_dir = dst_dir / skill_dir.name
        if not dry_run:
            dst_skill_dir.mkdir(parents=True, exist_ok=True)

        for src_file in sorted(skill_dir.rglob("*")):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(skill_dir)
            dst_file = dst_skill_dir / rel
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
            result = _install_file(src_file, dst_file, backups_dir, dry_run)
            if result == "installed":
                installed += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1

    detail_parts = [f"{installed + updated + skipped} files across {len(list(src_dir.iterdir()))} skills"]
    if invalid:
        detail_parts.append(f"{invalid} dirs skipped (no SKILL.md)")
    return StepResult(
        step=3,
        name="Skill installation",
        status="ok",
        detail=", ".join(detail_parts),
        items_installed=installed,
        items_updated=updated,
        items_skipped=skipped,
    )


def _step4_generate_agent_configs(orbit_dir: Path, pkg_root: Path, dry_run: bool) -> StepResult:
    """Generate native agent TOML configs from agent definitions."""
    try:
        from ..agents.native_config import generate_agent_toml, AGENT_DEFINITIONS
        from ..agents.definitions import AGENT_DEFINITIONS as DEFS
    except ImportError:
        return StepResult(step=4, name="Agent config generation", status="warn",
                          detail="Could not import agent definitions")

    agents_dir = orbit_dir / "agents"
    if not dry_run:
        agents_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = orbit_dir / "backups"
    prompts_dir = pkg_root / "prompts"

    installed = updated = skipped = 0
    for name, agent in DEFS.items():
        prompt_path = prompts_dir / f"{name}.md"
        if not prompt_path.is_file():
            continue
        prompt_content = prompt_path.read_text(encoding="utf-8")
        toml_content = generate_agent_toml(agent, prompt_content)
        dst = agents_dir / f"{name}.toml"

        if dry_run:
            skipped += 1
            continue

        if dst.exists():
            existing = dst.read_text(encoding="utf-8")
            if existing == toml_content:
                skipped += 1
                continue
            _backup(dst, backups_dir, dry_run=False)
            dst.write_text(toml_content, encoding="utf-8")
            updated += 1
        else:
            dst.write_text(toml_content, encoding="utf-8")
            installed += 1

    return StepResult(
        step=4,
        name="Agent config generation",
        status="ok",
        detail=f"TOML configs in {agents_dir}",
        items_installed=installed,
        items_updated=updated,
        items_skipped=skipped,
    )


def _step5_merge_config(orbit_dir: Path, pkg_root: Path, dry_run: bool) -> StepResult:
    """Merge project config with user config, preserving user overrides."""
    user_config_path = orbit_dir / "config.json"
    project_config_path = pkg_root / "orbit.config.json"

    # Default skeleton
    defaults: dict = {
        "provider": "anthropic",
        "model": "",
        "version": "1",
    }

    # Load project config if present
    project_config: dict = {}
    if project_config_path.exists():
        try:
            project_config = json.loads(project_config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Load existing user config (user overrides take priority)
    user_config: dict = {}
    existed = user_config_path.exists()
    if existed:
        try:
            user_config = json.loads(user_config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Merge: defaults < project < user
    merged = {**defaults, **project_config, **user_config}

    if not dry_run:
        orbit_dir.mkdir(parents=True, exist_ok=True)
        if existed:
            existing_text = user_config_path.read_text(encoding="utf-8")
            new_text = json.dumps(merged, indent=2)
            if existing_text.strip() != new_text.strip():
                _backup(user_config_path, orbit_dir / "backups", dry_run=False)
                user_config_path.write_text(new_text, encoding="utf-8")
                status: StepStatus = "ok"
                detail = "config.json updated (user overrides preserved)"
            else:
                status = "ok"
                detail = "config.json unchanged"
        else:
            user_config_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
            status = "ok"
            detail = f"config.json created at {user_config_path}"
    else:
        status = "ok"
        detail = "config merge dry-run (no changes written)"

    return StepResult(step=5, name="Config merging", status=status, detail=detail)


def _step6_verify(orbit_dir: Path, dry_run: bool = False) -> StepResult:
    """Verify all expected components are in place.

    In dry-run mode the directories won't have been created, so we check
    what the previous steps *would* install rather than what is on disk.
    """
    if dry_run:
        # In dry-run, steps 1-5 ran without writing; report a soft skip.
        return StepResult(
            step=6,
            name="Verification",
            status="skip",
            detail="skipped in dry-run mode (no writes occurred)",
        )

    failures: list[str] = []

    for sub in ORBIT_SUBDIRS:
        d = orbit_dir / sub
        if not d.is_dir():
            failures.append(f"missing dir: {d}")

    config_file = orbit_dir / "config.json"
    if not config_file.exists():
        failures.append("missing config.json")

    prompts_count = len(list((orbit_dir / "prompts").glob("*.md"))) if (orbit_dir / "prompts").is_dir() else 0
    skills_count = len([d for d in (orbit_dir / "skills").iterdir() if d.is_dir()]) if (orbit_dir / "skills").is_dir() else 0
    agents_count = len(list((orbit_dir / "agents").glob("*.toml"))) if (orbit_dir / "agents").is_dir() else 0

    if failures:
        return StepResult(step=6, name="Verification", status="fail",
                          detail="; ".join(failures))

    return StepResult(
        step=6,
        name="Verification",
        status="ok",
        detail=f"{prompts_count} prompts, {skills_count} skills, {agents_count} agent configs",
    )


def _step7_generate_agents_md(orbit_dir: Path, pkg_root: Path, dry_run: bool) -> StepResult:
    """Generate AGENTS.md with model tables from agent definitions."""
    try:
        from ..agents.definitions import AGENT_DEFINITIONS, get_agents_by_category
    except ImportError:
        return StepResult(step=7, name="AGENTS.md generation", status="warn",
                          detail="Could not import agent definitions")

    categories = ["build", "review", "domain", "product", "coordination"]
    lines: list[str] = [
        "# Orbit Agent Definitions",
        "",
        f"_Auto-generated by `orbit setup`. {len(AGENT_DEFINITIONS)} agents across {len(categories)} categories._",
        "",
    ]

    for cat in categories:
        agents = get_agents_by_category(cat)  # type: ignore[arg-type]
        if not agents:
            continue
        lines.append(f"## {cat.title()}")
        lines.append("")
        lines.append("| Agent | Description | Posture | Model Class | Reasoning | Routing |")
        lines.append("|-------|-------------|---------|-------------|-----------|---------|")
        for a in sorted(agents, key=lambda x: x.name):
            lines.append(
                f"| `{a.name}` | {a.description} | {a.posture} | {a.model_class} | {a.reasoning_effort} | {a.routing_role} |"
            )
        lines.append("")

    content = "\n".join(lines)
    dst = pkg_root / "AGENTS.md"

    if dry_run:
        return StepResult(step=7, name="AGENTS.md generation", status="ok",
                          detail=f"Would write {len(lines)} lines to {dst}")

    if dst.exists():
        existing = dst.read_text(encoding="utf-8")
        if existing.strip() == content.strip():
            return StepResult(step=7, name="AGENTS.md generation", status="ok",
                              detail="AGENTS.md unchanged", items_skipped=1)
        _backup(dst, orbit_dir / "backups", dry_run=False)
        dst.write_text(content, encoding="utf-8")
        return StepResult(step=7, name="AGENTS.md generation", status="ok",
                          detail=f"AGENTS.md updated ({len(AGENT_DEFINITIONS)} agents)", items_updated=1)
    else:
        dst.write_text(content, encoding="utf-8")
        return StepResult(step=7, name="AGENTS.md generation", status="ok",
                          detail=f"AGENTS.md created ({len(AGENT_DEFINITIONS)} agents)", items_installed=1)


def _step8_summary_report(report: SetupReport) -> StepResult:
    """Aggregate counts and emit final summary line."""
    total_installed = sum(s.items_installed for s in report.steps)
    total_updated = sum(s.items_updated for s in report.steps)
    total_skipped = sum(s.items_skipped for s in report.steps)
    failed_steps = [s for s in report.steps if s.status == "fail"]

    if failed_steps:
        detail = f"Failed steps: {', '.join(str(s.step) for s in failed_steps)}"
        status: StepStatus = "fail"
    else:
        detail = f"{total_installed} installed, {total_updated} updated, {total_skipped} unchanged"
        status = "ok"

    return StepResult(
        step=8,
        name="Summary report",
        status=status,
        detail=detail,
        items_installed=total_installed,
        items_updated=total_updated,
        items_skipped=total_skipped,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _resolve_orbit_dir(scope: Scope) -> Path:
    if scope == "user":
        return Path.home() / ORBIT_DIR_NAME
    return Path.cwd() / ORBIT_DIR_NAME


def setup_full(
    scope: Scope = "user",
    dry_run: bool = False,
    verbose: bool = False,
) -> SetupReport:
    """Run all 8 setup steps and return a SetupReport.

    Args:
        scope:   'user' for ~/.orbit/ (default) or 'project' for ./.orbit/
        dry_run: Preview changes without writing to disk.
        verbose: Print step results as they complete.
    """
    orbit_dir = _resolve_orbit_dir(scope)
    pkg_root = _pkg_root()
    report = SetupReport(scope=scope, orbit_dir=orbit_dir, dry_run=dry_run)

    steps = [
        lambda: _step1_create_directories(orbit_dir, dry_run),
        lambda: _step2_sync_prompts(orbit_dir, pkg_root, dry_run),
        lambda: _step3_install_skills(orbit_dir, pkg_root, dry_run),
        lambda: _step4_generate_agent_configs(orbit_dir, pkg_root, dry_run),
        lambda: _step5_merge_config(orbit_dir, pkg_root, dry_run),
        lambda: _step6_verify(orbit_dir, dry_run=dry_run),
        lambda: _step7_generate_agents_md(orbit_dir, pkg_root, dry_run),
        lambda: _step8_summary_report(report),
    ]

    for step_fn in steps:
        result = step_fn()
        report.add(result)
        if verbose:
            icon = "OK" if result.status in ("ok", "skip") else result.status.upper()
            print(f"  [{icon}] Step {result.step}: {result.name}  {result.detail}")

    return report


def setup_check(scope: Scope = "user") -> SetupReport:
    """Verify the installation without making any changes (dry_run=True + verify)."""
    orbit_dir = _resolve_orbit_dir(scope)
    pkg_root = _pkg_root()
    report = SetupReport(scope=scope, orbit_dir=orbit_dir, dry_run=True)

    # Only run directory check and verification
    report.add(_step1_create_directories(orbit_dir, dry_run=True))
    report.add(_step6_verify(orbit_dir))

    # Prompt count vs source
    src_prompts = list((pkg_root / "prompts").glob("*.md")) if (pkg_root / "prompts").is_dir() else []
    dst_prompts = list((orbit_dir / "prompts").glob("*.md")) if (orbit_dir / "prompts").is_dir() else []
    prompt_status: StepStatus = "ok" if len(dst_prompts) >= len(src_prompts) else "warn"
    report.add(StepResult(
        step=2,
        name="Prompt file check",
        status=prompt_status,
        detail=f"{len(dst_prompts)} installed / {len(src_prompts)} available in source",
    ))

    # Skill count vs source
    src_skills = [d for d in (pkg_root / "skills").iterdir() if d.is_dir() and (d / "SKILL.md").exists()] if (pkg_root / "skills").is_dir() else []
    dst_skills = [d for d in (orbit_dir / "skills").iterdir() if d.is_dir()] if (orbit_dir / "skills").is_dir() else []
    skill_status: StepStatus = "ok" if len(dst_skills) >= len(src_skills) else "warn"
    report.add(StepResult(
        step=3,
        name="Skill file check",
        status=skill_status,
        detail=f"{len(dst_skills)} installed / {len(src_skills)} available in source",
    ))

    return report


def run_setup_wizard(
    scope: Scope = "user",
    dry_run: bool = False,
    check_only: bool = False,
) -> int:
    """Entry point for CLI usage.

    Args:
        scope:      'user' or 'project'
        dry_run:    Preview only, no writes.
        check_only: Run setup_check() instead of full install.
    """
    if check_only:
        report = setup_check(scope=scope)
    else:
        print(f"{_c('Orbit Setup', _BOLD)}  scope={scope}" + (" [dry-run]" if dry_run else ""))
        print()
        report = setup_full(scope=scope, dry_run=dry_run, verbose=True)

    report.print_summary()
    return EXIT_OK if report.success else EXIT_ERROR
