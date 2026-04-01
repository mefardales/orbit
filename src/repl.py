"""Pyclaude interactive REPL - conversational terminal interface."""
from __future__ import annotations

import readline
import shlex
import sys
import os
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

LOGO = f"""
{GREEN}╔══════════════════════════════════════════╗
║  {BOLD}🐍 Pyclaude v0.1.0{RESET}{GREEN}                      ║
║  Python-native multi-agent orchestration  ║
╚══════════════════════════════════════════╝{RESET}
"""

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
  {CYAN}/model [name]{RESET}      Show or change model (e.g. /model claude-sonnet-4-20250514)
  {CYAN}/setup{RESET}             Configure API key
  {CYAN}/tokens{RESET}            Show token usage
  {CYAN}/clear-history{RESET}     Clear conversation history
  {CYAN}/status{RESET}            Show current session status
  {CYAN}/clear{RESET}             Clear the screen
  {CYAN}/exit{RESET}              Exit pyclaude

  Just type naturally to chat with Claude.
"""


class PyclaudeREPL:
    """Interactive REPL for Pyclaude."""

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
        histfile = Path.home() / '.pyclaude' / 'repl_history'
        histfile.parent.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(str(histfile))
        except (FileNotFoundError, OSError, PermissionError):
            pass
        readline.set_history_length(1000)
        self._histfile = histfile

        commands = [
            '/help', '/doctor', '/agents', '/agent', '/skills', '/explore',
            '/route', '/commands', '/tools', '/summary', '/manifest',
            '/subsystems', '/bootstrap', '/status', '/clear', '/exit',
        ]

        def completer(text, state):
            options = [c for c in commands if c.startswith(text)]
            return options[state] if state < len(options) else None

        readline.set_completer(completer)
        readline.parse_and_bind('tab: complete')

    def _save_history(self):
        try:
            readline.write_history_file(str(self._histfile))
        except OSError:
            pass

    def _print(self, text: str):
        print(text)

    def _handle_command(self, line: str) -> bool:
        """Handle a slash command. Returns True if handled."""
        parts = line.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ''

        if cmd == '/exit' or cmd == '/quit' or cmd == '/q':
            self.running = False
            return True

        if cmd == '/help' or cmd == '/?':
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
            self._print(f'\n{BOLD}Pyclaude Agents ({len(AGENT_DEFINITIONS)}):{RESET}\n')
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
                self._print(f'\n{BOLD}Pyclaude Skills ({len(manifest.skills)}):{RESET}\n')
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
            from .runtime import PyclaudeRuntime
            matches = PyclaudeRuntime().route_prompt(arg.strip(), limit=5)
            if not matches:
                self._print(f'{DIM}No matches found.{RESET}')
            else:
                self._print(f'\n{BOLD}Routing results:{RESET}\n')
                for m in matches:
                    kind_color = GREEN if m.kind == 'command' else CYAN
                    self._print(f'  {kind_color}[{m.kind}]{RESET} {m.name} (score: {m.score}) — {m.source_hint}')
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
            from .runtime import PyclaudeRuntime
            session = PyclaudeRuntime().bootstrap_session(arg.strip(), limit=5)
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
                # Switch model
                if '/' in arg or arg in ('anthropic', 'openai', 'ollama', 'deepseek', 'grok', 'groq', 'together', 'openrouter'):
                    # Provider switch
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
            # Stream response from the model
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

                # Update token counts (approximate from history)
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
            # No model connected - fall back to routing
            self._print(f'\n{YELLOW}No model connected.{RESET} Run {CYAN}/setup{RESET} to configure.\n')
            self._print(f'{DIM}Meanwhile, routing your prompt...{RESET}')
            from .runtime import PyclaudeRuntime
            matches = PyclaudeRuntime().route_prompt(line, limit=3)
            if matches:
                for m in matches:
                    kind_color = GREEN if m.kind == 'command' else CYAN
                    self._print(f'  {kind_color}[{m.kind}]{RESET} {m.name} — {m.source_hint}')
            self._print('')

    def run(self):
        """Main REPL loop."""
        self._print(LOGO)
        if self.model_client and self.model_client.config.is_configured:
            p = self.model_client.config
            self._print(f'  {GREEN}Connected:{RESET} {p.provider} / {p.model}')
        else:
            self._print(f'  {YELLOW}No model connected.{RESET} Run {CYAN}/setup{RESET} to configure a provider.')
        self._print(f'  {DIM}Type /help for commands, or just start chatting.{RESET}\n')

        while self.running:
            try:
                line = input(f'{CYAN}pyclaude>{RESET} ').strip()
                if not line:
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
    repl = PyclaudeREPL()
    repl.run()
