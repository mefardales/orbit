"""Orbit interactive REPL - conversational terminal interface powered by Rich."""
from __future__ import annotations

import asyncio
import getpass
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Rich setup ──────────────────────────────────────────────────────────

from .cli.rich_output import console

# ── ASCII Art (Rich markup) ─────────────────────────────────────────────

ORBIT_ART = (
    "[#ACE1AF]█▀▀█ █▀▀█ █▀▀▄ ▀█▀ ▀▀█▀▀[/]\n"
    "[#ACE1AF]█  █ █▄▄▀ █▀▀▄  █    █[/]\n"
    "[#ACE1AF]▀▀▀▀ ▀ ▀▀ ▀▀▀  ▀▀▀   ▀[/]"
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
    """Render Claude Code-style welcome screen with Orbit branding."""
    from .cli.version import get_version
    version = get_version()
    username = _get_username()
    cwd = _get_display_cwd()
    activity = _get_recent_activity()

    # ── Single column, compact ──
    logo_raw = ORBIT_ART.replace('[#ACE1AF]', '').replace('[/]', '')

    body = Text()
    body.append(logo_raw, style="#ACE1AF")
    body.append(f"\n\nWelcome back {username}!", style="bold")
    body.append(f"\n{provider} \u00b7 {model} \u00b7 ", style="dim")
    body.append(cwd, style="dim")
    body.append("\n\n")
    body.append("/help", style="#ACE1AF")
    body.append(" commands  ", style="dim")
    body.append("/setup", style="#ACE1AF")
    body.append(" config  ", style="dim")
    body.append("/doctor", style="#ACE1AF")
    body.append(" check", style="dim")
    if activity:
        body.append("\n\n")
        body.append("Recent: ", style="#ACE1AF")
        body.append(" \u00b7 ".join(a[:40] for a in activity[:3]), style="dim")

    console.print(Panel(
        body,
        title=f"[#ACE1AF]Orbit v{version}[/]",
        title_align="left",
        border_style="#ACE1AF",
        padding=(1, 2),
        expand=False,
    ))


# ── Prompt toolkit setup ────────────────────────────────────────────────

# ── Slash command definitions with descriptions (for dynamic menu) ─────
COMMAND_HELP = {
    '/help':          'Show available commands',
    '/doctor':        'Run environment diagnostics',
    '/agents':        'List all 30 agent roles',
    '/agent':         'Show agent details',
    '/skills':        'List available skills',
    '/explore':       'Search the codebase',
    '/route':         'Route prompt to agents/tools',
    '/commands':      'Search registered commands',
    '/tools':         'Search registered tools',
    '/summary':       'Show workspace summary',
    '/manifest':      'Print workspace manifest',
    '/subsystems':    'List workspace modules',
    '/bootstrap':     'Bootstrap a full session',
    '/setup':         'Configure AI provider',
    '/model':         'Show or change model',
    '/tokens':        'Show token usage',
    '/clear-history': 'Clear conversation history',
    '/status':        'Show session status',
    '/clear':         'Clear the screen',
    '/exit':          'Exit orbit',
}

QUICK_HELP_TEXT = (
    " /commands         double tap esc to clear     ctrl+c to cancel\n"
    " /help for guide   tab to autocomplete         ctrl+d to exit\n"
    " ? for this help   arrow up/down for history    /exit to quit"
)


def _create_prompt_session(repl: 'OrbitREPL'):
    """Create prompt_toolkit session with dynamic menus and instant shortcuts."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style as PTStyle

    style = PTStyle.from_dict({
        '':                      '#e0e0e0',
        'prompt':                'bold #ACE1AF',
        'placeholder':           '#586069 italic',
        # Completion menu: dark branded look
        'completion-menu':                  'bg:#161b22 #c9d1d9',
        'completion-menu.completion':       'bg:#161b22 #c9d1d9',
        'completion-menu.completion.current': 'bg:#1f6feb #ffffff bold',
        'completion-menu.meta':             'bg:#161b22 #586069',
        'completion-menu.meta.completion.current': 'bg:#1f6feb #8b949e',
        'scrollbar.background':             'bg:#21262d',
        'scrollbar.button':                 'bg:#30363d',
        # Bottom toolbar
        'bottom-toolbar':       'bg:#161b22 #586069',
    })

    class OrbitCompleter(Completer):
        """Custom completer: shows slash commands with descriptions as you type /."""
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.lstrip()
            if text.startswith('/'):
                query = text.lower()
                for cmd, desc in COMMAND_HELP.items():
                    if cmd.startswith(query):
                        yield Completion(
                            cmd, start_position=-len(text),
                            display=cmd, display_meta=desc,
                        )

    kb = KeyBindings()

    @kb.add('enter')
    def _enter_handler(event):
        """Enter on empty input does nothing; with text, submit as normal."""
        buf = event.app.current_buffer
        if buf.text.strip():
            buf.validate_and_handle()
        # Empty buffer: ignore, no new line, no submit

    @kb.add('/')
    def _slash_trigger(event):
        """Insert / and immediately open completion menu."""
        buf = event.app.current_buffer
        buf.insert_text('/')
        buf.start_completion()

    @kb.add('escape', 'escape')
    def _(event):
        """Double-tap escape to clear input."""
        buf = event.app.current_buffer
        if buf.text:
            buf.reset()

    @kb.add('c-c')
    def _(event):
        buf = event.app.current_buffer
        if buf.text:
            buf.reset()
        elif repl._streaming.active:
            repl._streaming.interrupt()
        else:
            event.app.exit(exception=KeyboardInterrupt)

    @kb.add('c-d')
    def _(event):
        event.app.exit(exception=EOFError)

    @kb.add('?')
    def _(event):
        """Instant help on ? — no enter needed."""
        buf = event.app.current_buffer
        if not buf.text:
            # Show quick help inline without submitting
            repl._pending_quick_help = True
            buf.insert_text('?')
        else:
            buf.insert_text('?')

    def _bottom_toolbar():
        model_info = ''
        provider = ''
        if repl.model_client and repl.model_client.config.is_configured:
            model_info = repl.model_client.config.model
            provider = repl.model_client.config.provider
        turns = len(repl.session_turns)

        left = '<style fg="#ACE1AF" bold="true"> orbit </style><style fg="#30363d"> | </style><style fg="#586069">? help  /commands  ctrl+c cancel</style>'

        parts = []
        if provider:
            parts.append(f'<style fg="#58a6ff">{provider}</style>')
        if model_info:
            parts.append(f'<style fg="#8b949e">{model_info}</style>')
        if turns:
            parts.append(f'<style fg="#8b949e">{turns} turns</style>')
        right = '<style fg="#30363d"> | </style>'.join(parts) if parts else ''

        return HTML(f' {left}{"":40}{right} ')

    session = PromptSession(
        completer=OrbitCompleter(),
        style=style,
        complete_while_typing=True,
        key_bindings=kb,
        bottom_toolbar=_bottom_toolbar,
        enable_history_search=True,
        multiline=False,
        complete_in_thread=True,
        placeholder=HTML('<style fg="#586069">Ask anything or type / for commands</style>'),
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
        self._pending_quick_help = False
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
        """Show user input as highlighted bar — visually distinct from response."""
        console.print(Text(f" {text} ", style="bold white on #21262d"), highlight=False)

    def _show_slash_command(self, text: str):
        """Show slash command as highlighted bar."""
        console.print(Text(f" {text} ", style="bold #ACE1AF on #21262d"), highlight=False)

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
            from .cli.doctor import run_doctor
            run_doctor()
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

    def _process_chat_sync(self, line: str) -> str:
        """Run AI chat synchronously (called from thread pool). Returns response text."""
        self.session_turns.append({'role': 'user', 'content': line, 'time': datetime.now().isoformat()})

        if not (self.model_client and self.model_client.config.is_configured):
            return ''

        self._streaming.start()
        full_response = ''

        try:
            for token in self.model_client.stream_chat(line):
                if self._streaming.should_stop:
                    break
                full_response += token
        except KeyboardInterrupt:
            pass
        except Exception as e:
            full_response = f'Error: {e}'
        finally:
            self._streaming.stop()

        if full_response:
            self.total_input_tokens += len(line.split()) * 2
            self.total_output_tokens += len(full_response.split()) * 2
            self.session_turns.append({'role': 'assistant', 'content': full_response, 'time': datetime.now().isoformat()})

        return full_response

    async def _handle_chat_async(self, line: str):
        """Process AI chat in background: run model in thread pool, render when done."""
        loop = asyncio.get_event_loop()

        # Run the blocking AI call in the thread pool
        full_response = await loop.run_in_executor(None, self._process_chat_sync, line)

        if not full_response:
            if not (self.model_client and self.model_client.config.is_configured):
                def _warn():
                    console.print('\n  [yellow]No model connected.[/] Run [#ACE1AF]/setup[/] to configure.\n')
                app = self.prompt_session.app
                await app.run_in_terminal_async(_warn)
            return

        # Temporarily suspend prompt, render Rich output cleanly, restore prompt
        def _render():
            console.print()
            console.print(Markdown(full_response))
            console.print()

        app = self.prompt_session.app
        await app.run_in_terminal_async(_render)

    # ── Main loop ───────────────────────────────────────────────────────

    async def run(self):
        """Main REPL loop with async prompt_toolkit input."""
        provider, model = self._get_provider_display()
        _render_welcome(provider, model)

        # Setup prompt_toolkit
        try:
            self.prompt_session = _create_prompt_session(self)
            use_prompt_toolkit = True
        except Exception:
            use_prompt_toolkit = False

        while self.running:
            try:
                if use_prompt_toolkit:
                    from prompt_toolkit.formatted_text import ANSI
                    line = await self.prompt_session.prompt_async(
                        ANSI('\033[1m\033[38;2;172;225;175m \u276f \033[0m'),
                    )
                    line = line.strip()
                else:
                    line = input(' \033[1m\033[38;2;172;225;175m\u276f\033[0m ').strip()

                # Empty input: do absolutely nothing
                if not line:
                    continue

                if line == '?':
                    console.print(f'\n[dim]{QUICK_HELP_TEXT}[/]\n')
                    continue

                if line.startswith('/'):
                    if not self._handle_command(line):
                        console.print(f'[yellow]Unknown command: {line.split()[0]}. Type /help for commands.[/]')
                else:
                    # Show status, then fire background task
                    console.print(f'  [dim]⏳ {line[:80]}{"…" if len(line) > 80 else ""}[/]')
                    asyncio.ensure_future(self._handle_chat_async(line))

            except KeyboardInterrupt:
                if self._streaming.active:
                    self._streaming.interrupt()
                else:
                    console.print()
            except EOFError:
                console.print()
                self.running = False

        elapsed = datetime.now() - self.session_start
        console.print(f'\n[bold green]Session ended.[/] [dim]{len(self.session_turns)} turns in {elapsed.seconds // 60}m {elapsed.seconds % 60}s[/]')


def run_repl():
    """Entry point for the interactive REPL."""
    repl = OrbitREPL()
    asyncio.run(repl.run())
