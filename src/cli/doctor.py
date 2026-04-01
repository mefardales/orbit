"""Environment diagnostics, mirrors src/cli/doctor.ts."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .constants import DEFAULT_CONFIG_DIR, DEFAULT_DATA_DIR, EXIT_ERROR, EXIT_OK


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ''


@dataclass
class DiagnosticReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def summary(self) -> str:
        lines: list[str] = []
        for c in self.checks:
            icon = 'OK' if c.ok else 'FAIL'
            lines.append(f'  [{icon}] {c.name}')
            if c.detail:
                lines.append(f'        {c.detail}')
        passed = sum(1 for c in self.checks if c.ok)
        lines.append(f'\n{passed}/{len(self.checks)} checks passed.')
        return '\n'.join(lines)


def _check_python_version() -> Check:
    vi = sys.version_info
    ok = vi >= (3, 10)
    return Check('Python >= 3.10', ok, f'found {vi.major}.{vi.minor}.{vi.micro}')


def _check_git() -> Check:
    found = shutil.which('git') is not None
    return Check('git available', found)


def _check_config_dir() -> Check:
    exists = DEFAULT_CONFIG_DIR.is_dir()
    return Check('config directory exists', exists, str(DEFAULT_CONFIG_DIR))


def _check_data_dir() -> Check:
    exists = DEFAULT_DATA_DIR.is_dir()
    return Check('data directory exists', exists, str(DEFAULT_DATA_DIR))


def _check_node() -> Check:
    found = shutil.which('node') is not None
    return Check('node available (optional)', found)


def run_doctor(*, fix: bool = False) -> int:
    """Run all diagnostic checks and print a report.

    If *fix* is True, attempt to create missing directories.
    """
    if fix:
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    report = DiagnosticReport(checks=[
        _check_python_version(),
        _check_git(),
        _check_config_dir(),
        _check_data_dir(),
        _check_node(),
    ])
    print(report.summary())
    return EXIT_OK if report.passed else EXIT_ERROR
