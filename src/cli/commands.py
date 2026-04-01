"""CLI entry point and subcommand registry.

Mirrors src/cli/index.ts and src/cli/omx.ts from orbit.
Each subcommand is registered via argparse and dispatched to the
appropriate handler function.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .constants import CLI_NAME, EXIT_ERROR, EXIT_OK, EXIT_USAGE


def build_cli() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description='orbit CLI - manage agents, research, catalogs, and more',
    )
    parser.add_argument('--version', action='store_true', help='print version and exit')
    parser.add_argument('--verbose', '-v', action='store_true', help='enable verbose output')

    sub = parser.add_subparsers(dest='subcommand')

    # --- ask ---
    ask_p = sub.add_parser('ask', help='send a one-shot prompt to an agent')
    ask_p.add_argument('prompt', nargs='+', help='the prompt text')
    ask_p.add_argument('--model', '-m', default=None, help='model override')

    # --- agents ---
    agents_p = sub.add_parser('agents', help='list or inspect configured agents')
    agents_p.add_argument('--init', action='store_true', help='initialise default agent configs')
    agents_p.add_argument('--json', action='store_true', help='output as JSON')

    # --- autoresearch ---
    ar_p = sub.add_parser('autoresearch', help='run automated research pipeline')
    ar_p.add_argument('topic', nargs='?', default=None, help='research topic')
    ar_p.add_argument('--guided', action='store_true', help='interactive guided mode')
    ar_p.add_argument('--intake', action='store_true', help='intake-only mode')

    # --- catalog ---
    cat_p = sub.add_parser('catalog', help='manage the contract catalog')
    cat_p.add_argument('action', nargs='?', choices=['list', 'show', 'validate'], default='list')
    cat_p.add_argument('name', nargs='?', default=None)

    # --- doctor ---
    doc_p = sub.add_parser('doctor', help='diagnose environment and configuration issues')
    doc_p.add_argument('--fix', action='store_true', help='attempt automatic fixes')

    # --- explore ---
    exp_p = sub.add_parser('explore', help='explore codebase structure')
    exp_p.add_argument('path', nargs='?', default='.', help='root path to explore')

    # --- setup ---
    sub.add_parser('setup', help='run first-time setup wizard')

    # --- cleanup ---
    sub.add_parser('cleanup', help='remove temporary files and caches')

    # --- hooks ---
    hooks_p = sub.add_parser('hooks', help='manage lifecycle hooks')
    hooks_p.add_argument('action', nargs='?', choices=['list', 'run', 'install'], default='list')
    hooks_p.add_argument('name', nargs='?', default=None)

    # --- session-search ---
    ss_p = sub.add_parser('session-search', help='search session history')
    ss_p.add_argument('query', help='search query')
    ss_p.add_argument('--limit', type=int, default=20)

    # --- team ---
    team_p = sub.add_parser('team', help='manage multi-agent team sessions')
    team_p.add_argument('action', nargs='?', choices=['start', 'status', 'stop'], default='status')

    # --- ralph ---
    ralph_p = sub.add_parser('ralph', help='run ralph verification')
    ralph_p.add_argument('target', nargs='?', default=None)

    # --- sparkshell ---
    sub.add_parser('sparkshell', help='launch interactive spark shell')

    # --- star-prompt ---
    sp_p = sub.add_parser('star-prompt', help='bookmark or recall a starred prompt')
    sp_p.add_argument('action', nargs='?', choices=['save', 'list', 'run'], default='list')
    sp_p.add_argument('name', nargs='?', default=None)

    # --- tmux-hook ---
    tmux_p = sub.add_parser('tmux-hook', help='manage tmux session hooks')
    tmux_p.add_argument('action', nargs='?', choices=['install', 'remove', 'status'], default='status')

    # --- update ---
    sub.add_parser('update', help='check for and apply updates')

    # --- uninstall ---
    sub.add_parser('uninstall', help='remove omx configuration and data')

    # --- version ---
    sub.add_parser('version', help='print version information')

    # --- native-assets ---
    na_p = sub.add_parser('native-assets', help='manage native (Rust) binary assets')
    na_p.add_argument('action', nargs='?', choices=['check', 'build', 'install'], default='check')

    return parser


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_version() -> int:
    from .version import print_version
    print_version()
    return EXIT_OK


def _handle_doctor(args: argparse.Namespace) -> int:
    from .doctor import run_doctor
    return run_doctor(fix=args.fix)


def _handle_setup(_args: argparse.Namespace) -> int:
    from .setup import run_setup_wizard
    return run_setup_wizard()


def _handle_ask(args: argparse.Namespace) -> int:
    from .ask import send_ask
    return send_ask(prompt=' '.join(args.prompt), model=args.model)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_SIMPLE_HANDLERS: dict[str, str] = {
    'version': '_handle_version',
}

_ARG_HANDLERS: dict[str, str] = {
    'doctor': '_handle_doctor',
    'setup': '_handle_setup',
    'ask': '_handle_ask',
}


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Parse *argv* and dispatch to the appropriate subcommand handler."""
    parser = build_cli()
    args = parser.parse_args(argv)

    if args.version:
        return _handle_version()

    if args.subcommand is None:
        parser.print_help()
        return EXIT_USAGE

    # Simple (no-arg) handlers
    if args.subcommand in _SIMPLE_HANDLERS:
        handler = globals()[_SIMPLE_HANDLERS[args.subcommand]]
        return handler()

    # Handlers that receive the parsed namespace
    if args.subcommand in _ARG_HANDLERS:
        handler = globals()[_ARG_HANDLERS[args.subcommand]]
        return handler(args)

    # Fallback: subcommand recognised by argparse but not yet wired up
    print(f'{CLI_NAME}: subcommand {args.subcommand!r} is not yet implemented', file=sys.stderr)
    return EXIT_ERROR
