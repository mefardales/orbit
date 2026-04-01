"""CLI module ported from orbit src/cli/.

This module provides the command-line interface for omx (orbit),
including subcommands for agents, autoresearch, setup, doctor, version,
and other utilities.

Upstream TypeScript files (25):
    agents-init.ts, agents.ts, ask.ts, autoresearch-guided.ts,
    autoresearch-intake.ts, autoresearch.ts, catalog-contract.ts,
    cleanup.ts, constants.ts, doctor.ts, explore.ts, hooks.ts,
    index.ts, native-assets.ts, omx.ts, ralph.ts, session-search.ts,
    setup.ts, sparkshell.ts, star-prompt.ts, team.ts, tmux-hook.ts,
    uninstall.ts, update.ts, version.ts
"""

from __future__ import annotations

from .commands import build_cli, run_cli
from .constants import CLI_NAME, DEFAULT_CONFIG_DIR, DEFAULT_DATA_DIR

__all__ = [
    'CLI_NAME',
    'DEFAULT_CONFIG_DIR',
    'DEFAULT_DATA_DIR',
    'build_cli',
    'run_cli',
]
