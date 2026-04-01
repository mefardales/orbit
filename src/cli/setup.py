"""First-time setup wizard, mirrors src/cli/setup.ts."""

from __future__ import annotations

from pathlib import Path

from .constants import DEFAULT_CONFIG_DIR, DEFAULT_DATA_DIR, EXIT_OK


def run_setup_wizard() -> int:
    """Create default directories and placeholder config files."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    config_file = DEFAULT_CONFIG_DIR / 'config.json'
    if not config_file.exists():
        config_file.write_text('{}')
        print(f'Created {config_file}')

    print('Setup complete.')
    return EXIT_OK
