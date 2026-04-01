"""Orbit interactive REPL - conversational terminal interface."""
from __future__ import annotations

import getpass
import os
import readline
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ANSI colors
CYAN = '\033[36m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'
MAGENTA = '\033[35m'
WHITE = '\033[37m'
BG_RESET = '\033[49m'

# Box drawing characters
BOX_H = '\u2500'
BOX_V = '\u2502'
BOX_TL = '\u256d'
BOX_TR = '\u256e'
BOX_BL = '\u2570'
BOX_BR = '\u256f'
BOX_T_LEFT = '\u252c'
BOX_T_RIGHT = '\u252c'
BOX_SPLIT_L = '\u251c'
BOX_SPLIT_R = '\u2524'

SNAKE_ART = [
    f"  {GREEN}\033[33m    ___    {RESET}",
    f"  {GREEN}\033[33m   / _ \\   {RESET}",
    f"  {GREEN}\033[33m  | (_) |  {RESET}",
    f"  {GREEN}\033[33m   > _ <   {RESET}",
    f"  {GREEN}\033[33m  / / \\ \\  {RESET}",
    f"  {GREEN}\033[33m  \\_/ \\_/  {RESET}",
]

SLASH_COMMANDS = [
    '/help', '/doctor', '/agents', '/agent', '/skills', '/explore',
    '/route', '/commands', '/tools', '/summary', '/manifest',
    '/subsystems', '/bootstrap', '/setup', '/model', '/tokens',
    '/clear-history', '/status', '/clear', '/exit', '/quit', '/q',
]

HELP_TEXT = f"""
{BOLD}Available commands:{RESET}

  {CYAN}/help{RESET}              Show this help
  {CYAN}/doctor{RESET}            Run environment diagnostics
  {CYAN}/agents{RESET}            List all 30 agent roles
  {CYAN}/agent <name>{RESET}      Show agent details (e.g. /agent architect)
  {CYAN}/skills{RESET}            List all available skills
  {CYAN}/explore <query>{RESET}   Search the codebase
  {CYAN}/route <prompt>{RESET}    Route a prompt to matching agents/tools
  {CYAN}/commands [query]{RESET}  Search registered commands
  {CYAN}/tools [query]{RESET}     Search registered tools
  {CYAN}/summary{RESET}           Show workspace summary
  {CYAN}/manifest{RESET}          Show workspace manifest
  {CYAN}/subsystems{RESET}        List workspace modules
  {CYAN}/bootstrap <prompt>{RESET} Bootstrap a full session
  {CYAN}/model [name]{RESET}      Show or change model
  {CYAN}/setup{RESET}             Configure API key
  {CYAN}/tokens{RESET}            Show token usage
  {CYAN}/clear-history{RESET}     Clear conversation history
  {CYAN}/status{RESET}            Show current session status
  {CYAN}/clear{RESET}             Clear the screen
  {CYAN}/exit{RESET}              Exit orbit

  Just type naturally to chat with your AI model.
"""


def _get_terminal_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _get_username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return 'user'


def _get_recent_activity() -> list[str]:
    """Get recent git activity for the welcome screen."""
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


