"""Orbit interactive REPL - conversational terminal interface powered by Rich."""
from __future__ import annotations

import getpass
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ── Rich setup ──────────────────────────────────────────────────────────

ORBIT_THEME = Theme({
    "orbit.green": "green",
    "orbit.cyan": "cyan",
    "orbit.dim": "dim",
    "orbit.yellow": "yellow",
    "orbit.red": "red",
    "orbit.accent": "bold cyan",
    "orbit.user": "bold white on grey23",
    "orbit.cmd": "bold yellow on grey23",
})

console = Console(theme=ORBIT_THEME)

# ── ASCII Art (Rich markup) ─────────────────────────────────────────────

ORBIT_ART = (
    "[green] ██████╗ [cyan]██████╗ [green]██████╗ [cyan]██╗[green]████████╗[/]\n"
    "[green]██╔═══██╗[cyan]██╔══██╗[green]██╔══██╗[cyan]██║[green]╚══██╔══╝[/]\n"
    "[green]██║   ██║[cyan]██████╔╝[green]██████╔╝[cyan]██║[green]   ██║[/]\n"
    "[green]██║   ██║[cyan]██╔══██╗[green]██╔══██╗[cyan]██║[green]   ██║[/]\n"
    "[green]╚██████╔╝[cyan]██║  ██║[green]██████╔╝[cyan]██║[green]   ██║[/]\n"
    "[green] ╚═════╝ [cyan]╚═╝  ╚═╝[green]╚═════╝ [cyan]╚═╝[green]   ╚═╝[/]"
)

SLASH_COMMANDS = [
    '/help', '/doctor', '/agents', '/agent', '/skills', '/explore',
    '/route', '/commands', '/tools', '/summary', '/manifest',
    '/subsystems', '/bootstrap', '/setup', '/model', '/tokens',
    '/clear-history', '/status', '/clear', '/exit', '/quit', '/q',
]


# ── Helpers ─────────────────────────────────────────────────────────────

def _get_username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return 'user'


def _get_recent_activity() -> list[str]:
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'log', '--oneline', '-3', '--no-decorate'],
            capture_output=True, text=True, timeout=3, cwd=os.getcwd(),
        )
        if result.returncode == 0 and result.stdout.strip():
            return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    except Exception:
        pass
    return []


def _get_display_cwd() -> str:
    cwd = os.getcwd()
    home = str(Path.home())
    return ('~' + cwd[len(home):]) if cwd.startswith(home) else cwd


# ── Welcome screen ──────────────────────────────────────────────────────

def _render_welcome(provider: str, model: str):
    """Render the Claude-Code style welcome screen using Rich."""
    from .cli.version import get_version
    version = get_version()
    username = _get_username()

    # Left column
    left_parts = Text()
    left_parts.append(f"Welcome back {username}!\n\n", style="bold")

    # Right column - tips
    right_parts = Text()
    right_parts.append("Tips for getting started\n", style="green")
    right_parts.append("Run ", style="dim")
    right_parts.append("/help", style="cyan")
    right_parts.append(" for available commands\n", style="dim")
    right_parts.append("Run ", style="dim")
    right_parts.append("/setup", style="cyan")
    right_parts.append(" to configure AI provider\n", style="dim")
    right_parts.append("Run ", style="dim")
    right_parts.append("/doctor", style="cyan")
    right_parts.append(" to check environment", style="dim")

    # Recent activity
    activity = _get_recent_activity()
    activity_text = Text()
    activity_text.append("\nRecent activity\n", style="green")
    if activity:
        for commit in activity[:3]:
            short = commit[:55] + ('...' if len(commit) > 55 else '')
            activity_text.append(f"{short}\n", style="dim")
    else:
        activity_text.append("No recent activity\n", style="dim")

    # Two-column layout
    info_table = Table.grid(padding=(0, 3))
    info_table.add_column(min_width=35)
    info_table.add_column(min_width=35)
    info_table.add_row(left_parts, right_parts)

    # Full content: art + info + activity
    content = Table.grid(padding=0)
    content.add_column()
    content.add_row(Text(""))
    content.add_row(Text.from_markup(ORBIT_ART))
    content.add_row(Text(""))
    content.add_row(info_table)
    content.add_row(activity_text)

    panel = Panel(
        content,
        title=f"[bold]Orbit v{version}[/]",
        title_align="left",
        border_style="dim",
        padding=(0, 1),
    )
    console.print(panel)

    # Provider info below box
    console.print(f"\n  {provider} [dim]\u00b7[/] {model} [dim]\u00b7[/] {_get_display_cwd()}")
    console.print()


