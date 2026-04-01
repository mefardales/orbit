"""Pyclaude multi-provider model client.

Supports: Anthropic (Claude), OpenAI (GPT), Ollama (local), DeepSeek, Grok (xAI),
and any OpenAI-compatible API endpoint.

Configuration via environment variables or ~/.pyclaude/config.json
"""
from __future__ import annotations

import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterator

# ANSI
BOLD = '\033[1m'
DIM = '\033[2m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'
CYAN = '\033[36m'
RESET = '\033[0m'

# Provider presets: (provider_name, default_model, env_var_for_key, base_url)
PROVIDER_PRESETS = {
    'anthropic': {
        'default_model': 'claude-sonnet-4-20250514',
        'env_key': 'ANTHROPIC_API_KEY',
        'base_url': 'https://api.anthropic.com',
    },
    'openai': {
        'default_model': 'gpt-4o',
        'env_key': 'OPENAI_API_KEY',
        'base_url': 'https://api.openai.com/v1',
    },
    'ollama': {
        'default_model': 'llama3.2',
        'env_key': '',  # No key needed
        'base_url': 'http://localhost:11434',
    },
    'deepseek': {
        'default_model': 'deepseek-chat',
        'env_key': 'DEEPSEEK_API_KEY',
        'base_url': 'https://api.deepseek.com/v1',
    },
    'grok': {
        'default_model': 'grok-3',
        'env_key': 'XAI_API_KEY',
        'base_url': 'https://api.x.ai/v1',
    },
    'groq': {
        'default_model': 'llama-3.3-70b-versatile',
        'env_key': 'GROQ_API_KEY',
        'base_url': 'https://api.groq.com/openai/v1',
    },
    'together': {
        'default_model': 'meta-llama/Llama-3-70b-chat-hf',
        'env_key': 'TOGETHER_API_KEY',
        'base_url': 'https://api.together.xyz/v1',
    },
    'openrouter': {
        'default_model': 'anthropic/claude-sonnet-4-20250514',
        'env_key': 'OPENROUTER_API_KEY',
        'base_url': 'https://openrouter.ai/api/v1',
    },
}


@dataclass
class ModelConfig:
    provider: str = 'anthropic'
    model: str = ''
    api_key: str = ''
    base_url: str = ''
    max_tokens: int = 4096
    temperature: float = 0.7
    system_prompt: str = ''

    @classmethod
    def from_env(cls) -> 'ModelConfig':
        """Load config from env vars + config file."""
        config = cls()

        # Load from config file first
        config_file = Path.home() / '.pyclaude' / 'config.json'
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text())
                config.provider = data.get('provider', config.provider)
                config.model = data.get('model', '')
                config.api_key = data.get('api_key', '')
                config.base_url = data.get('base_url', '')
            except (json.JSONDecodeError, OSError):
                pass

        # Env overrides
        config.provider = os.environ.get('PYCLAUDE_PROVIDER', config.provider)
        config.model = os.environ.get('PYCLAUDE_MODEL', config.model)
        config.base_url = os.environ.get('PYCLAUDE_BASE_URL', config.base_url)

        # Resolve provider preset
        preset = PROVIDER_PRESETS.get(config.provider, {})
        if not config.model:
            config.model = preset.get('default_model', 'gpt-4o')
        if not config.base_url:
            config.base_url = preset.get('base_url', '')

        # API key: env var takes priority
        env_key = preset.get('env_key', '')
        if env_key:
            env_val = os.environ.get(env_key, '')
            if env_val:
                config.api_key = env_val
        # Generic fallback
        if not config.api_key:
            config.api_key = os.environ.get('PYCLAUDE_API_KEY', config.api_key)

        # System prompt from AGENTS.md
        agents_md = Path.cwd() / 'AGENTS.md'
        if agents_md.exists():
            try:
                config.system_prompt = agents_md.read_text()[:4000]
            except OSError:
                pass

        return config

    def save(self) -> None:
        """Save config to ~/.pyclaude/config.json"""
        config_dir = Path.home() / '.pyclaude'
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / 'config.json'
        data = {}
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        data['provider'] = self.provider
        data['model'] = self.model
        if self.api_key:
            data['api_key'] = self.api_key
        if self.base_url:
            data['base_url'] = self.base_url
        config_file.write_text(json.dumps(data, indent=2))

    @property
    def is_configured(self) -> bool:
        if self.provider == 'ollama':
            return True  # No key needed
        return bool(self.api_key)