def _render_welcome_box(provider_info: str, model_info: str) -> str:
    """Render a Claude-Code-style welcome box."""
    from .cli.version import get_version

    term_w = min(_get_terminal_width(), 90)
    inner_w = term_w - 4  # 2 for border + 2 for padding
    if inner_w < 40:
        inner_w = 40

    username = _get_username()
    cwd = os.getcwd()
    home = str(Path.home())
    if cwd.startswith(home):
        display_cwd = '~' + cwd[len(home):]
    else:
        display_cwd = cwd

    version = get_version()

    # Split box into left panel and right panel
    left_w = inner_w // 2
    right_w = inner_w - left_w

    def pad_line(left: str, right: str, left_plain_len: int = 0, right_plain_len: int = 0) -> str:
        """Build a line with left and right columns inside box borders."""
        if left_plain_len == 0:
            left_plain_len = len(left.replace(BOLD, '').replace(RESET, '').replace(GREEN, '')
                                  .replace(CYAN, '').replace(YELLOW, '').replace(RED, '')
                                  .replace(DIM, '').replace(MAGENTA, '').replace(WHITE, ''))
        if right_plain_len == 0:
            right_plain_len = len(right.replace(BOLD, '').replace(RESET, '').replace(GREEN, '')
                                   .replace(CYAN, '').replace(YELLOW, '').replace(RED, '')
                                   .replace(DIM, '').replace(MAGENTA, '').replace(WHITE, ''))
        l_pad = left_w - left_plain_len
        r_pad = right_w - right_plain_len
        if l_pad < 0:
            l_pad = 0
        if r_pad < 0:
            r_pad = 0
        return f" {BOX_V} {left}{' ' * l_pad}{right}{' ' * r_pad}{BOX_V}"

    def full_line(text: str, plain_len: int = 0) -> str:
        if plain_len == 0:
            plain_len = len(text.replace(BOLD, '').replace(RESET, '').replace(GREEN, '')
                              .replace(CYAN, '').replace(YELLOW, '').replace(RED, '')
                              .replace(DIM, '').replace(MAGENTA, '').replace(WHITE, ''))
        total_pad = inner_w - plain_len
        if total_pad < 0:
            total_pad = 0
        return f" {BOX_V} {text}{' ' * total_pad}{BOX_V}"

    lines = []

    # Top border with title
    title = f" Orbit v{version} "
    border_left = 2
    border_right = inner_w - len(title) - border_left + 2
    if border_right < 2:
        border_right = 2
    lines.append(f" {BOX_TL}{BOX_H * border_left}{title}{BOX_H * border_right}{BOX_TR}")

    # Empty line
    lines.append(full_line(''))

    # Welcome + Tips
    welcome = f"{BOLD}Welcome back {username}!{RESET}"
    welcome_plain = f"Welcome back {username}!"
    tips_title = f"{GREEN}Tips for getting started{RESET}"
    tips_plain = "Tips for getting started"
    lines.append(pad_line(welcome, tips_title, len(welcome_plain), len(tips_plain)))

    # Logo + tips content
    tip_lines = [
        (f"Run {CYAN}/help{RESET} for available commands", f"Run /help for available commands"),
        (f"Run {CYAN}/setup{RESET} to configure AI provider", f"Run /setup to configure AI provider"),
        (f"Run {CYAN}/doctor{RESET} to check environment", f"Run /doctor to check environment"),
    ]

    art_lines = SNAKE_ART + [''] * max(0, len(tip_lines) + 2 - len(SNAKE_ART))

    # Blank line under welcome
    lines.append(pad_line('', tip_lines[0][0], 0, len(tip_lines[0][1])))

    for i, art in enumerate(art_lines[:len(tip_lines) + 1]):
        art_plain = art.replace(GREEN, '').replace(RESET, '').replace('\033[33m', '')
        if i + 1 < len(tip_lines):
            lines.append(pad_line(art, tip_lines[i + 1][0], len(art_plain), len(tip_lines[i + 1][1])))
        else:
            lines.append(pad_line(art, '', len(art_plain), 0))

    # Empty line
    lines.append(full_line(''))

    # Recent activity section
    activity = _get_recent_activity()
    activity_title = f"{GREEN}Recent activity{RESET}"
    # Provider info on the left, activity on the right
    prov_line = f"{provider_info} {DIM}\u00b7{RESET} {model_info}"
    prov_plain = f"{provider_info.replace(BOLD, '').replace(RESET, '').replace(GREEN, '').replace(CYAN, '').replace(YELLOW, '').replace(DIM, '').replace(MAGENTA, '')} \u00b7 {model_info.replace(BOLD, '').replace(RESET, '').replace(GREEN, '').replace(CYAN, '').replace(YELLOW, '').replace(DIM, '').replace(MAGENTA, '')}"
    lines.append(pad_line(prov_line, activity_title, len(prov_plain), len("Recent activity")))

    # CWD + activity lines
    cwd_line = f"{DIM}      {display_cwd}{RESET}"
    cwd_plain = f"      {display_cwd}"
    if activity:
        for i, commit in enumerate(activity[:3]):
            short = commit[:40] + ('...' if len(commit) > 40 else '')
            act = f"{DIM}{short}{RESET}"
            act_plain = short
            if i == 0:
                lines.append(pad_line(cwd_line, act, len(cwd_plain), len(act_plain)))
            else:
                lines.append(pad_line('', act, 0, len(act_plain)))
    else:
        no_act = f"{DIM}No recent activity{RESET}"
        lines.append(pad_line(cwd_line, no_act, len(cwd_plain), len("No recent activity")))

    # Empty line
    lines.append(full_line(''))

    # Bottom border
    lines.append(f" {BOX_BL}{BOX_H * (inner_w + 2)}{BOX_BR}")

    return '\n'.join(lines)


