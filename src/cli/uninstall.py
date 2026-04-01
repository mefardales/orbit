"""Uninstall Orbit from the current project or user scope."""
from __future__ import annotations

import shutil
from pathlib import Path


_PROJECT_ARTIFACTS = [
    '.orbit',
    '.omx',
    'AGENTS.md',
]

_USER_DIR = Path.home() / '.orbit'


def run_uninstall(scope: str = 'project', dry_run: bool = False) -> int:
    """Remove Orbit artifacts from the project or user directory."""
    removed: list[str] = []

    if scope in ('project', 'all'):
        cwd = Path.cwd()
        for name in _PROJECT_ARTIFACTS:
            target = cwd / name
            if target.exists():
                if dry_run:
                    print(f'  [dry-run] would remove {target}')
                else:
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    print(f'  removed {target}')
                removed.append(str(target))

    if scope in ('user', 'all'):
        if _USER_DIR.exists():
            if dry_run:
                print(f'  [dry-run] would remove {_USER_DIR}')
            else:
                shutil.rmtree(_USER_DIR)
                print(f'  removed {_USER_DIR}')
            removed.append(str(_USER_DIR))

    if not removed:
        print('  Nothing to remove.')
    elif not dry_run:
        print(f'\n  Orbit uninstalled ({len(removed)} items removed).')
        print('  To fully remove the package: pip uninstall orbit')

    return 0
