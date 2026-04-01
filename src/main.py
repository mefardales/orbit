"""Orbit CLI - Python-native multi-agent orchestration framework.

Built with Typer + Rich for a polished developer experience.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.markdown import Markdown

from .cli.rich_output import console

# ── Typer app ──────────────────────────────────────────────────────────────

app = typer.Typer(
    name="orbit",
    help="Orbit - Python-native multi-agent orchestration framework",
    no_args_is_help=False,
    rich_markup_mode="rich",
    add_completion=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)


# ── Enums for choices ──────────────────────────────────────────────────────

class CategoryChoice(str, Enum):
    build = "build"
    review = "review"
    domain = "domain"
    product = "product"
    coordination = "coordination"

class SkillCategoryChoice(str, Enum):
    execution = "execution"
    planning = "planning"
    shortcut = "shortcut"
    utility = "utility"

class ScopeChoice(str, Enum):
    user = "user"
    project = "project"

class UninstallScope(str, Enum):
    project = "project"
    user = "user"
    all = "all"

class OutputFormat(str, Enum):
    text = "text"
    json = "json"
    markdown = "markdown"

class SessionFormat(str, Enum):
    table = "table"
    json = "json"

class HudPreset(str, Enum):
    minimal = "minimal"
    focused = "focused"
    full = "full"


# ── Global flags via callback ──────────────────────────────────────────────

def _version_callback(value: bool):
    if value:
        from .cli.version import get_version
        console.print(f"[bold]orbit[/] [dim]{get_version()}[/]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit.", callback=_version_callback, is_eager=True),
    madmax: bool = typer.Option(False, "--madmax", help="Maximum autonomy mode."),
    high: bool = typer.Option(False, "--high", help="High reasoning effort."),
    xhigh: bool = typer.Option(False, "--xhigh", help="Extra-high reasoning effort."),
    spark: bool = typer.Option(False, "--spark", help="Use spark (fast) model tier."),
    madmax_spark: bool = typer.Option(False, "--madmax-spark", help="Madmax + spark mode."),
    model: Optional[str] = typer.Option(None, "--model", help="Explicit model override."),
    config: Optional[str] = typer.Option(None, "-c", "--config", help="Path to configuration file."),
):
    """[bold green]Orbit[/] - Python-native multi-agent orchestration framework."""
    # Apply global flags
    from .config.runtime_context import RuntimeContext
    ctx_rt = RuntimeContext.get()
    if madmax or madmax_spark:
        ctx_rt.autonomy = 'madmax'
    if xhigh:
        ctx_rt.reasoning_effort = 'xhigh'
    elif high:
        ctx_rt.reasoning_effort = 'high'
    if madmax_spark or spark:
        ctx_rt.model_tier = 'spark'
    if model:
        ctx_rt.model_override = model
    if config:
        ctx_rt.config_path = config

    # Update/star checks
    from .cli.update_check import maybe_check_and_prompt_update
    from .cli.github_star import maybe_prompt_github_star
    maybe_check_and_prompt_update()
    maybe_prompt_github_star()

    # No subcommand = REPL
    if ctx.invoked_subcommand is None:
        from .repl import run_repl
        run_repl()


# ═══════════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════════

@app.command()
def chat():
    """Start interactive chat session."""
    from .repl import run_repl
    run_repl()


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Attempt to fix issues."),
    verbose: bool = typer.Option(False, "--verbose", help="Extra per-check context."),
):
    """Run environment diagnostics."""
    from .cli.doctor import run_doctor
    raise typer.Exit(run_doctor(fix=fix, verbose=verbose))


@app.command()
def setup(
    scope: ScopeChoice = typer.Option(ScopeChoice.user, help="Install scope."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
    check: bool = typer.Option(False, "--check", help="Verify without changes."),
):
    """Run installation pipeline."""
    from .cli.setup import run_setup_wizard
    raise typer.Exit(run_setup_wizard(scope=scope.value, dry_run=dry_run, check_only=check))


@app.command()
def cleanup(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without deleting."),
):
    """Remove stale state and orphan sessions."""
    from .cli.cleanup import run_cleanup
    raise typer.Exit(run_cleanup(dry_run=dry_run))


@app.command()
def uninstall(
    scope: UninstallScope = typer.Option(UninstallScope.project, help="What to remove."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without deleting."),
):
    """Remove Orbit from project or user scope."""
    from .cli.uninstall import run_uninstall
    raise typer.Exit(run_uninstall(scope=scope.value, dry_run=dry_run))


@app.command()
def star(
    dismiss: bool = typer.Option(False, "--dismiss", help="Permanently dismiss star prompt."),
):
    """Manage GitHub star prompt."""
    from .cli.github_star import _load_state, _save_state
    if dismiss:
        state = _load_state()
        state['dismissed'] = True
        _save_state(state)
        console.print('[green]Star prompt dismissed. Thank you for using Orbit![/]')
    else:
        console.print('[bold]Give us a star:[/] [link=https://github.com/mefardales/orbit]https://github.com/mefardales/orbit[/]')


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="The prompt to send."),
    provider: Optional[str] = typer.Option(None, "-p", "--provider", help="Provider: claude, openai, ollama, etc."),
    role: Optional[str] = typer.Option(None, "-r", "--role", help="Agent role for system prompt."),
    output_format: OutputFormat = typer.Option(OutputFormat.text, "-f", "--format", help="Output format."),
    model: Optional[str] = typer.Option(None, "-m", "--model", help="Model override."),
    stream: bool = typer.Option(False, "--stream", help="Stream tokens."),
):
    """Send a single prompt to a model."""
    from .cli.ask import run_ask
    raise typer.Exit(run_ask(
        prompt=prompt, provider=provider, role=role,
        output_format=output_format.value, model=model, stream=stream,
    ))


@app.command()
def agents(
    category: Optional[CategoryChoice] = typer.Option(None, help="Filter by category."),
    detail: Optional[str] = typer.Option(None, "--detail", help="Show details for a specific agent."),
):
    """List available agent definitions."""
    raise typer.Exit(_run_agents(category=category.value if category else None, detail=detail))


@app.command()
def skills(
    category: Optional[SkillCategoryChoice] = typer.Option(None, help="Filter by category."),
):
    """List available skills."""
    raise typer.Exit(_run_skills(category=category.value if category else None))


@app.command()
def explore(
    query: str = typer.Argument("", help="Search query."),
):
    """Explore the codebase."""
    raise typer.Exit(_run_explore(query))


@app.command()
def hud(
    watch: bool = typer.Option(False, "--watch", help="Continuous polling mode."),
    json_out: bool = typer.Option(False, "--json", help="JSON output."),
    preset: HudPreset = typer.Option(HudPreset.focused, help="Display preset."),
    interval: int = typer.Option(1000, help="Polling interval in ms."),
):
    """Heads-up display for active modes."""
    from .hud.watcher import HudWatcher
    watcher = HudWatcher(cwd='.', preset=preset.value)
    if json_out:
        watcher.print_json()
    elif watch:
        watcher.run_watch(interval_ms=interval)
    else:
        watcher.print_once()


@app.command()
def summary():
    """Render workspace summary."""
    from .workspace_manifest import build_workspace_manifest
    from .query_engine import QueryEnginePort
    console.print(Markdown(QueryEnginePort(build_workspace_manifest()).render_summary()))


@app.command()
def manifest():
    """Print workspace manifest."""
    from .workspace_manifest import build_workspace_manifest
    console.print(Markdown(build_workspace_manifest().to_markdown()))


@app.command(name="config-audit")
def config_audit():
    """Run configuration audit."""
    from .parity_audit import run_config_audit
    console.print(Markdown(run_config_audit().to_markdown()))


@app.command(name="setup-report")
def setup_report():
    """Render startup/setup report."""
    from .setup import run_setup
    console.print(Markdown(run_setup().as_markdown()))


@app.command(name="command-graph")
def command_graph():
    """Show command graph segmentation."""
    from .command_graph import build_command_graph
    console.print(Markdown(build_command_graph().as_markdown()))


@app.command(name="tool-pool")
def tool_pool():
    """Show assembled tool pool."""
    from .tool_pool import assemble_tool_pool
    console.print(Markdown(assemble_tool_pool().as_markdown()))


@app.command(name="bootstrap-graph")
def bootstrap_graph():
    """Show bootstrap/runtime graph stages."""
    from .bootstrap_graph import build_bootstrap_graph
    console.print(Markdown(build_bootstrap_graph().as_markdown()))


@app.command()
def subsystems(
    limit: int = typer.Option(32, help="Max modules to show."),
):
    """List workspace modules."""
    from rich.table import Table
    from .workspace_manifest import build_workspace_manifest
    m = build_workspace_manifest()
    table = Table(title=f"Subsystems ({len(m.top_level_modules)})", border_style="dim", pad_edge=False)
    table.add_column("Module", style="bold")
    table.add_column("Files", justify="right", style="cyan")
    table.add_column("Notes", style="dim")
    for sub in m.top_level_modules[:limit]:
        table.add_row(sub.name, str(sub.file_count), sub.notes)
    console.print()
    console.print(table)
    console.print()


@app.command()
def commands(
    limit: int = typer.Option(20, help="Max results."),
    query: Optional[str] = typer.Option(None, help="Search query."),
    no_plugin: bool = typer.Option(False, "--no-plugin-commands", help="Exclude plugin commands."),
    no_skill: bool = typer.Option(False, "--no-skill-commands", help="Exclude skill commands."),
):
    """List registered commands."""
    from .commands import get_commands, find_commands, REGISTERED_COMMANDS
    from rich.table import Table
    if query:
        results = find_commands(query, limit=limit)
        table = Table(title=f'Commands: "{query}" ({len(results)} matches)', border_style="dim", pad_edge=False)
    else:
        results = list(get_commands(include_plugin_commands=not no_plugin, include_skill_commands=not no_skill))[:limit]
        table = Table(title=f"Commands ({len(REGISTERED_COMMANDS)} total)", border_style="dim", pad_edge=False)
    table.add_column("Command", style="bold cyan")
    table.add_column("Source", style="dim")
    for m in results:
        table.add_row(m.name, m.source_hint)
    console.print()
    console.print(table)
    console.print()


@app.command()
def tools(
    limit: int = typer.Option(20, help="Max results."),
    query: Optional[str] = typer.Option(None, help="Search query."),
    simple_mode: bool = typer.Option(False, "--simple-mode"),
    no_mcp: bool = typer.Option(False, "--no-mcp"),
    deny_tool: Optional[list[str]] = typer.Option(None, "--deny-tool"),
    deny_prefix: Optional[list[str]] = typer.Option(None, "--deny-prefix"),
):
    """List registered tools."""
    from .tools import get_tools, find_tools, REGISTERED_TOOLS
    from .permissions import ToolPermissionContext
    from rich.table import Table
    if query:
        results = find_tools(query, limit=limit)
        table = Table(title=f'Tools: "{query}" ({len(results)} matches)', border_style="dim", pad_edge=False)
    else:
        pc = ToolPermissionContext.from_iterables(deny_tool or [], deny_prefix or [])
        results = list(get_tools(simple_mode=simple_mode, include_mcp=not no_mcp, permission_context=pc))[:limit]
        table = Table(title=f"Tools ({len(REGISTERED_TOOLS)} total)", border_style="dim", pad_edge=False)
    table.add_column("Tool", style="bold cyan")
    table.add_column("Source", style="dim")
    for m in results:
        table.add_row(m.name, m.source_hint)
    console.print()
    console.print(table)
    console.print()


@app.command()
def route(
    prompt: str = typer.Argument(..., help="Prompt to route."),
    limit: int = typer.Option(5, help="Max matches."),
):
    """Route a prompt to matching agents/tools."""
    from .runtime import OrbitRuntime
    from rich.table import Table
    matches = OrbitRuntime().route_prompt(prompt, limit=limit)
    if not matches:
        console.print('[dim]No matches found.[/]')
        raise typer.Exit()
    table = Table(title="Routing Results", border_style="dim", pad_edge=False)
    table.add_column("Type", style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Source", style="dim")
    for m in matches:
        color = "green" if m.kind == "command" else "cyan"
        table.add_row(f"[{color}]{m.kind}[/]", m.name, str(m.score), m.source_hint)
    console.print()
    console.print(table)
    console.print()


@app.command()
def bootstrap(
    prompt: str = typer.Argument(..., help="Session prompt."),
    limit: int = typer.Option(5, help="Max matches."),
):
    """Bootstrap a full session."""
    from .runtime import OrbitRuntime
    console.print(Markdown(OrbitRuntime().bootstrap_session(prompt, limit=limit).as_markdown()))


@app.command(name="turn-loop")
def turn_loop(
    prompt: str = typer.Argument(...),
    limit: int = typer.Option(5),
    max_turns: int = typer.Option(3, "--max-turns"),
    structured_output: bool = typer.Option(False, "--structured-output"),
):
    """Run a stateful turn loop."""
    from .runtime import OrbitRuntime
    results = OrbitRuntime().run_turn_loop(prompt, limit=limit, max_turns=max_turns, structured_output=structured_output)
    for idx, result in enumerate(results, start=1):
        console.print(f'\n[bold]Turn {idx}[/]')
        console.print(Markdown(result.output))
        console.print(f'[dim]stop_reason={result.stop_reason}[/]')


@app.command(name="flush-transcript")
def flush_transcript(prompt: str = typer.Argument(...)):
    """Persist and flush transcript."""
    from .query_engine import QueryEnginePort
    engine = QueryEnginePort.from_workspace()
    engine.submit_message(prompt)
    path = engine.persist_session()
    console.print(f'[cyan]{path}[/]')
    console.print(f'[dim]flushed={engine.transcript_store.flushed}[/]')


@app.command(name="load-session")
def load_session_cmd(session_id: str = typer.Argument(...)):
    """Load and resume a persisted session."""
    from .session_store import load_session, get_session_manager
    from rich.panel import Panel
    from rich.table import Table
    mgr = get_session_manager()
    try:
        state = mgr.resume_session(session_id)
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim")
        grid.add_column()
        grid.add_row("Session", state.session_id)
        grid.add_row("Messages", str(state.message_count))
        grid.add_row("Status", state.status)
        grid.add_row("Provider", state.provider or "\u2014")
        grid.add_row("Model", state.model or "\u2014")
        console.print(Panel(grid, title="[bold]Session Loaded[/]", border_style="cyan"))
        raise typer.Exit()
    except (KeyError, FileNotFoundError):
        pass
    session = load_session(session_id)
    console.print(f'[cyan]{session.session_id}[/]  [dim]{len(session.messages)} messages  in={session.input_tokens} out={session.output_tokens}[/]')


@app.command()
def sessions(
    limit: int = typer.Option(20, help="Max sessions."),
    fmt: SessionFormat = typer.Option(SessionFormat.table, "--format", help="Output format."),
):
    """List recent sessions."""
    raise typer.Exit(_run_sessions(limit=limit, fmt=fmt.value))


@app.command(name="session-search")
def session_search(
    query: str = typer.Argument(..., help="Search query."),
    limit: int = typer.Option(20),
):
    """Search session transcripts."""
    raise typer.Exit(_run_session_search(query, limit=limit))


# ── Runtime modes ──────────────────────────────────────────────────────────

@app.command(name="remote-mode")
def remote_mode(target: str = typer.Argument(...)):
    """Remote-control runtime."""
    from .remote_runtime import run_remote_mode
    console.print(Markdown(run_remote_mode(target).as_text()))

@app.command(name="ssh-mode")
def ssh_mode(target: str = typer.Argument(...)):
    """SSH runtime."""
    from .remote_runtime import run_ssh_mode
    console.print(Markdown(run_ssh_mode(target).as_text()))

@app.command(name="teleport-mode")
def teleport_mode(target: str = typer.Argument(...)):
    """Teleport runtime."""
    from .remote_runtime import run_teleport_mode
    console.print(Markdown(run_teleport_mode(target).as_text()))

@app.command(name="direct-connect-mode")
def direct_connect_mode(target: str = typer.Argument(...)):
    """Direct-connect runtime."""
    from .direct_modes import run_direct_connect
    console.print(Markdown(run_direct_connect(target).as_text()))

@app.command(name="deep-link-mode")
def deep_link_mode(target: str = typer.Argument(...)):
    """Deep-link runtime."""
    from .direct_modes import run_deep_link
    console.print(Markdown(run_deep_link(target).as_text()))


# ── Inspect/execute ────────────────────────────────────────────────────────

@app.command(name="show-command")
def show_command(name: str = typer.Argument(...)):
    """Show a command by name."""
    from .commands import get_command
    from rich.panel import Panel
    from rich.table import Table
    module = get_command(name)
    if module is None:
        console.print(f'[red]Command not found: {name}[/]')
        raise typer.Exit(1)
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim")
    grid.add_column()
    grid.add_row("Name", f"[bold]{module.name}[/]")
    grid.add_row("Source", module.source_hint)
    grid.add_row("Responsibility", module.responsibility)
    console.print(Panel(grid, border_style="cyan"))

@app.command(name="show-tool")
def show_tool(name: str = typer.Argument(...)):
    """Show a tool by name."""
    from .tools import get_tool
    from rich.panel import Panel
    from rich.table import Table
    module = get_tool(name)
    if module is None:
        console.print(f'[red]Tool not found: {name}[/]')
        raise typer.Exit(1)
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim")
    grid.add_column()
    grid.add_row("Name", f"[bold]{module.name}[/]")
    grid.add_row("Source", module.source_hint)
    grid.add_row("Responsibility", module.responsibility)
    console.print(Panel(grid, border_style="cyan"))

@app.command(name="exec-command")
def exec_command(name: str = typer.Argument(...), prompt: str = typer.Argument(...)):
    """Execute a command by name."""
    from .commands import execute_command
    result = execute_command(name, prompt)
    if result.handled:
        console.print(f'[green]\u2714[/] {result.message}')
    else:
        console.print(f'[red]\u2718[/] {result.message}')
        raise typer.Exit(1)

@app.command(name="exec-tool")
def exec_tool(name: str = typer.Argument(...), payload: str = typer.Argument(...)):
    """Execute a tool by name."""
    from .tools import execute_tool
    result = execute_tool(name, payload)
    if result.handled:
        console.print(f'[green]\u2714[/] {result.message}')
    else:
        console.print(f'[red]\u2718[/] {result.message}')
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# Internal rich-output helpers (used by commands above)
# ═══════════════════════════════════════════════════════════════════════════

def _run_agents(category: str | None = None, detail: str | None = None) -> int:
    from rich.panel import Panel
    from rich.table import Table
    from .agents.definitions import AGENT_DEFINITIONS, get_agent, get_agents_by_category

    cat_styles = {
        'build': 'category.build', 'review': 'category.review',
        'domain': 'category.domain', 'product': 'category.product',
        'coordination': 'category.coordination',
    }

    if detail:
        agent = get_agent(detail)
        if not agent:
            console.print(f"[red]Agent not found: {detail}[/]")
            return 1
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", min_width=16)
        grid.add_column()
        grid.add_row("Description", agent.description)
        grid.add_row("Category", f"[{cat_styles.get(agent.category, '')}]{agent.category}[/]")
        grid.add_row("Posture", agent.posture)
        grid.add_row("Model class", agent.model_class)
        grid.add_row("Routing role", agent.routing_role)
        grid.add_row("Reasoning", agent.reasoning_effort)
        grid.add_row("Tools", agent.tools)
        console.print()
        console.print(Panel(grid, title=f"[bold]{agent.name}[/]", border_style="cyan", padding=(1, 2)))
        console.print()
        return 0

    agents_list = get_agents_by_category(category) if category else list(AGENT_DEFINITIONS.values())
    table = Table(title=f"Orbit Agents ({len(agents_list)})", show_header=True, header_style="bold", border_style="dim", pad_edge=False)
    table.add_column("Agent", style="bold", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Description", ratio=1)
    for a in agents_list:
        style = cat_styles.get(a.category, '')
        table.add_row(a.name, f"[{style}]{a.category}[/]", a.description)
    console.print()
    console.print(table)
    console.print()
    return 0


def _run_skills(category: str | None = None) -> int:
    from rich.table import Table
    try:
        from .catalog.reader import read_catalog_manifest
        m = read_catalog_manifest()
        skill_list = m.skills
        if category:
            skill_list = [s for s in skill_list if s.category == category]
        table = Table(title=f"Orbit Skills ({len(skill_list)})", show_header=True, header_style="bold", border_style="dim", pad_edge=False)
        table.add_column("Skill", style="bold", min_width=24)
        table.add_column("Status", min_width=10)
        table.add_column("Category")
        table.add_column("Core", justify="center")
        status_styles = {'active': 'green', 'alias': 'dim', 'merged': 'dim italic', 'internal': 'yellow'}
        for s in skill_list:
            table.add_row(s.name, f"[{status_styles.get(s.status, '')}]{s.status}[/]", str(s.category), "[green]\u2714[/]" if s.core else "")
        console.print()
        console.print(table)
        console.print()
        return 0
    except Exception:
        console.print('[red]Could not load skill catalog.[/]')
        return 1


def _run_explore(query: str) -> int:
    from rich.table import Table
    from rich.tree import Tree
    root = Path(__file__).resolve().parent
    if not query:
        tree = Tree("[bold]Orbit Codebase[/]", guide_style="dim")
        dirs: dict = {}
        for p in sorted(root.rglob('*.py')):
            rel = p.relative_to(root)
            parts = rel.parts
            if len(parts) == 1:
                tree.add(f"[cyan]{parts[0]}[/]")
            else:
                if parts[0] not in dirs:
                    dirs[parts[0]] = tree.add(f"[bold yellow]{parts[0]}/[/]")
                dirs[parts[0]].add(f"[dim]{'/'.join(parts[1:])}[/]")
        console.print()
        console.print(tree)
        console.print()
        return 0
    needle = query.lower()
    matches = []
    for p in root.rglob('*.py'):
        try:
            if needle in p.read_text(encoding='utf-8', errors='ignore').lower():
                matches.append(p.relative_to(root))
        except OSError:
            continue
    table = Table(title=f'Search: "{query}" ({len(matches)} files)', border_style="dim", pad_edge=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("File", style="cyan")
    table.add_column("Directory", style="dim")
    for i, m in enumerate(matches, 1):
        table.add_row(str(i), m.parts[-1], str(m.parent) if len(m.parts) > 1 else ".")
    console.print()
    console.print(table)
    console.print()
    return 0


def _run_sessions(limit: int = 20, fmt: str = 'table') -> int:
    import time as _time
    from .session_store import get_session_manager
    mgr = get_session_manager()
    ses = mgr.list_sessions(limit=limit)
    if not ses:
        console.print('[dim]No sessions found.[/]')
        return 0
    if fmt == 'json':
        import json
        from rich.syntax import Syntax
        data = json.dumps([{'session_id': s.session_id, 'status': s.status, 'messages': s.message_count, 'provider': s.provider, 'model': s.model, 'updated_at': s.updated_at, 'tags': s.tags} for s in ses], indent=2)
        console.print(Syntax(data, "json", theme="monokai"))
        return 0
    from rich.table import Table
    table = Table(title=f"Recent Sessions ({len(ses)})", border_style="dim", pad_edge=False)
    table.add_column("Session ID", style="cyan")
    table.add_column("Status")
    table.add_column("Msgs", justify="right")
    table.add_column("Provider")
    table.add_column("Updated", style="dim")
    for s in ses:
        updated = _time.strftime('%Y-%m-%d %H:%M', _time.localtime(s.updated_at))
        table.add_row(s.session_id[:30], s.status, str(s.message_count), s.provider or "\u2014", updated)
    console.print()
    console.print(table)
    console.print()
    return 0


def _run_session_search(query: str, limit: int = 20) -> int:
    import time as _time
    from .session_store import get_session_manager
    from rich.table import Table
    mgr = get_session_manager()
    results = mgr.search_sessions(query, limit=limit)
    if not results:
        console.print(f'[dim]No sessions matched[/] [bold]{query!r}[/]')
        return 0
    table = Table(title=f'Session Search: {query!r} ({len(results)} results)', border_style="dim", pad_edge=False)
    table.add_column("Session ID", style="cyan")
    table.add_column("Status")
    table.add_column("Msgs", justify="right")
    table.add_column("Updated", style="dim")
    table.add_column("Tags", style="dim")
    for s in results:
        updated = _time.strftime('%Y-%m-%d %H:%M', _time.localtime(s.updated_at))
        table.add_row(s.session_id[:30], s.status, str(s.message_count), updated, ", ".join(s.tags) if s.tags else "")
    console.print()
    console.print(table)
    console.print()
    return 0


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app()
