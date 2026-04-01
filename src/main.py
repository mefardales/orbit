"""Orbit CLI - Python-native multi-agent orchestration framework."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bootstrap_graph import build_bootstrap_graph
from .command_graph import build_command_graph
from .commands import execute_command, get_command, get_commands, render_command_index
from .direct_modes import run_deep_link, run_direct_connect
from .parity_audit import run_config_audit
from .permissions import ToolPermissionContext
from .workspace_manifest import build_workspace_manifest
from .query_engine import QueryEnginePort
from .remote_runtime import run_remote_mode, run_ssh_mode, run_teleport_mode
from .runtime import OrbitRuntime
from .session_store import load_session, get_session_manager
from .setup import run_setup
from .tool_pool import assemble_tool_pool
from .tools import execute_tool, get_tool, get_tools, render_tool_index


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='orbit',
        description='Orbit - Python-native multi-agent orchestration framework',
    )
    parser.add_argument('--version', action='store_true', help='show version and exit')
    subparsers = parser.add_subparsers(dest='command')

    # --- Interactive mode ---
    subparsers.add_parser('chat', help='start interactive chat session')

    # --- Core workspace commands ---
    subparsers.add_parser('summary', help='render workspace summary')
    subparsers.add_parser('manifest', help='print workspace manifest')
    subparsers.add_parser('config-audit', help='run configuration audit')
    subparsers.add_parser('setup-report', help='render startup/setup report')
    subparsers.add_parser('command-graph', help='show command graph segmentation')
    subparsers.add_parser('tool-pool', help='show assembled tool pool')
    subparsers.add_parser('bootstrap-graph', help='show bootstrap/runtime graph stages')

    list_parser = subparsers.add_parser('subsystems', help='list workspace modules')
    list_parser.add_argument('--limit', type=int, default=32)

    # --- Agent system ---
    agents_parser = subparsers.add_parser('agents', help='list available agent definitions')
    agents_parser.add_argument('--category', choices=['build', 'review', 'domain', 'product', 'coordination'])
    agents_parser.add_argument('--detail', type=str, help='show details for a specific agent')

    # --- Skills ---
    skills_parser = subparsers.add_parser('skills', help='list available skills')
    skills_parser.add_argument('--category', choices=['execution', 'planning', 'shortcut', 'utility'])

    # --- Doctor ---
    doctor_parser = subparsers.add_parser('doctor', help='run environment diagnostics')
    doctor_parser.add_argument('--fix', action='store_true', help='attempt to fix issues')
    doctor_parser.add_argument('--verbose', action='store_true', help='emit extra per-check context')

    # --- Setup ---
    setup_parser = subparsers.add_parser('setup', help='run 8-step installation pipeline')
    setup_parser.add_argument('--scope', choices=['user', 'project'], default='user',
                               help='install scope: user (~/.orbit/) or project (./.orbit/)')
    setup_parser.add_argument('--dry-run', action='store_true', help='preview without writing')
    setup_parser.add_argument('--check', action='store_true', help='verify without making changes')

    # --- Cleanup ---
    cleanup_parser = subparsers.add_parser('cleanup', help='remove stale state and orphan sessions')
    cleanup_parser.add_argument('--dry-run', action='store_true', help='preview without deleting')

    # --- Ask ---
    ask_parser = subparsers.add_parser('ask', help='send a single prompt to a model')
    ask_parser.add_argument('prompt', help='the prompt to send')
    ask_parser.add_argument('--provider', '-p', default=None,
                             help='provider: claude, openai, ollama, etc.')
    ask_parser.add_argument('--role', '-r', default=None,
                             help='agent role for system prompt (e.g. architect, executor)')
    ask_parser.add_argument('--format', '-f', dest='output_format',
                             choices=['text', 'json', 'markdown'], default='text')
    ask_parser.add_argument('--model', '-m', default=None, help='model override')
    ask_parser.add_argument('--stream', action='store_true', help='stream tokens to stdout')

    # --- Explore ---
    explore_parser = subparsers.add_parser('explore', help='explore the codebase')
    explore_parser.add_argument('query', nargs='?', default='', help='search query')

    # --- Command/tool registries ---
    commands_parser = subparsers.add_parser('commands', help='list registered commands')
    commands_parser.add_argument('--limit', type=int, default=20)
    commands_parser.add_argument('--query')
    commands_parser.add_argument('--no-plugin-commands', action='store_true')
    commands_parser.add_argument('--no-skill-commands', action='store_true')

    tools_parser = subparsers.add_parser('tools', help='list registered tools')
    tools_parser.add_argument('--limit', type=int, default=20)
    tools_parser.add_argument('--query')
    tools_parser.add_argument('--simple-mode', action='store_true')
    tools_parser.add_argument('--no-mcp', action='store_true')
    tools_parser.add_argument('--deny-tool', action='append', default=[])
    tools_parser.add_argument('--deny-prefix', action='append', default=[])

    # --- Routing and sessions ---
    route_parser = subparsers.add_parser('route', help='route a prompt to matching agents/tools')
    route_parser.add_argument('prompt')
    route_parser.add_argument('--limit', type=int, default=5)

    bootstrap_parser = subparsers.add_parser('bootstrap', help='bootstrap a full session')
    bootstrap_parser.add_argument('prompt')
    bootstrap_parser.add_argument('--limit', type=int, default=5)

    loop_parser = subparsers.add_parser('turn-loop', help='run a stateful turn loop')
    loop_parser.add_argument('prompt')
    loop_parser.add_argument('--limit', type=int, default=5)
    loop_parser.add_argument('--max-turns', type=int, default=3)
    loop_parser.add_argument('--structured-output', action='store_true')

    flush_parser = subparsers.add_parser('flush-transcript', help='persist and flush transcript')
    flush_parser.add_argument('prompt')

    load_session_parser = subparsers.add_parser('load-session', help='load and resume a persisted session')
    load_session_parser.add_argument('session_id')

    sessions_parser = subparsers.add_parser('sessions', help='list recent sessions')
    sessions_parser.add_argument('--limit', type=int, default=20)
    sessions_parser.add_argument('--format', choices=['table', 'json'], default='table')

    session_search_parser = subparsers.add_parser('session-search', help='search session transcripts')
    session_search_parser.add_argument('query')
    session_search_parser.add_argument('--limit', type=int, default=20)

    # --- HUD ---
    hud_parser = subparsers.add_parser('hud', help='heads-up display for active modes')
    hud_parser.add_argument('--watch', action='store_true', help='continuous polling mode')
    hud_parser.add_argument('--json', action='store_true', help='JSON output')
    hud_parser.add_argument('--preset', choices=['minimal', 'focused', 'full'], default='focused')
    hud_parser.add_argument('--interval', type=int, default=1000, help='polling interval in ms')

    # --- Runtime modes ---
    remote_parser = subparsers.add_parser('remote-mode', help='remote-control runtime')
    remote_parser.add_argument('target')
    ssh_parser = subparsers.add_parser('ssh-mode', help='SSH runtime')
    ssh_parser.add_argument('target')
    teleport_parser = subparsers.add_parser('teleport-mode', help='teleport runtime')
    teleport_parser.add_argument('target')
    direct_parser = subparsers.add_parser('direct-connect-mode', help='direct-connect runtime')
    direct_parser.add_argument('target')
    deep_link_parser = subparsers.add_parser('deep-link-mode', help='deep-link runtime')
    deep_link_parser.add_argument('target')

    # --- Inspect/execute ---
    show_command = subparsers.add_parser('show-command', help='show a command by name')
    show_command.add_argument('name')
    show_tool = subparsers.add_parser('show-tool', help='show a tool by name')
    show_tool.add_argument('name')

    exec_command_parser = subparsers.add_parser('exec-command', help='execute a command by name')
    exec_command_parser.add_argument('name')
    exec_command_parser.add_argument('prompt')

    exec_tool_parser = subparsers.add_parser('exec-tool', help='execute a tool by name')
    exec_tool_parser.add_argument('name')
    exec_tool_parser.add_argument('payload')

    return parser


def _run_doctor(fix: bool = False) -> int:
    """Run environment diagnostics."""
    checks = [
        ('Python version', sys.version.split()[0], sys.version_info >= (3, 9)),
        ('Platform', sys.platform, True),
        ('Workspace manifest', '', None),
        ('Command registry', '', None),
        ('Tool registry', '', None),
        ('Agent definitions', '', None),
        ('Skill catalog', '', None),
    ]

    try:
        manifest = build_workspace_manifest()
        checks[2] = ('Workspace manifest', f'{manifest.total_python_files} Python files', True)
    except Exception as e:
        checks[2] = ('Workspace manifest', str(e), False)

    try:
        from .commands import REGISTERED_COMMANDS
        checks[3] = ('Command registry', f'{len(REGISTERED_COMMANDS)} commands', True)
    except Exception as e:
        checks[3] = ('Command registry', str(e), False)

    try:
        from .tools import REGISTERED_TOOLS
        checks[4] = ('Tool registry', f'{len(REGISTERED_TOOLS)} tools', True)
    except Exception as e:
        checks[4] = ('Tool registry', str(e), False)

    try:
        from .agents.definitions import AGENT_DEFINITIONS
        checks[5] = ('Agent definitions', f'{len(AGENT_DEFINITIONS)} agents', True)
    except Exception as e:
        checks[5] = ('Agent definitions', str(e), False)

    try:
        from .catalog.reader import read_catalog_manifest
        cat = read_catalog_manifest()
        checks[6] = ('Skill catalog', f'{len(cat.skills)} skills, {len(cat.agents)} agents', True)
    except Exception as e:
        checks[6] = ('Skill catalog', str(e), False)

    print('# Orbit Doctor\n')
    all_ok = True
    for name, detail, ok in checks:
        icon = 'PASS' if ok else 'FAIL'
        if not ok:
            all_ok = False
        print(f'  [{icon}] {name}: {detail}')

    print(f'\n{"All checks passed." if all_ok else "Some checks failed."}')
    return 0 if all_ok else 1


def _run_agents(category: str | None = None, detail: str | None = None) -> int:
    """List or inspect agent definitions."""
    from .agents.definitions import AGENT_DEFINITIONS, get_agent, get_agents_by_category

    if detail:
        agent = get_agent(detail)
        if not agent:
            print(f'Agent not found: {detail}')
            return 1
        print(f'Name:            {agent.name}')
        print(f'Description:     {agent.description}')
        print(f'Category:        {agent.category}')
        print(f'Posture:         {agent.posture}')
        print(f'Model class:     {agent.model_class}')
        print(f'Routing role:    {agent.routing_role}')
        print(f'Reasoning:       {agent.reasoning_effort}')
        print(f'Tools:           {agent.tools}')
        return 0

    if category:
        agents = get_agents_by_category(category)
    else:
        agents = list(AGENT_DEFINITIONS.values())

    print(f'# Orbit Agents ({len(agents)})\n')
    for agent in agents:
        print(f'  {agent.name:24s} [{agent.category:12s}] {agent.description}')
    return 0


def _run_skills(category: str | None = None) -> int:
    """List available skills from catalog."""
    try:
        from .catalog.reader import read_catalog_manifest
        manifest = read_catalog_manifest()
        skills = manifest.skills
        if category:
            skills = [s for s in skills if s.category == category]
        print(f'# Orbit Skills ({len(skills)})\n')
        for skill in skills:
            status = f'[{skill.status}]'
            core = ' (core)' if skill.core else ''
            print(f'  {skill.name:28s} {status:12s} {skill.category}{core}')
        return 0
    except Exception:
        # Fallback: list skill directories
        skills_dir = Path(__file__).resolve().parent.parent / 'skills'
        if skills_dir.exists():
            skill_names = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and (d / 'SKILL.md').exists())
            print(f'# Orbit Skills ({len(skill_names)})\n')
            for name in skill_names:
                print(f'  {name}')
            return 0
        print('No skills found.')
        return 1


def _run_explore(query: str) -> int:
    """Explore the codebase."""
    root = Path(__file__).resolve().parent
    if not query:
        print(f'# Orbit Codebase\n')
        for p in sorted(root.rglob('*.py')):
            rel = p.relative_to(root)
            print(f'  {rel}')
        return 0

    # Search for query in Python files
    needle = query.lower()
    matches = []
    for p in root.rglob('*.py'):
        try:
            content = p.read_text()
            if needle in content.lower():
                matches.append(p.relative_to(root))
        except OSError:
            continue

    print(f'# Search results for "{query}" ({len(matches)} files)\n')
    for m in matches:
        print(f'  {m}')
    return 0


def _run_sessions(limit: int = 20, fmt: str = 'table') -> int:
    """List recent sessions from the SessionManager store."""
    import time as _time
    mgr = get_session_manager()
    sessions = mgr.list_sessions(limit=limit)
    if not sessions:
        print('No sessions found.')
        return 0

    if fmt == 'json':
        import json as _json
        print(_json.dumps([
            {
                'session_id': s.session_id,
                'status': s.status,
                'messages': s.message_count,
                'provider': s.provider,
                'model': s.model,
                'updated_at': s.updated_at,
                'tags': s.tags,
            }
            for s in sessions
        ], indent=2))
        return 0

    print(f'# Recent sessions ({len(sessions)})\n')
    print(f'  {"ID":34s} {"STATUS":12s} {"MSGS":5s} {"PROVIDER":12s} {"UPDATED"}')
    print('  ' + '-' * 80)
    for s in sessions:
        updated = _time.strftime('%Y-%m-%d %H:%M', _time.localtime(s.updated_at))
        print(
            f'  {s.session_id:34s} {s.status:12s} {s.message_count:5d} '
            f'{(s.provider or "—"):12s} {updated}'
        )
    return 0


def _run_session_search(query: str, limit: int = 20) -> int:
    """Search session transcripts for a query string."""
    import time as _time
    mgr = get_session_manager()
    results = mgr.search_sessions(query, limit=limit)
    if not results:
        print(f'No sessions matched {query!r}.')
        return 0

    print(f'# Session search: {query!r} ({len(results)} results)\n')
    for s in results:
        updated = _time.strftime('%Y-%m-%d %H:%M', _time.localtime(s.updated_at))
        print(f'  {s.session_id}  [{s.status}]  msgs={s.message_count}  updated={updated}')
        if s.tags:
            print(f'    tags: {", ".join(s.tags)}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from .cli.version import print_version
        print_version()
        return 0

    if not args.command:
        # No command = launch interactive REPL
        from .repl import run_repl
        run_repl()
        return 0

    if args.command == 'chat':
        from .repl import run_repl
        run_repl()
        return 0

    # --- New Pythonic commands ---
    if args.command == 'doctor':
        from .cli.doctor import run_doctor
        return run_doctor(fix=args.fix, verbose=getattr(args, 'verbose', False))
    if args.command == 'setup':
        from .cli.setup import run_setup_wizard
        return run_setup_wizard(
            scope=args.scope,
            dry_run=args.dry_run,
            check_only=args.check,
        )
    if args.command == 'cleanup':
        from .cli.cleanup import run_cleanup
        return run_cleanup(dry_run=args.dry_run)
    if args.command == 'ask':
        from .cli.ask import run_ask
        return run_ask(
            prompt=args.prompt,
            provider=args.provider,
            role=args.role,
            output_format=args.output_format,
            model=args.model,
            stream=args.stream,
        )
    if args.command == 'hud':
        from .hud.watcher import HudWatcher
        watcher = HudWatcher(cwd='.', preset=args.preset)
        if args.json:
            watcher.print_json()
        elif args.watch:
            watcher.run_watch(interval_ms=args.interval)
        else:
            watcher.print_once()
        return 0
    if args.command == 'agents':
        return _run_agents(category=args.category, detail=args.detail)
    if args.command == 'skills':
        return _run_skills(category=args.category)
    if args.command == 'explore':
        return _run_explore(args.query)

    # --- Core workspace commands ---
    manifest = build_workspace_manifest()
    if args.command == 'summary':
        print(QueryEnginePort(manifest).render_summary())
        return 0
    if args.command == 'manifest':
        print(manifest.to_markdown())
        return 0
    if args.command == 'config-audit':
        print(run_config_audit().to_markdown())
        return 0
    if args.command == 'setup-report':
        print(run_setup().as_markdown())
        return 0
    if args.command == 'command-graph':
        print(build_command_graph().as_markdown())
        return 0
    if args.command == 'tool-pool':
        print(assemble_tool_pool().as_markdown())
        return 0
    if args.command == 'bootstrap-graph':
        print(build_bootstrap_graph().as_markdown())
        return 0
    if args.command == 'subsystems':
        for subsystem in manifest.top_level_modules[: args.limit]:
            print(f'{subsystem.name}\t{subsystem.file_count}\t{subsystem.notes}')
        return 0
    if args.command == 'commands':
        if args.query:
            print(render_command_index(limit=args.limit, query=args.query))
        else:
            commands = get_commands(include_plugin_commands=not args.no_plugin_commands, include_skill_commands=not args.no_skill_commands)
            output_lines = [f'Command entries: {len(commands)}', '']
            output_lines.extend(f'- {module.name} — {module.source_hint}' for module in commands[: args.limit])
            print('\n'.join(output_lines))
        return 0
    if args.command == 'tools':
        if args.query:
            print(render_tool_index(limit=args.limit, query=args.query))
        else:
            permission_context = ToolPermissionContext.from_iterables(args.deny_tool, args.deny_prefix)
            tools = get_tools(simple_mode=args.simple_mode, include_mcp=not args.no_mcp, permission_context=permission_context)
            output_lines = [f'Tool entries: {len(tools)}', '']
            output_lines.extend(f'- {module.name} — {module.source_hint}' for module in tools[: args.limit])
            print('\n'.join(output_lines))
        return 0
    if args.command == 'route':
        matches = OrbitRuntime().route_prompt(args.prompt, limit=args.limit)
        if not matches:
            print('No command/tool matches found.')
            return 0
        for match in matches:
            print(f'{match.kind}\t{match.name}\t{match.score}\t{match.source_hint}')
        return 0
    if args.command == 'bootstrap':
        print(OrbitRuntime().bootstrap_session(args.prompt, limit=args.limit).as_markdown())
        return 0
    if args.command == 'turn-loop':
        results = OrbitRuntime().run_turn_loop(args.prompt, limit=args.limit, max_turns=args.max_turns, structured_output=args.structured_output)
        for idx, result in enumerate(results, start=1):
            print(f'## Turn {idx}')
            print(result.output)
            print(f'stop_reason={result.stop_reason}')
        return 0
    if args.command == 'flush-transcript':
        engine = QueryEnginePort.from_workspace()
        engine.submit_message(args.prompt)
        path = engine.persist_session()
        print(path)
        print(f'flushed={engine.transcript_store.flushed}')
        return 0
    if args.command == 'load-session':
        # Try full SessionManager first (provides richer output); fall back to legacy.
        mgr = get_session_manager()
        try:
            state = mgr.resume_session(args.session_id)
            print(f'{state.session_id}')
            print(f'{state.message_count} messages  status={state.status}')
            print(f'provider={state.provider or "—"}  model={state.model or "—"}')
            return 0
        except (KeyError, FileNotFoundError):
            pass
        session = load_session(args.session_id)
        print(f'{session.session_id}\n{len(session.messages)} messages\nin={session.input_tokens} out={session.output_tokens}')
        return 0
    if args.command == 'sessions':
        return _run_sessions(limit=args.limit, fmt=args.format)
    if args.command == 'session-search':
        return _run_session_search(args.query, limit=args.limit)
    if args.command == 'remote-mode':
        print(run_remote_mode(args.target).as_text())
        return 0
    if args.command == 'ssh-mode':
        print(run_ssh_mode(args.target).as_text())
        return 0
    if args.command == 'teleport-mode':
        print(run_teleport_mode(args.target).as_text())
        return 0
    if args.command == 'direct-connect-mode':
        print(run_direct_connect(args.target).as_text())
        return 0
    if args.command == 'deep-link-mode':
        print(run_deep_link(args.target).as_text())
        return 0
    if args.command == 'show-command':
        module = get_command(args.name)
        if module is None:
            print(f'Command not found: {args.name}')
            return 1
        print('\n'.join([module.name, module.source_hint, module.responsibility]))
        return 0
    if args.command == 'show-tool':
        module = get_tool(args.name)
        if module is None:
            print(f'Tool not found: {args.name}')
            return 1
        print('\n'.join([module.name, module.source_hint, module.responsibility]))
        return 0
    if args.command == 'exec-command':
        result = execute_command(args.name, args.prompt)
        print(result.message)
        return 0 if result.handled else 1
    if args.command == 'exec-tool':
        result = execute_tool(args.name, args.payload)
        print(result.message)
        return 0 if result.handled else 1

    parser.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
