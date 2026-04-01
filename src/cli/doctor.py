"""Orbit environment diagnostics - expanded 10+ check suite.

Each check produces a named result with PASS / FAIL / WARN status and a
detail message. The --fix flag attempts remediation where possible.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .constants import EXIT_ERROR, EXIT_OK

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CheckStatus = Literal["PASS", "FAIL", "WARN"]

_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _c(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


@dataclass
class Check:
    name: str
    status: CheckStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "PASS"

    def format_line(self) -> str:
        if self.status == "PASS":
            icon = _c("[PASS]", _GREEN)
        elif self.status == "WARN":
            icon = _c("[WARN]", _YELLOW)
        else:
            icon = _c("[FAIL]", _RED)
        detail = f"  {_c(self.detail, _DIM)}" if self.detail else ""
        return f"  {icon}  {self.name}{detail}"


@dataclass
class DiagnosticReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.status != "FAIL" for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "PASS")

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    def summary(self) -> str:
        lines: list[str] = [f"\n{_c('Orbit Doctor', _BOLD)}\n"]
        for c in self.checks:
            lines.append(c.format_line())
        verdict = _c("All checks passed.", _GREEN) if self.passed else _c("Some checks failed.", _RED)
        lines.append(
            f"\n  {self.pass_count} passed, {self.warn_count} warned, {self.fail_count} failed."
            f"  {verdict}\n"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _orbit_dir() -> Path:
    return Path.home() / ".orbit"


def _pkg_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)


# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------

def _check_python_version() -> Check:
    vi = sys.version_info
    ok = vi >= (3, 9)
    status: CheckStatus = "PASS" if ok else "FAIL"
    return Check(
        name="Python version (>=3.9)",
        status=status,
        detail=f"{vi.major}.{vi.minor}.{vi.micro}",
    )


def _check_platform() -> Check:
    import platform
    return Check(
        name="Platform",
        status="PASS",
        detail=f"{sys.platform} / {platform.machine()} / Python {platform.python_implementation()}",
    )


def _check_git() -> Check:
    if shutil.which("git") is None:
        return Check(name="git availability", status="FAIL", detail="git not found in PATH")
    try:
        result = _run(["git", "--version"])
        version = result.stdout.strip()
    except Exception as exc:
        return Check(name="git availability", status="FAIL", detail=str(exc))
    return Check(name="git availability", status="PASS", detail=version)


def _check_orbit_dirs() -> Check:
    orbit = _orbit_dir()
    required = ["prompts", "skills", "state", "backups", "agents"]
    missing = [sub for sub in required if not (orbit / sub).is_dir()]
    if not orbit.is_dir():
        return Check(
            name="~/.orbit/ directory structure",
            status="FAIL",
            detail=f"{orbit} does not exist - run `orbit setup`",
        )
    if missing:
        return Check(
            name="~/.orbit/ directory structure",
            status="WARN",
            detail=f"Missing subdirs: {', '.join(missing)} - run `orbit setup`",
        )
    return Check(
        name="~/.orbit/ directory structure",
        status="PASS",
        detail=str(orbit),
    )


def _check_prompts_installed() -> Check:
    orbit = _orbit_dir()
    prompts_dir = orbit / "prompts"
    pkg_prompts = _pkg_root() / "prompts"

    installed = list(prompts_dir.glob("*.md")) if prompts_dir.is_dir() else []
    baseline = list(pkg_prompts.glob("*.md")) if pkg_prompts.is_dir() else []

    if not installed:
        return Check(
            name="Prompt files installed",
            status="FAIL",
            detail=f"0 installed / {len(baseline)} available - run `orbit setup`",
        )
    if len(installed) < len(baseline):
        return Check(
            name="Prompt files installed",
            status="WARN",
            detail=f"{len(installed)} installed / {len(baseline)} available",
        )
    return Check(
        name="Prompt files installed",
        status="PASS",
        detail=f"{len(installed)} prompt files",
    )


def _check_skills_installed() -> Check:
    orbit = _orbit_dir()
    skills_dir = orbit / "skills"
    pkg_skills = _pkg_root() / "skills"

    if not skills_dir.is_dir():
        return Check(name="Skill files installed", status="FAIL",
                     detail="~/.orbit/skills/ not found - run `orbit setup`")

    installed = [d for d in skills_dir.iterdir() if d.is_dir()]
    baseline = [d for d in pkg_skills.iterdir() if d.is_dir() and (d / "SKILL.md").exists()] if pkg_skills.is_dir() else []

    if not installed:
        return Check(name="Skill files installed", status="WARN",
                     detail=f"0 skills installed / {len(baseline)} available")
    return Check(
        name="Skill files installed",
        status="PASS",
        detail=f"{len(installed)} skills installed",
    )


def _check_agent_definitions() -> Check:
    try:
        from ..agents.definitions import AGENT_DEFINITIONS
        count = len(AGENT_DEFINITIONS)
        return Check(name="Agent definitions loaded", status="PASS",
                     detail=f"{count} agents defined")
    except Exception as exc:
        return Check(name="Agent definitions loaded", status="FAIL", detail=str(exc))


def _check_config_validity() -> Check:
    config_path = _orbit_dir() / "config.json"
    if not config_path.exists():
        return Check(name="Config file validity", status="WARN",
                     detail="~/.orbit/config.json not found - run `orbit setup`")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return Check(name="Config file validity", status="PASS",
                     detail=f"Valid JSON ({len(data)} keys)")
    except Exception as exc:
        return Check(name="Config file validity", status="FAIL",
                     detail=f"Invalid JSON: {exc}")


def _check_tmux() -> Check:
    """Optional: tmux availability (required for team mode)."""
    if shutil.which("tmux") is None:
        return Check(name="tmux availability (optional - team mode)", status="WARN",
                     detail="tmux not found; team mode unavailable")
    try:
        result = _run(["tmux", "-V"])
        version = result.stdout.strip()
    except Exception as exc:
        return Check(name="tmux availability (optional - team mode)", status="WARN",
                     detail=str(exc))
    return Check(name="tmux availability (optional - team mode)", status="PASS", detail=version)


def _check_api_key() -> Check:
    """Optional: at least one provider API key or Ollama reachable."""
    import os
    key_vars = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ORBIT_API_KEY",
                "DEEPSEEK_API_KEY", "GROQ_API_KEY", "XAI_API_KEY"]
    found = [v for v in key_vars if os.environ.get(v)]
    if found:
        return Check(name="API key configured (optional)", status="PASS",
                     detail=f"Found: {', '.join(found)}")

    # Fallback: check Ollama is reachable
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return Check(name="API key configured (optional)", status="PASS",
                         detail="Ollama reachable at localhost:11434")
    except Exception:
        pass

    # Also check config.json
    config_path = _orbit_dir() / "config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            if data.get("api_key") or data.get("provider") == "ollama":
                return Check(name="API key configured (optional)", status="PASS",
                             detail="Key in ~/.orbit/config.json")
        except Exception:
            pass

    return Check(name="API key configured (optional)", status="WARN",
                 detail="No API key found; set ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.")


# ---------------------------------------------------------------------------
# Team diagnostics (only when team state exists)
# ---------------------------------------------------------------------------

def _find_team_state_dirs() -> list[Path]:
    """Return all team state directories under ~/.orbit/state/team/ and ./.omx/state/team/."""
    candidates: list[Path] = []
    for base in [_orbit_dir() / "state" / "team", Path.cwd() / ".omx" / "state" / "team"]:
        if base.is_dir():
            candidates.extend(d for d in base.iterdir() if d.is_dir())
    return candidates


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.rstrip("Z")).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _check_team_diagnostics() -> list[Check]:
    """Run team-specific checks when team state directories exist."""
    team_dirs = _find_team_state_dirs()
    if not team_dirs:
        return []

    checks: list[Check] = []
    now = datetime.now(timezone.utc)
    stale_heartbeats: list[str] = []
    shutdown_hangs: list[str] = []
    orphan_workers: list[str] = []

    for team_dir in team_dirs:
        team_name = team_dir.name
        workers_dir = team_dir / "workers"
        if not workers_dir.is_dir():
            continue

        for worker_dir in workers_dir.iterdir():
            if not worker_dir.is_dir():
                continue
            worker_name = worker_dir.name

            # Stale heartbeat check (>60s)
            hb_path = worker_dir / "heartbeat.json"
            if hb_path.exists():
                try:
                    hb = json.loads(hb_path.read_text())
                    last_turn = _parse_iso(hb.get("last_turn_at", ""))
                    if last_turn:
                        age_s = (now - last_turn).total_seconds()
                        if age_s > 60 and hb.get("alive", True):
                            stale_heartbeats.append(f"{team_name}/{worker_name} ({int(age_s)}s)")
                except Exception:
                    pass

            # Status check for shutdown hang (>30s in shutdown state)
            st_path = worker_dir / "status.json"
            if st_path.exists():
                try:
                    st = json.loads(st_path.read_text())
                    if st.get("state") == "shutdown":
                        updated = _parse_iso(st.get("updated_at", ""))
                        if updated:
                            age_s = (now - updated).total_seconds()
                            if age_s > 30:
                                shutdown_hangs.append(f"{team_name}/{worker_name} ({int(age_s)}s)")
                except Exception:
                    pass

            # Orphan: alive in state but no tmux session
            if hb_path.exists():
                try:
                    hb = json.loads(hb_path.read_text())
                    if hb.get("alive"):
                        session_name = f"orbit-team-{team_name}-{worker_name}"
                        if shutil.which("tmux"):
                            result = subprocess.run(
                                ["tmux", "has-session", "-t", session_name],
                                capture_output=True,
                            )
                            if result.returncode != 0:
                                orphan_workers.append(session_name)
                except Exception:
                    pass

    if stale_heartbeats:
        checks.append(Check(
            name="Team: stale heartbeats (>60s)",
            status="WARN",
            detail=", ".join(stale_heartbeats),
        ))
    else:
        checks.append(Check(name="Team: stale heartbeats (>60s)", status="PASS",
                            detail=f"All workers active across {len(team_dirs)} team(s)"))

    if shutdown_hangs:
        checks.append(Check(
            name="Team: shutdown hangs (>30s)",
            status="WARN",
            detail=", ".join(shutdown_hangs),
        ))
    else:
        checks.append(Check(name="Team: shutdown hangs (>30s)", status="PASS", detail="None detected"))

    if orphan_workers:
        checks.append(Check(
            name="Team: orphan worker sessions",
            status="WARN",
            detail=f"Orphaned tmux sessions: {', '.join(orphan_workers)}",
        ))
    else:
        checks.append(Check(name="Team: orphan worker sessions", status="PASS", detail="None detected"))

    return checks


# ---------------------------------------------------------------------------
# Fix actions
# ---------------------------------------------------------------------------

def _attempt_fix(report: DiagnosticReport, verbose: bool = False) -> list[str]:
    """Attempt to fix detected issues. Returns list of actions taken."""
    actions: list[str] = []
    orbit = _orbit_dir()

    for check in report.checks:
        if check.status == "PASS":
            continue

        if "directory structure" in check.name and not orbit.is_dir():
            from .setup import setup_full
            setup_full(scope="user", verbose=verbose)
            actions.append("Ran `orbit setup` to create directory structure")
            break  # setup handles everything

        if "Prompt files" in check.name or "Skill files" in check.name:
            if not any("setup" in a for a in actions):
                from .setup import setup_full
                setup_full(scope="user", verbose=verbose)
                actions.append("Ran `orbit setup` to install prompts and skills")
            break

        if "Config file" in check.name:
            config_path = orbit / "config.json"
            orbit.mkdir(parents=True, exist_ok=True)
            if not config_path.exists():
                config_path.write_text(json.dumps({"provider": "anthropic", "model": ""}, indent=2))
                actions.append("Created default ~/.orbit/config.json")

    return actions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_doctor(*, fix: bool = False, verbose: bool = False) -> int:
    """Run all diagnostic checks and print a report.

    Args:
        fix:     If True, attempt to remediate failures automatically.
        verbose: If True, emit extra per-check context.
    """
    checks: list[Check] = [
        _check_python_version(),
        _check_platform(),
        _check_git(),
        _check_orbit_dirs(),
        _check_prompts_installed(),
        _check_skills_installed(),
        _check_agent_definitions(),
        _check_config_validity(),
        _check_tmux(),
        _check_api_key(),
    ]

    # Team diagnostics (conditional)
    checks.extend(_check_team_diagnostics())

    report = DiagnosticReport(checks=checks)
    print(report.summary())

    if fix and not report.passed:
        actions = _attempt_fix(report, verbose=verbose)
        if actions:
            print("  Fix actions taken:")
            for action in actions:
                print(f"    - {action}")
            # Re-run to show updated state
            print("\n  Re-checking after fixes...\n")
            return run_doctor(fix=False)

    return EXIT_OK if report.passed else EXIT_ERROR