@dataclass
class ChatMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str


@dataclass
class ModelResponse:
    content: str
    model: str
    provider: str = ''
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ''


class BaseProvider(ABC):
    """Abstract base for model providers."""

    def __init__(self, config: ModelConfig):
        self.config = config

    @abstractmethod
    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        ...

    @abstractmethod
    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        ...

    @property
    def name(self) -> str:
        return self.config.provider


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.config.api_key)
            except ImportError:
                raise RuntimeError('pip install anthropic')
        return self._client

    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        client = self._get_client()
        kwargs = {'model': self.config.model, 'max_tokens': self.config.max_tokens, 'messages': messages}
        if system:
            kwargs['system'] = system
        response = client.messages.create(**kwargs)
        content = response.content[0].text if response.content else ''
        return ModelResponse(
            content=content, model=response.model, provider='anthropic',
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or '',
        )

    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        client = self._get_client()
        kwargs = {'model': self.config.model, 'max_tokens': self.config.max_tokens, 'messages': messages}
        if system:
            kwargs['system'] = system
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text


class OpenAICompatProvider(BaseProvider):
    """OpenAI-compatible provider (works with OpenAI, DeepSeek, Grok, Groq, Together, OpenRouter, etc.)"""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                kwargs = {}
                if self.config.api_key:
                    kwargs['api_key'] = self.config.api_key
                if self.config.base_url:
                    kwargs['base_url'] = self.config.base_url
                self._client = OpenAI(**kwargs)
            except ImportError:
                raise RuntimeError('pip install openai')
        return self._client

    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        client = self._get_client()
        msgs = []
        if system:
            msgs.append({'role': 'system', 'content': system})
        msgs.extend(messages)
        response = client.chat.completions.create(
            model=self.config.model, messages=msgs,
            max_tokens=self.config.max_tokens, temperature=self.config.temperature,
        )
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice else ''
        usage = response.usage
        return ModelResponse(
            content=content or '', model=response.model or self.config.model,
            provider=self.config.provider,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            stop_reason=choice.finish_reason if choice else '',
        )

    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        client = self._get_client()
        msgs = []
        if system:
            msgs.append({'role': 'system', 'content': system})
        msgs.extend(messages)
        stream = client.chat.completions.create(
            model=self.config.model, messages=msgs,
            max_tokens=self.config.max_tokens, temperature=self.config.temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class OllamaProvider(BaseProvider):
    """Ollama local provider - no API key needed."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.base_url = config.base_url or 'http://localhost:11434'

    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        import urllib.request
        msgs = []
        if system:
            msgs.append({'role': 'system', 'content': system})
        msgs.extend(messages)
        payload = json.dumps({'model': self.config.model, 'messages': msgs, 'stream': False}).encode()
        req = urllib.request.Request(
            f'{self.base_url}/api/chat', data=payload,
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        content = data.get('message', {}).get('content', '')
        return ModelResponse(
            content=content, model=self.config.model, provider='ollama',
            input_tokens=data.get('prompt_eval_count', 0),
            output_tokens=data.get('eval_count', 0),
        )

    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        import urllib.request
        msgs = []
        if system:
            msgs.append({'role': 'system', 'content': system})
        msgs.extend(messages)
        payload = json.dumps({'model': self.config.model, 'messages': msgs, 'stream': True}).encode()
        req = urllib.request.Request(
            f'{self.base_url}/api/chat', data=payload,
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                try:
                    data = json.loads(line)
                    content = data.get('message', {}).get('content', '')
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue


def create_provider(config: ModelConfig) -> BaseProvider:
    """Factory - create the right provider based on config."""
    if config.provider == 'anthropic':
        return AnthropicProvider(config)
    elif config.provider == 'ollama':
        return OllamaProvider(config)
    else:
        # Everything else uses OpenAI-compatible API
        return OpenAICompatProvider(config)


class ModelClient:
    """Multi-provider model client with conversation history."""

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig.from_env()
        self.history: list[ChatMessage] = []
        self._provider: BaseProvider | None = None

    @property
    def provider(self) -> BaseProvider:
        if self._provider is None:
            self._provider = create_provider(self.config)
        return self._provider

    def chat(self, message: str) -> ModelResponse:
        """Send a message and get a complete response."""
        self.history.append(ChatMessage(role='user', content=message))
        messages = [{'role': m.role, 'content': m.content} for m in self.history]
        response = self.provider.chat(messages, system=self.config.system_prompt)
        self.history.append(ChatMessage(role='assistant', content=response.content))
        return response

    def stream_chat(self, message: str) -> Iterator[str]:
        """Stream a response token by token. Accumulates in history."""
        self.history.append(ChatMessage(role='user', content=message))
        messages = [{'role': m.role, 'content': m.content} for m in self.history]
        full_content = ''
        for token in self.provider.stream_chat(messages, system=self.config.system_prompt):
            full_content += token
            yield token
        self.history.append(ChatMessage(role='assistant', content=full_content))

    def switch_provider(self, provider: str, model: str = '', api_key: str = '') -> None:
        """Switch to a different provider on the fly."""
        preset = PROVIDER_PRESETS.get(provider, {})
        self.config.provider = provider
        self.config.model = model or preset.get('default_model', '')
        self.config.base_url = preset.get('base_url', '')
        if api_key:
            self.config.api_key = api_key
        elif preset.get('env_key'):
            self.config.api_key = os.environ.get(preset['env_key'], self.config.api_key)
        self._provider = None  # Force re-create

    def clear_history(self) -> None:
        self.history.clear()

    @property
    def turn_count(self) -> int:
        return len([m for m in self.history if m.role == 'user'])


def setup_interactive() -> ModelConfig:
    """Interactive setup wizard for configuring the model provider."""
    print(f'\n{BOLD}Pyclaude Setup{RESET}\n')
    print(f'Available providers:\n')

    providers = list(PROVIDER_PRESETS.keys())
    for i, name in enumerate(providers, 1):
        preset = PROVIDER_PRESETS[name]
        needs_key = '(needs API key)' if preset['env_key'] else '(local, no key needed)'
        print(f'  {CYAN}{i}{RESET}. {name:15s} {DIM}{preset["default_model"]:30s} {needs_key}{RESET}')

    print(f'\n  {CYAN}0{RESET}. Custom OpenAI-compatible endpoint')
    print()

    choice = input('Select provider [1]: ').strip() or '1'

    if choice == '0':
        # Custom endpoint
        provider = 'custom'
        base_url = input('Base URL (e.g. http://localhost:8080/v1): ').strip()
        model = input('Model name: ').strip()
        api_key = input('API key (or empty): ').strip()
        config = ModelConfig(provider='custom', model=model, api_key=api_key, base_url=base_url)
    else:
        try:
            idx = int(choice) - 1
            provider = providers[idx]
        except (ValueError, IndexError):
            provider = 'anthropic'

        preset = PROVIDER_PRESETS[provider]
        model = input(f'Model [{preset["default_model"]}]: ').strip() or preset['default_model']

        api_key = ''
        if preset['env_key']:
            existing = os.environ.get(preset['env_key'], '')
            if existing:
                print(f'{GREEN}API key found in ${preset["env_key"]}{RESET}')
                api_key = existing
            else:
                api_key = input(f'API key: ').strip()

        config = ModelConfig(provider=provider, model=model, api_key=api_key, base_url=preset['base_url'])

    config.save()
    print(f'\n{GREEN}Configuration saved to ~/.pyclaude/config.json{RESET}')
    print(f'Provider: {config.provider}, Model: {config.model}\n')
    return config