class OrbitREPL:
    """Interactive REPL for Orbit."""

    def __init__(self):
        self.session_turns: list[dict] = []
        self.session_start = datetime.now()
        self.running = True
        self.model_client = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._init_model()
        self._setup_readline()

    def _init_model(self):
        """Initialize model client if API key is available."""
        try:
            from .model_client import ModelClient, ModelConfig
            config = ModelConfig.from_env()
            if config.is_configured:
                self.model_client = ModelClient(config)
        except Exception:
            pass

    def _setup_readline(self):
        """Configure readline for history and tab completion."""
        histfile = Path.home() / '.orbit' / 'repl_history'
        histfile.parent.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(str(histfile))
        except (FileNotFoundError, OSError, PermissionError):
            pass
        readline.set_history_length(1000)
        self._histfile = histfile

        def completer(text, state):
            if text.startswith('/'):
                options = [c for c in SLASH_COMMANDS if c.startswith(text)]
            else:
                options = []
            return options[state] if state < len(options) else None

        readline.set_completer(completer)
        readline.parse_and_bind('tab: complete')
        # Show all completions on first tab
        readline.set_completer_delims(' \t\n')

    def _save_history(self):
        try:
            readline.write_history_file(str(self._histfile))
        except OSError:
            pass

    def _print(self, text: str):
        print(text)

    def _get_provider_display(self) -> tuple[str, str]:
        """Get provider and model display strings."""
        if self.model_client and self.model_client.config.is_configured:
            c = self.model_client.config
            provider = c.provider.capitalize()
            model = c.model
            return provider, model
        return 'Not configured', 'Run /setup'

    def _handle_command(self, line: str) -> bool:
        """Handle a slash command. Returns True if handled."""
        parts = line.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ''

        if cmd in ('/exit', '/quit', '/q'):
            self.running = False
            return True

        if cmd in ('/help', '/?'):
            self._print(HELP_TEXT)
            return True

        if cmd == '/clear':
            os.system('clear' if os.name != 'nt' else 'cls')
            return True

        if cmd == '/doctor':
            from .main import _run_doctor
            _run_doctor()
            return True

        if cmd == '/agents':
            from .agents.definitions import AGENT_DEFINITIONS
            self._print(f'\n{BOLD}Orbit Agents ({len(AGENT_DEFINITIONS)}):{RESET}\n')
            for agent in AGENT_DEFINITIONS.values():
                color = {'build': GREEN, 'review': CYAN, 'domain': YELLOW, 'product': DIM, 'coordination': RED}.get(agent.category, '')
                self._print(f'  {color}{agent.name:24s}{RESET} [{agent.category:12s}] {agent.description}')
            self._print('')
            return True

        if cmd == '/agent':
            if not arg:
                self._print(f'{YELLOW}Usage: /agent <name>{RESET}')
                return True
            from .agents.definitions import get_agent
            agent = get_agent(arg.strip())
            if not agent:
                self._print(f'{RED}Agent not found: {arg}{RESET}')
                return True
            self._print(f'\n{BOLD}{agent.name}{RESET}')
            self._print(f'  Description:  {agent.description}')
            self._print(f'  Category:     {agent.category}')
            self._print(f'  Posture:      {agent.posture}')
            self._print(f'  Model class:  {agent.model_class}')
            self._print(f'  Routing role: {agent.routing_role}')
            self._print(f'  Reasoning:    {agent.reasoning_effort}')
            self._print(f'  Tools:        {agent.tools}')
            self._print('')
            return True

        if cmd == '/skills':
            try:
                from .catalog.reader import read_catalog_manifest
                manifest = read_catalog_manifest()
                self._print(f'\n{BOLD}Orbit Skills ({len(manifest.skills)}):{RESET}\n')
                for skill in manifest.skills:
                    status_color = {'active': GREEN, 'alias': DIM, 'merged': DIM, 'internal': YELLOW}.get(skill.status, '')
                    core = f' {GREEN}(core){RESET}' if skill.core else ''
                    self._print(f'  {skill.name:28s} {status_color}[{skill.status}]{RESET} {skill.category}{core}')
                self._print('')
            except Exception:
                self._print(f'{RED}Could not load skill catalog{RESET}')
            return True

        if cmd == '/explore':
            if not arg:
                self._print(f'{YELLOW}Usage: /explore <query>{RESET}')
                return True
            from .main import _run_explore
            _run_explore(arg.strip())
            return True

        if cmd == '/route':
            if not arg:
                self._print(f'{YELLOW}Usage: /route <prompt>{RESET}')
                return True
            from .runtime import OrbitRuntime
            matches = OrbitRuntime().route_prompt(arg.strip(), limit=5)
            if not matches:
                self._print(f'{DIM}No matches found.{RESET}')
            else:
                self._print(f'\n{BOLD}Routing results:{RESET}\n')
                for m in matches:
                    kind_color = GREEN if m.kind == 'command' else CYAN
                    self._print(f'  {kind_color}[{m.kind}]{RESET} {m.name} (score: {m.score}) -- {m.source_hint}')
                self._print('')
            return True

        if cmd == '/commands':
            from .commands import REGISTERED_COMMANDS, find_commands
            if arg:
                results = find_commands(arg.strip(), limit=10)
                self._print(f'\n{BOLD}Commands matching "{arg.strip()}" ({len(results)}):{RESET}\n')
                for m in results:
                    self._print(f'  {m.name:30s} {DIM}{m.source_hint}{RESET}')
            else:
                self._print(f'\n{BOLD}Registered commands: {len(REGISTERED_COMMANDS)}{RESET}')
                self._print(f'{DIM}Use /commands <query> to search{RESET}\n')
            return True

        if cmd == '/tools':
            from .tools import REGISTERED_TOOLS, find_tools
            if arg:
                results = find_tools(arg.strip(), limit=10)
                self._print(f'\n{BOLD}Tools matching "{arg.strip()}" ({len(results)}):{RESET}\n')
                for m in results:
                    self._print(f'  {m.name:30s} {DIM}{m.source_hint}{RESET}')
            else:
                self._print(f'\n{BOLD}Registered tools: {len(REGISTERED_TOOLS)}{RESET}')
                self._print(f'{DIM}Use /tools <query> to search{RESET}\n')
            return True

        if cmd == '/summary':
            from .workspace_manifest import build_workspace_manifest
            from .query_engine import QueryEnginePort
            manifest = build_workspace_manifest()
            self._print(QueryEnginePort(manifest).render_summary())
            return True

        if cmd == '/manifest':
            from .workspace_manifest import build_workspace_manifest
            self._print(build_workspace_manifest().to_markdown())
            return True

        if cmd == '/subsystems':
            from .subsystems import list_subsystems
            subs = list_subsystems()
            self._print(f'\n{BOLD}Subsystems ({len(subs)}):{RESET}\n')
            for s in subs[:20]:
                self._print(f'  {s.name:20s} {s.module_count:4d} modules')
            self._print('')
            return True

        if cmd == '/bootstrap':
            if not arg:
                self._print(f'{YELLOW}Usage: /bootstrap <prompt>{RESET}')
                return True
            from .runtime import OrbitRuntime
            session = OrbitRuntime().bootstrap_session(arg.strip(), limit=5)
            self._print(session.as_markdown())
            return True

        if cmd == '/setup':
            from .model_client import setup_interactive
            config = setup_interactive()
            from .model_client import ModelClient
            self.model_client = ModelClient(config)
            return True

        if cmd == '/model':
            if arg:
                if '/' in arg or arg in ('anthropic', 'openai', 'ollama', 'deepseek', 'grok', 'groq', 'together', 'openrouter'):
                    if self.model_client:
                        parts = arg.split(None, 1)
                        provider = parts[0]
                        model = parts[1] if len(parts) > 1 else ''
                        self.model_client.switch_provider(provider, model)
                        self._print(f'{GREEN}Switched to {provider}: {self.model_client.config.model}{RESET}')
                    else:
                        self._print(f'{YELLOW}Run /setup first{RESET}')
                else:
                    if self.model_client:
                        self.model_client.config.model = arg.strip()
                        self.model_client._provider = None
                        self._print(f'{GREEN}Model set to: {arg.strip()}{RESET}')
                    else:
                        self._print(f'{YELLOW}Run /setup first{RESET}')
            else:
                if self.model_client:
                    c = self.model_client.config
                    self._print(f'\n{BOLD}Current model:{RESET}')
                    self._print(f'  Provider: {c.provider}')
                    self._print(f'  Model:    {c.model}')
                    self._print(f'  Base URL: {c.base_url or "(default)"}')
                    self._print(f'  API key:  {"***" + c.api_key[-4:] if c.api_key else "(not set)"}')
                    self._print('')
                else:
                    self._print(f'{YELLOW}No model configured. Run /setup{RESET}')
            return True

        if cmd == '/tokens':
            self._print(f'\n{BOLD}Token Usage:{RESET}')
            self._print(f'  Input:  {self.total_input_tokens:,}')
            self._print(f'  Output: {self.total_output_tokens:,}')
            self._print(f'  Total:  {self.total_input_tokens + self.total_output_tokens:,}')
            if self.model_client:
                self._print(f'  Turns:  {self.model_client.turn_count}')
            self._print('')
            return True

        if cmd == '/clear-history':
            if self.model_client:
                self.model_client.clear_history()
            self.session_turns.clear()
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self._print(f'{GREEN}Conversation history cleared.{RESET}')
            return True

        if cmd == '/status':
            elapsed = datetime.now() - self.session_start
            self._print(f'\n{BOLD}Session Status:{RESET}')
            self._print(f'  Turns:    {len(self.session_turns)}')
            self._print(f'  Elapsed:  {elapsed.seconds // 60}m {elapsed.seconds % 60}s')
            self._print(f'  Started:  {self.session_start.strftime("%H:%M:%S")}')
            if self.model_client:
                self._print(f'  Provider: {self.model_client.config.provider}')
                self._print(f'  Model:    {self.model_client.config.model}')
                self._print(f'  Tokens:   {self.total_input_tokens + self.total_output_tokens:,}')
            else:
                self._print(f'  Model:    {DIM}not connected (run /setup){RESET}')
            self._print('')
            return True

        return False

    def _handle_natural_input(self, line: str):
        """Handle natural language input - send to AI model with streaming."""
        self.session_turns.append({'role': 'user', 'content': line, 'time': datetime.now().isoformat()})

        if self.model_client and self.model_client.config.is_configured:
            try:
                sys.stdout.write(f'\n{GREEN}')
                sys.stdout.flush()
                full_response = ''
                for token in self.model_client.stream_chat(line):
                    sys.stdout.write(token)
                    sys.stdout.flush()
                    full_response += token
                sys.stdout.write(f'{RESET}\n\n')
                sys.stdout.flush()

                self.total_input_tokens += len(line.split()) * 2
                self.total_output_tokens += len(full_response.split()) * 2
                self.session_turns.append({'role': 'assistant', 'content': full_response, 'time': datetime.now().isoformat()})

            except KeyboardInterrupt:
                sys.stdout.write(f'{RESET}\n{DIM}(response interrupted){RESET}\n\n')
                sys.stdout.flush()
            except Exception as e:
                self._print(f'\n{RED}Error: {e}{RESET}')
                self._print(f'{DIM}Check /model or /setup to verify configuration.{RESET}\n')
        else:
            self._print(f'\n{YELLOW}No model connected.{RESET} Run {CYAN}/setup{RESET} to configure.\n')
            self._print(f'{DIM}Meanwhile, routing your prompt...{RESET}')
            from .runtime import OrbitRuntime
            matches = OrbitRuntime().route_prompt(line, limit=3)
            if matches:
                for m in matches:
                    kind_color = GREEN if m.kind == 'command' else CYAN
                    self._print(f'  {kind_color}[{m.kind}]{RESET} {m.name} -- {m.source_hint}')
            self._print('')

    def run(self):
        """Main REPL loop."""
        provider, model = self._get_provider_display()
        welcome = _render_welcome_box(provider, model)
        self._print(welcome)
        self._print('')

        # Shortcuts hint at the bottom
        self._print(f' {DIM}? for shortcuts{RESET}')
        self._print('')

        while self.running:
            try:
                line = input(f' {BOLD}{CYAN}>{RESET} ').strip()
                if not line:
                    continue

                if line == '?':
                    self._print(HELP_TEXT)
                    continue

                if line.startswith('/'):
                    if not self._handle_command(line):
                        self._print(f'{YELLOW}Unknown command: {line.split()[0]}. Type /help for available commands.{RESET}')
                else:
                    self._handle_natural_input(line)

            except KeyboardInterrupt:
                self._print(f'\n{DIM}(Use /exit to quit){RESET}')
            except EOFError:
                self._print('')
                self.running = False

        self._save_history()
        elapsed = datetime.now() - self.session_start
        self._print(f'\n{GREEN}Session ended. {len(self.session_turns)} turns in {elapsed.seconds // 60}m {elapsed.seconds % 60}s.{RESET}')


def run_repl():
    """Entry point for the interactive REPL."""
    repl = OrbitREPL()
    repl.run()