# ── Prompt toolkit setup ────────────────────────────────────────────────

def _create_prompt_session(repl: OrbitREPL):
    """Create prompt_toolkit session with autocompletion and dynamic toolbar."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style as PTStyle

    style = PTStyle.from_dict({
        'bottom-toolbar': 'bg:#1a1a2e #666688',
        'bottom-toolbar.text': '#888888',
    })

    completer = WordCompleter(SLASH_COMMANDS, match_middle=False)

    # Key bindings
    kb = KeyBindings()

    @kb.add('escape')
    def _(event):
        """Escape clears current input or cancels."""
        buf = event.app.current_buffer
        if buf.text:
            buf.reset()
        else:
            # Show hint
            pass

    @kb.add('c-c')
    def _(event):
        """Ctrl+C clears input or raises interrupt for streaming."""
        buf = event.app.current_buffer
        if buf.text:
            buf.reset()
        else:
            event.app.exit(exception=KeyboardInterrupt)

    @kb.add('c-d')
    def _(event):
        """Ctrl+D exits."""
        event.app.exit(exception=EOFError)

    def _bottom_toolbar():
        model_info = ''
        if repl.model_client and repl.model_client.config.is_configured:
            model_info = repl.model_client.config.model
        left = '  ? for shortcuts'
        right = f'{model_info}  ' if model_info else ''
        # prompt_toolkit handles the gap
        return HTML(
            f'<b>{left}</b>'
            f'<style fg="#666688">{" " * 40}</style>'
            f'<style fg="#88aa88">{right}</style>'
        )

    session = PromptSession(
        completer=completer,
        style=style,
        complete_while_typing=True,
        key_bindings=kb,
        bottom_toolbar=_bottom_toolbar,
        enable_history_search=True,
    )
    return session


# ── Streaming interrupt flag ────────────────────────────────────────────

class _StreamingState:
    """Thread-safe streaming state for interrupt handling."""
    def __init__(self):
        self.active = False
        self.interrupted = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            self.active = True
            self.interrupted = False

    def interrupt(self):
        with self._lock:
            self.interrupted = True

    def stop(self):
        with self._lock:
            self.active = False
            self.interrupted = False

    @property
    def should_stop(self) -> bool:
        with self._lock:
            return self.interrupted


# ── Main REPL ───────────────────────────────────────────────────────────

class OrbitREPL:
    """Interactive REPL for Orbit with Rich rendering."""

    def __init__(self):
        self.session_turns: list[dict] = []
        self.session_start = datetime.now()
        self.running = True
        self.model_client = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.prompt_session = None
        self._streaming = _StreamingState()
        self._init_model()
        self._setup_signals()

    def _init_model(self):
        try:
            from .model_client import ModelClient, ModelConfig
            config = ModelConfig.from_env()
            if config.is_configured:
                self.model_client = ModelClient(config)
        except Exception:
            pass

    def _setup_signals(self):
        """Setup signal handlers for graceful interruption."""
        original_sigint = signal.getsignal(signal.SIGINT)

        def _handle_sigint(signum, frame):
            if self._streaming.active:
                self._streaming.interrupt()
            else:
                # Default behavior - raise KeyboardInterrupt
                if callable(original_sigint):
                    original_sigint(signum, frame)
                else:
                    raise KeyboardInterrupt

        signal.signal(signal.SIGINT, _handle_sigint)

    def _get_provider_display(self) -> tuple[str, str]:
        if self.model_client and self.model_client.config.is_configured:
            c = self.model_client.config
            return c.provider.capitalize(), c.model
        return 'Not configured', 'Run /setup'

    def _show_user_input(self, text: str):
        """Display user input as full-width highlighted bar."""
        console.print(Text(f" {text}", style="bold white"), style="on grey23", highlight=False)

    def _show_slash_command(self, text: str):
        """Display slash command as highlighted bar."""
        console.print(Text(f" {text}", style="bold yellow"), style="on grey23", highlight=False)

    # ── Command handlers ────────────────────────────────────────────────

    def _handle_command(self, line: str) -> bool:
        parts = line.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ''

        if cmd in ('/exit', '/quit', '/q'):
            self.running = False
            return True

        if cmd in ('/help', '/?'):
            help_text = Text()
            help_text.append("\nAvailable commands:\n\n", style="bold")
            cmds = [
                ("/help", "Show this help"),
                ("/doctor", "Run environment diagnostics"),
                ("/agents", "List all 30 agent roles"),
                ("/agent <name>", "Show agent details"),
                ("/skills", "List all available skills"),
                ("/explore <query>", "Search the codebase"),
                ("/route <prompt>", "Route to matching agents/tools"),
                ("/commands [query]", "Search registered commands"),
                ("/tools [query]", "Search registered tools"),
                ("/summary", "Show workspace summary"),
                ("/manifest", "Show workspace manifest"),
                ("/subsystems", "List workspace modules"),
                ("/bootstrap <prompt>", "Bootstrap a full session"),
                ("/model [name]", "Show or change model"),
                ("/setup", "Configure API key"),
                ("/tokens", "Show token usage"),
                ("/clear-history", "Clear conversation history"),
                ("/status", "Show session status"),
                ("/clear", "Clear the screen"),
                ("/exit", "Exit orbit"),
            ]
            for name, desc in cmds:
                help_text.append(f"  {name:25s}", style="cyan")
                help_text.append(f"{desc}\n")
            help_text.append("\n  Just type naturally to chat with your AI model.\n")
            console.print(help_text)
            return True

        if cmd == '/clear':
            console.clear()
            return True

        if cmd == '/doctor':
            from .main import _run_doctor
            _run_doctor()
            return True

        if cmd == '/agents':
            from .agents.definitions import AGENT_DEFINITIONS
            table = Table(title=f"Orbit Agents ({len(AGENT_DEFINITIONS)})", border_style="dim", show_lines=False, pad_edge=False)
            table.add_column("Name", style="bold", min_width=20)
            table.add_column("Category", style="dim")
            table.add_column("Description")
            cat_colors = {'build': 'green', 'review': 'cyan', 'domain': 'yellow', 'product': 'dim', 'coordination': 'red'}
            for agent in AGENT_DEFINITIONS.values():
                table.add_row(Text(agent.name, style=cat_colors.get(agent.category, '')), agent.category, agent.description)
            console.print()
            console.print(table)
            console.print()
            return True

        if cmd == '/agent':
            if not arg:
                console.print("[yellow]Usage: /agent <name>[/]")
                return True
            from .agents.definitions import get_agent
            agent = get_agent(arg.strip())
            if not agent:
                console.print(f"[red]Agent not found: {arg}[/]")
                return True
            info = Table.grid(padding=(0, 2))
            info.add_column(style="dim")
            info.add_column()
            for label, val in [("Description", agent.description), ("Category", agent.category), ("Posture", agent.posture),
                               ("Model class", agent.model_class), ("Routing role", agent.routing_role),
                               ("Reasoning", agent.reasoning_effort), ("Tools", agent.tools)]:
                info.add_row(label, val)
            console.print(Panel(info, title=f"[bold]{agent.name}[/]", border_style="dim"))
            return True

        if cmd == '/skills':
            try:
                from .catalog.reader import read_catalog_manifest
                manifest = read_catalog_manifest()
                table = Table(title=f"Orbit Skills ({len(manifest.skills)})", border_style="dim")
                table.add_column("Name", style="bold", min_width=24)
                table.add_column("Status")
                table.add_column("Category")
                for skill in manifest.skills:
                    ss = {'active': 'green', 'alias': 'dim', 'merged': 'dim', 'internal': 'yellow'}.get(skill.status, '')
                    core = " (core)" if skill.core else ""
                    table.add_row(skill.name, Text(f"[{skill.status}]", style=ss), f"{skill.category}{core}")
                console.print()
                console.print(table)
                console.print()
            except Exception:
                console.print("[red]Could not load skill catalog[/]")
            return True

        if cmd == '/explore':
            if not arg:
                console.print("[yellow]Usage: /explore <query>[/]")
                return True
            from .main import _run_explore
            _run_explore(arg.strip())
            return True

        if cmd == '/route':
            if not arg:
                console.print("[yellow]Usage: /route <prompt>[/]")
                return True
            from .runtime import OrbitRuntime
            matches = OrbitRuntime().route_prompt(arg.strip(), limit=5)
            if not matches:
                console.print("[dim]No matches found.[/]")
            else:
                table = Table(title="Routing results", border_style="dim")
                table.add_column("Type", style="bold")
                table.add_column("Name")
                table.add_column("Score")
                table.add_column("Source", style="dim")
                for m in matches:
                    table.add_row(Text(m.kind, style='green' if m.kind == 'command' else 'cyan'), m.name, str(m.score), m.source_hint)
                console.print()
                console.print(table)
                console.print()
            return True

        if cmd == '/commands':
            from .commands import REGISTERED_COMMANDS, find_commands
            if arg:
                results = find_commands(arg.strip(), limit=10)
                console.print(f'\n[bold]Commands matching "{arg.strip()}" ({len(results)}):[/]\n')
                for m in results:
                    console.print(f'  {m.name:30s} [dim]{m.source_hint}[/]')
            else:
                console.print(f'\n[bold]Registered commands: {len(REGISTERED_COMMANDS)}[/]')
                console.print('[dim]Use /commands <query> to search[/]\n')
            return True

        if cmd == '/tools':
            from .tools import REGISTERED_TOOLS, find_tools
            if arg:
                results = find_tools(arg.strip(), limit=10)
                console.print(f'\n[bold]Tools matching "{arg.strip()}" ({len(results)}):[/]\n')
                for m in results:
                    console.print(f'  {m.name:30s} [dim]{m.source_hint}[/]')
            else:
                console.print(f'\n[bold]Registered tools: {len(REGISTERED_TOOLS)}[/]')
                console.print('[dim]Use /tools <query> to search[/]\n')
            return True

        if cmd == '/summary':
            from .workspace_manifest import build_workspace_manifest
            from .query_engine import QueryEnginePort
            console.print(Markdown(QueryEnginePort(build_workspace_manifest()).render_summary()))
            return True

        if cmd == '/manifest':
            from .workspace_manifest import build_workspace_manifest
            console.print(Markdown(build_workspace_manifest().to_markdown()))
            return True

        if cmd == '/subsystems':
            from .subsystems import list_subsystems
            subs = list_subsystems()
            table = Table(title=f"Subsystems ({len(subs)})", border_style="dim")
            table.add_column("Name", style="bold")
            table.add_column("Modules", justify="right")
            for s in subs[:20]:
                table.add_row(s.name, str(s.module_count))
            console.print()
            console.print(table)
            console.print()
            return True

        if cmd == '/bootstrap':
            if not arg:
                console.print("[yellow]Usage: /bootstrap <prompt>[/]")
                return True
            from .runtime import OrbitRuntime
            console.print(Markdown(OrbitRuntime().bootstrap_session(arg.strip(), limit=5).as_markdown()))
            return True

        if cmd == '/setup':
            from .model_client import setup_interactive
            config = setup_interactive()
            from .model_client import ModelClient
            self.model_client = ModelClient(config)
            return True

        if cmd == '/model':
            if arg:
                providers = ('anthropic', 'openai', 'ollama', 'deepseek', 'grok', 'groq', 'together', 'openrouter')
                if '/' in arg or arg in providers:
                    if self.model_client:
                        p = arg.split(None, 1)
                        self.model_client.switch_provider(p[0], p[1] if len(p) > 1 else '')
                        console.print(f'[green]Switched to {p[0]}: {self.model_client.config.model}[/]')
                    else:
                        console.print('[yellow]Run /setup first[/]')
                else:
                    if self.model_client:
                        self.model_client.config.model = arg.strip()
                        self.model_client._provider = None
                        console.print(f'[green]Model set to: {arg.strip()}[/]')
                    else:
                        console.print('[yellow]Run /setup first[/]')
            else:
                if self.model_client:
                    c = self.model_client.config
                    info = Table.grid(padding=(0, 2))
                    info.add_column(style="dim")
                    info.add_column()
                    info.add_row("Provider", c.provider)
                    info.add_row("Model", c.model)
                    info.add_row("Base URL", c.base_url or "(default)")
                    info.add_row("API key", "***" + c.api_key[-4:] if c.api_key else "(not set)")
                    console.print(Panel(info, title="[bold]Current model[/]", border_style="dim"))
                else:
                    console.print('[yellow]No model configured. Run /setup[/]')
            return True

        if cmd == '/tokens':
            total = self.total_input_tokens + self.total_output_tokens
            info = Table.grid(padding=(0, 2))
            info.add_column(style="dim")
            info.add_column(justify="right")
            info.add_row("Input", f"{self.total_input_tokens:,}")
            info.add_row("Output", f"{self.total_output_tokens:,}")
            info.add_row("Total", f"{total:,}")
            if self.model_client:
                info.add_row("Turns", str(self.model_client.turn_count))
            console.print(Panel(info, title="[bold]Token Usage[/]", border_style="dim"))
            return True

        if cmd == '/clear-history':
            if self.model_client:
                self.model_client.clear_history()
            self.session_turns.clear()
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            console.print('[green]Conversation history cleared.[/]')
            return True

        if cmd == '/status':
            elapsed = datetime.now() - self.session_start
            info = Table.grid(padding=(0, 2))
            info.add_column(style="dim")
            info.add_column()
            info.add_row("Turns", str(len(self.session_turns)))
            info.add_row("Elapsed", f"{elapsed.seconds // 60}m {elapsed.seconds % 60}s")
            info.add_row("Started", self.session_start.strftime("%H:%M:%S"))
            if self.model_client:
                info.add_row("Provider", self.model_client.config.provider)
                info.add_row("Model", self.model_client.config.model)
                info.add_row("Tokens", f"{self.total_input_tokens + self.total_output_tokens:,}")
            else:
                info.add_row("Model", "[dim]not connected (run /setup)[/]")
            console.print(Panel(info, title="[bold]Session Status[/]", border_style="dim"))
            return True

        return False

    # ── Natural language / AI chat ──────────────────────────────────────

    def _handle_natural_input(self, line: str):
        """Handle natural language input with streaming + interrupt support."""
        self.session_turns.append({'role': 'user', 'content': line, 'time': datetime.now().isoformat()})
        self._show_user_input(line)

        if not (self.model_client and self.model_client.config.is_configured):
            console.print('\n[yellow]No model connected.[/] Run [cyan]/setup[/] to configure.\n')
            console.print('[dim]Meanwhile, routing your prompt...[/]')
            from .runtime import OrbitRuntime
            matches = OrbitRuntime().route_prompt(line, limit=3)
            if matches:
                for m in matches:
                    color = 'green' if m.kind == 'command' else 'cyan'
                    console.print(f'  [{color}][{m.kind}][/{color}] {m.name} -- {m.source_hint}')
            console.print()
            return

        # Start streaming with interrupt support
        self._streaming.start()

        # Show thinking spinner
        with console.status("[yellow]Thinking\u2026[/]", spinner="dots") as status:
            try:
                full_response = ''
                first_token = True

                for token in self.model_client.stream_chat(line):
                    # Check for interrupt (Ctrl+C / Escape during streaming)
                    if self._streaming.should_stop:
                        break

                    if first_token:
                        status.stop()
                        # Green bullet prefix like Claude Code
                        console.print()
                        sys.stdout.write("\033[32m\u25cf\033[0m ")
                        sys.stdout.flush()
                        first_token = False

                    sys.stdout.write(token)
                    sys.stdout.flush()
                    full_response += token

                if first_token:
                    status.stop()

                sys.stdout.write('\n')
                sys.stdout.flush()

                if self._streaming.should_stop:
                    console.print('[dim](response interrupted)[/]')

                self.total_input_tokens += len(line.split()) * 2
                self.total_output_tokens += len(full_response.split()) * 2
                self.session_turns.append({'role': 'assistant', 'content': full_response, 'time': datetime.now().isoformat()})

            except KeyboardInterrupt:
                status.stop()
                sys.stdout.write('\n')
                sys.stdout.flush()
                console.print('[dim](response interrupted)[/]')
            except Exception as e:
                status.stop()
                console.print(f'\n[red]Error: {e}[/]')
                console.print('[dim]Check /model or /setup to verify configuration.[/]')
            finally:
                self._streaming.stop()

    # ── Main loop ───────────────────────────────────────────────────────

    def run(self):
        """Main REPL loop with prompt_toolkit input."""
        provider, model = self._get_provider_display()
        _render_welcome(provider, model)

        # Separator
        console.rule(style="dim")
        console.print()

        # Setup prompt_toolkit
        try:
            self.prompt_session = _create_prompt_session(self)
            use_prompt_toolkit = True
        except Exception:
            use_prompt_toolkit = False

        while self.running:
            try:
                if use_prompt_toolkit:
                    from prompt_toolkit.formatted_text import HTML
                    line = self.prompt_session.prompt(
                        HTML('<style fg="ansibrightcyan" bold="true"> \u203a </style> '),
                    ).strip()
                else:
                    line = input(' \033[1m\033[36m\u203a\033[0m ').strip()

                if not line:
                    continue

                if line == '?':
                    self._handle_command('/help')
                    continue

                if line.startswith('/'):
                    self._show_slash_command(line)
                    if not self._handle_command(line):
                        console.print(f'[yellow]Unknown command: {line.split()[0]}. Type /help for commands.[/]')
                else:
                    self._handle_natural_input(line)

                # Separator after interaction
                console.print()
                console.rule(style="dim")

                # Status line
                model_name = ''
                if self.model_client and self.model_client.config.is_configured:
                    model_name = self.model_client.config.model
                status_right = f"[dim]{model_name}[/]" if model_name else ''
                console.print(f"  [dim]esc to interrupt[/]{'':>50}{status_right}")
                console.print()

            except KeyboardInterrupt:
                if self._streaming.active:
                    self._streaming.interrupt()
                else:
                    console.print()
            except EOFError:
                console.print()
                self.running = False

        elapsed = datetime.now() - self.session_start
        console.print(f'\n[green]Session ended. {len(self.session_turns)} turns in {elapsed.seconds // 60}m {elapsed.seconds % 60}s.[/]')


def run_repl():
    """Entry point for the interactive REPL."""
    repl = OrbitREPL()
    repl.run()
