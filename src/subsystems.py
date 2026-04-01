"""Orbit subsystem registry - loads all subsystem metadata from JSON definitions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SUBSYSTEMS_DIR = Path(__file__).resolve().parent / 'reference_data' / 'subsystems'


@dataclass(frozen=True)
class Subsystem:
    name: str
    module_count: int
    sample_files: tuple[str, ...]

    @property
    def description(self) -> str:
        return f'Orbit subsystem: {self.name} ({self.module_count} modules)'


def _load_subsystem(name: str) -> Subsystem:
    path = SUBSYSTEMS_DIR / f'{name}.json'
    data = json.loads(path.read_text())
    return Subsystem(
        name=data['archive_name'],
        module_count=data['module_count'],
        sample_files=tuple(data['sample_files']),
    )


SUBSYSTEM_NAMES = [
    'assistant', 'bootstrap', 'bridge', 'buddy', 'cli', 'components',
    'constants', 'coordinator', 'entrypoints', 'hooks', 'keybindings',
    'memdir', 'migrations', 'moreright', 'native_ts', 'outputStyles',
    'plugins', 'remote', 'schemas', 'screens', 'server', 'services',
    'skills', 'state', 'types', 'upstreamproxy', 'utils', 'vim', 'voice',
]

SUBSYSTEMS: dict[str, Subsystem] = {}


def load_all_subsystems() -> dict[str, Subsystem]:
    """Load all subsystem definitions. Cached after first call."""
    if SUBSYSTEMS:
        return SUBSYSTEMS
    for name in SUBSYSTEM_NAMES:
        try:
            SUBSYSTEMS[name] = _load_subsystem(name)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            continue
    return SUBSYSTEMS


def get_subsystem(name: str) -> Subsystem | None:
    """Get a single subsystem by name."""
    subs = load_all_subsystems()
    return subs.get(name)


def total_module_count() -> int:
    """Total modules across all subsystems."""
    return sum(s.module_count for s in load_all_subsystems().values())


def list_subsystems() -> list[Subsystem]:
    """List all subsystems sorted by module count (descending)."""
    return sorted(load_all_subsystems().values(), key=lambda s: -s.module_count)
