"""Orbit multi-provider model client.

Supports: Anthropic (Claude), OpenAI (GPT), Ollama (local), DeepSeek, Grok (xAI),
and any OpenAI-compatible API endpoint.

Configuration priority (highest to lowest):
  1. Environment variables (ORBIT_PROVIDER, ORBIT_MODEL, ORBIT_API_KEY, ORBIT_BASE_URL)
  2. Provider-specific env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY, …)
  3. ~/.orbit/config.json
  4. Built-in defaults from PROVIDER_PRESETS

Optional SDK dependencies — wrapped in try/except so the module imports cleanly
even when neither `anthropic` nor `openai` is installed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
BOLD   = '\033[1m'
DIM    = '\033[2m'
GREEN  = '\033[32m'
YELLOW = '\033[33m'
RED    = '\033[31m'
CYAN   = '\033[36m'
RESET  = '\033[0m'

# ---------------------------------------------------------------------------
# Provider presets
# (provider_name → default_model, env_key, base_url)
# ---------------------------------------------------------------------------
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
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
        'env_key': '',  # No API key required
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

# Providers whose streaming API returns per-chunk usage when
# stream_options={"include_usage": True} is requested.
_STREAM_USAGE_PROVIDERS = {'openai', 'groq', 'openrouter', 'deepseek'}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    provider: str = 'anthropic'
    model: str = ''
    api_key: str = ''
    base_url: str = ''
    max_tokens: int = 4096
    temperature: float = 0.7
    system_prompt: str = ''

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> 'ModelConfig':
        """Build config by merging config file + environment variables.

        Load order (later sources override earlier ones):
          1. Hardcoded defaults (dataclass field defaults above)
          2. ~/.orbit/config.json
          3. Provider-specific env var (e.g. ANTHROPIC_API_KEY)
          4. Generic ORBIT_* env vars
        """
        config = cls()

        # --- 1. Config file ---
        config_file = Path.home() / '.orbit' / 'config.json'
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding='utf-8'))
                config.provider    = data.get('provider', config.provider)
                config.model       = data.get('model', '')
                config.api_key     = data.get('api_key', '')
                config.base_url    = data.get('base_url', '')
                config.max_tokens  = int(data.get('max_tokens', config.max_tokens))
                config.temperature = float(data.get('temperature', config.temperature))
            except (json.JSONDecodeError, OSError, ValueError):
                pass  # Corrupt file — fall back to defaults silently

        # --- 2. Generic ORBIT_* env overrides ---
        config.provider = os.environ.get('ORBIT_PROVIDER', config.provider)
        config.model    = os.environ.get('ORBIT_MODEL', config.model)
        config.base_url = os.environ.get('ORBIT_BASE_URL', config.base_url)

        # --- 3. Resolve preset for the chosen provider ---
        preset = PROVIDER_PRESETS.get(config.provider, {})
        if not config.model:
            config.model = preset.get('default_model', 'gpt-4o')
        if not config.base_url:
            config.base_url = preset.get('base_url', '')

        # --- 4. API key resolution ---
        # Provider-specific var first (e.g. ANTHROPIC_API_KEY), then ORBIT_API_KEY
        provider_env_key = preset.get('env_key', '')
        if provider_env_key:
            env_val = os.environ.get(provider_env_key, '')
            if env_val:
                config.api_key = env_val
        # Generic override always wins when set
        orbit_key = os.environ.get('ORBIT_API_KEY', '')
        if orbit_key:
            config.api_key = orbit_key

        # --- 5. System prompt from AGENTS.md in cwd ---
        agents_md = Path.cwd() / 'AGENTS.md'
        if agents_md.exists():
            try:
                config.system_prompt = agents_md.read_text(encoding='utf-8')[:4000]
            except OSError:
                pass

        return config

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist this config to ~/.orbit/config.json (merge, never clobber)."""
        config_dir  = Path.home() / '.orbit'
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / 'config.json'

        # Read existing file so we don't lose unrelated keys
        existing: dict = {}
        if config_file.exists():
            try:
                existing = json.loads(config_file.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                pass

        existing['provider']    = self.provider
        existing['model']       = self.model
        existing['max_tokens']  = self.max_tokens
        existing['temperature'] = self.temperature
        if self.api_key:
            existing['api_key'] = self.api_key
        if self.base_url:
            existing['base_url'] = self.base_url

        config_file.write_text(json.dumps(existing, indent=2), encoding='utf-8')

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True when we have enough information to attempt an API call."""
        if self.provider == 'ollama':
            return bool(self.base_url)  # Base URL required; no API key needed
        if self.provider == 'custom':
            return bool(self.api_key) and bool(self.base_url)
        return bool(self.api_key)

    def __repr__(self) -> str:
        key_hint = f'{self.api_key[:6]}…' if self.api_key else '(none)'
        return (
            f'ModelConfig(provider={self.provider!r}, model={self.model!r}, '
            f'api_key={key_hint!r}, base_url={self.base_url!r})'
        )


# ---------------------------------------------------------------------------
# Message / response types
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    role: str     # 'user' | 'assistant' | 'system'
    content: str


@dataclass
class ModelResponse:
    content: str
    model: str
    provider: str = ''
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ''

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# Base provider
# ---------------------------------------------------------------------------

class BaseProvider(ABC):
    """Abstract base class for all model providers."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    @abstractmethod
    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        """Send messages and return a complete response."""
        ...

    @abstractmethod
    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        """Stream response tokens one-by-one as a generator."""
        ...

    @property
    def name(self) -> str:
        return self.config.provider


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------

class AnthropicProvider(BaseProvider):
    """Anthropic Claude via the official `anthropic` SDK.

    Install: pip install anthropic
    """

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazily create the Anthropic client, raising a clear error on missing dep."""
        if self._client is None:
            try:
                import anthropic as _anthropic  # noqa: PLC0415
            except ImportError:
                raise RuntimeError(
                    'The anthropic package is required for this provider.\n'
                    'Install it with: pip install anthropic'
                )
            self._client = _anthropic.Anthropic(api_key=self.config.api_key)
        return self._client

    def _build_kwargs(self, messages: list[dict], system: str) -> dict:
        kwargs: dict = {
            'model':      self.config.model,
            'max_tokens': self.config.max_tokens,
            'messages':   messages,
        }
        if self.config.temperature != 1.0:
            # Anthropic default is 1.0; only send if caller changed it
            kwargs['temperature'] = self.config.temperature
        if system:
            kwargs['system'] = system
        return kwargs

    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        """Blocking full-response call to the Anthropic Messages API."""
        try:
            import anthropic as _anthropic  # noqa: PLC0415
            client = self._get_client()
            response = client.messages.create(**self._build_kwargs(messages, system))
            content = response.content[0].text if response.content else ''
            return ModelResponse(
                content=content,
                model=response.model,
                provider='anthropic',
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                stop_reason=response.stop_reason or '',
            )
        except _anthropic.AuthenticationError as exc:
            raise PermissionError(
                f'Anthropic authentication failed — check your API key.\n{exc}'
            ) from exc
        except _anthropic.RateLimitError as exc:
            raise RuntimeError(
                f'Anthropic rate limit reached. Wait a moment and try again.\n{exc}'
            ) from exc
        except _anthropic.APIConnectionError as exc:
            raise ConnectionError(
                f'Could not connect to Anthropic API: {exc}'
            ) from exc
        except _anthropic.BadRequestError as exc:
            raise ValueError(
                f'Anthropic rejected the request (bad input): {exc}'
            ) from exc
        except _anthropic.APIStatusError as exc:
            raise RuntimeError(
                f'Anthropic API error {exc.status_code}: {exc.message}'
            ) from exc

    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        """Stream response tokens from the Anthropic Messages streaming API.

        Yields raw text deltas. The caller is responsible for accumulating them.
        Uses the SDK's managed `messages.stream()` context manager which handles
        reconnection and event parsing internally.
        """
        try:
            import anthropic as _anthropic  # noqa: PLC0415
            client = self._get_client()
            with client.messages.stream(**self._build_kwargs(messages, system)) as stream:
                for text in stream.text_stream:
                    yield text
        except _anthropic.AuthenticationError as exc:
            raise PermissionError(
                f'Anthropic authentication failed — check your API key.\n{exc}'
            ) from exc
        except _anthropic.RateLimitError as exc:
            raise RuntimeError(
                f'Anthropic rate limit reached. Wait a moment and try again.\n{exc}'
            ) from exc
        except _anthropic.APIConnectionError as exc:
            raise ConnectionError(
                f'Could not connect to Anthropic API: {exc}'
            ) from exc
        except _anthropic.APIStatusError as exc:
            raise RuntimeError(
                f'Anthropic API error {exc.status_code}: {exc.message}'
            ) from exc


# ---------------------------------------------------------------------------
# OpenAI-compatible provider
# ---------------------------------------------------------------------------

class OpenAICompatProvider(BaseProvider):
    """OpenAI and every OpenAI-compatible API (DeepSeek, Grok, Groq, Together, OpenRouter…).

    Install: pip install openai
    """

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self._client = None
        # Whether to request per-stream-chunk usage from this provider
        self._request_stream_usage: bool = (
            config.provider in _STREAM_USAGE_PROVIDERS
        )

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI  # noqa: PLC0415
            except ImportError:
                raise RuntimeError(
                    'The openai package is required for this provider.\n'
                    'Install it with: pip install openai'
                )
            kwargs: dict = {}
            if self.config.api_key:
                kwargs['api_key'] = self.config.api_key
            if self.config.base_url:
                kwargs['base_url'] = self.config.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def _build_messages(self, messages: list[dict], system: str) -> list[dict]:
        """Prepend system message when provided."""
        if system:
            return [{'role': 'system', 'content': system}, *messages]
        return list(messages)

    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        """Blocking chat completion call."""
        try:
            import openai as _openai  # noqa: PLC0415
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.config.model,
                messages=self._build_messages(messages, system),
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            choice = response.choices[0] if response.choices else None
            usage  = response.usage
            return ModelResponse(
                content=choice.message.content if choice and choice.message.content else '',
                model=response.model or self.config.model,
                provider=self.config.provider,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                stop_reason=choice.finish_reason if choice else '',
            )
        except _openai.AuthenticationError as exc:
            raise PermissionError(
                f'Authentication failed for {self.config.provider} — check your API key.\n{exc}'
            ) from exc
        except _openai.RateLimitError as exc:
            raise RuntimeError(
                f'{self.config.provider} rate limit reached. Wait a moment and try again.\n{exc}'
            ) from exc
        except _openai.APIConnectionError as exc:
            raise ConnectionError(
                f'Could not connect to {self.config.provider} ({self.config.base_url}): {exc}'
            ) from exc
        except _openai.BadRequestError as exc:
            raise ValueError(
                f'{self.config.provider} rejected the request: {exc}'
            ) from exc
        except _openai.APIStatusError as exc:
            raise RuntimeError(
                f'{self.config.provider} API error {exc.status_code}: {exc.message}'
            ) from exc

    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        """Stream chat completion tokens.

        For providers that support it (OpenAI, Groq, OpenRouter, DeepSeek), we
        request per-stream usage so token counts are available on the final chunk.
        The generator yields text deltas only; the ModelClient accumulates them.
        """
        try:
            import openai as _openai  # noqa: PLC0415
            client = self._get_client()

            create_kwargs: dict = dict(
                model=self.config.model,
                messages=self._build_messages(messages, system),
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                stream=True,
            )
            if self._request_stream_usage:
                create_kwargs['stream_options'] = {'include_usage': True}

            stream = client.chat.completions.create(**create_kwargs)

            for chunk in stream:
                if not chunk.choices:
                    # Final chunk may carry usage but no choices — ignore for token
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        except _openai.AuthenticationError as exc:
            raise PermissionError(
                f'Authentication failed for {self.config.provider} — check your API key.\n{exc}'
            ) from exc
        except _openai.RateLimitError as exc:
            raise RuntimeError(
                f'{self.config.provider} rate limit reached. Wait a moment and try again.\n{exc}'
            ) from exc
        except _openai.APIConnectionError as exc:
            raise ConnectionError(
                f'Could not connect to {self.config.provider} ({self.config.base_url}): {exc}'
            ) from exc
        except _openai.APIStatusError as exc:
            raise RuntimeError(
                f'{self.config.provider} API error {exc.status_code}: {exc.message}'
            ) from exc


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------

class OllamaProvider(BaseProvider):
    """Ollama local inference — no API key required.

    Uses only stdlib (urllib) so there is no extra dependency.
    Ollama must be running at base_url (default: http://localhost:11434).
    """

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self.base_url = (config.base_url or 'http://localhost:11434').rstrip('/')

    def _request(self, endpoint: str, payload: dict, *, timeout: int = 120) -> urllib.request.Request:
        body = json.dumps(payload).encode('utf-8')
        return urllib.request.Request(
            f'{self.base_url}{endpoint}',
            data=body,
            headers={'Content-Type': 'application/json'},
        )

    def _wrap_url_error(self, exc: urllib.error.URLError) -> ConnectionError:
        reason = str(exc.reason) if hasattr(exc, 'reason') else str(exc)
        return ConnectionError(
            f'Could not reach Ollama at {self.base_url}. '
            f'Is Ollama running? ({reason})'
        )

    def chat(self, messages: list[dict], system: str = '') -> ModelResponse:
        """Blocking chat call via Ollama /api/chat endpoint."""
        msgs: list[dict] = []
        if system:
            msgs.append({'role': 'system', 'content': system})
        msgs.extend(messages)

        payload = {
            'model':    self.config.model,
            'messages': msgs,
            'stream':   False,
        }
        req = self._request('/api/chat', payload)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data: dict = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
            raise RuntimeError(
                f'Ollama returned HTTP {exc.code}: {body}'
            ) from exc
        except urllib.error.URLError as exc:
            raise self._wrap_url_error(exc) from exc

        content = data.get('message', {}).get('content', '')
        return ModelResponse(
            content=content,
            model=self.config.model,
            provider='ollama',
            input_tokens=data.get('prompt_eval_count', 0),
            output_tokens=data.get('eval_count', 0),
            stop_reason='stop' if data.get('done') else '',
        )

    def stream_chat(self, messages: list[dict], system: str = '') -> Iterator[str]:
        """Stream chat tokens from Ollama's newline-delimited JSON stream.

        Ollama sends one JSON object per line. Each line has:
          {"message": {"role": "assistant", "content": "..."}, "done": false}
        The final line has "done": true and contains token-count stats but
        an empty content string — we skip it.
        """
        msgs: list[dict] = []
        if system:
            msgs.append({'role': 'system', 'content': system})
        msgs.extend(messages)

        payload = {
            'model':    self.config.model,
            'messages': msgs,
            'stream':   True,
        }
        req = self._request('/api/chat', payload)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data: dict = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # Malformed line — skip

                    # The final summary line has done=True but empty content.
                    # Skip it so we don't yield an empty string to the caller.
                    if data.get('done'):
                        break

                    content = data.get('message', {}).get('content', '')
                    if content:
                        yield content

        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
            raise RuntimeError(
                f'Ollama returned HTTP {exc.code}: {body}'
            ) from exc
        except urllib.error.URLError as exc:
            raise self._wrap_url_error(exc) from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_provider(config: ModelConfig) -> BaseProvider:
    """Instantiate the correct provider for the given config."""
    if config.provider == 'anthropic':
        return AnthropicProvider(config)
    elif config.provider == 'ollama':
        return OllamaProvider(config)
    else:
        # All other named providers + 'custom' use the OpenAI-compatible API
        return OpenAICompatProvider(config)


# ---------------------------------------------------------------------------
# ModelClient — conversation manager
# ---------------------------------------------------------------------------

class ModelClient:
    """Multi-provider model client with persistent conversation history.

    Usage::

        client = ModelClient()                         # auto-configure from env
        response = client.chat("What is Django?")      # blocking
        for token in client.stream_chat("explain it"): # streaming
            print(token, end='', flush=True)

    The client maintains full conversation history across turns so each new
    message is sent with all prior context.
    """

    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig.from_env()
        self.history: list[ChatMessage] = []
        self._provider: BaseProvider | None = None
        # Running token totals across all turns in this session
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        # Last complete response (useful for callers that stream but want metadata)
        self.last_response: ModelResponse | None = None

    # ------------------------------------------------------------------
    # Provider access (lazy init)
    # ------------------------------------------------------------------

    @property
    def provider(self) -> BaseProvider:
        if self._provider is None:
            self._provider = create_provider(self.config)
        return self._provider

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def chat(self, message: str) -> ModelResponse:
        """Send *message*, accumulate history, return a complete ModelResponse.

        Raises:
            PermissionError: Invalid or missing API key.
            ConnectionError: Network or server unreachable.
            RuntimeError:    Rate limit or other API error.
            ValueError:      Bad request (e.g. invalid model name).
        """
        self.history.append(ChatMessage(role='user', content=message))
        messages = self._history_as_dicts()
        response = self.provider.chat(messages, system=self.config.system_prompt)
        self.history.append(ChatMessage(role='assistant', content=response.content))
        self._update_token_counts(response.input_tokens, response.output_tokens)
        self.last_response = response
        return response

    def stream_chat(self, message: str) -> Iterator[str]:
        """Stream *message* token by token; accumulate history when complete.

        Yields individual text delta strings as they arrive from the provider.
        History is updated with the full accumulated response once the stream ends.

        Raises:
            PermissionError: Invalid or missing API key.
            ConnectionError: Network or server unreachable.
            RuntimeError:    Rate limit or other API error.
        """
        self.history.append(ChatMessage(role='user', content=message))
        messages = self._history_as_dicts()
        accumulated = ''
        try:
            for token in self.provider.stream_chat(messages, system=self.config.system_prompt):
                accumulated += token
                yield token
        finally:
            # Always append whatever we got, even on an interrupted stream
            if accumulated:
                self.history.append(ChatMessage(role='assistant', content=accumulated))
                # Streaming doesn't return token counts in most providers, so we
                # create a partial response for last_response tracking.
                self.last_response = ModelResponse(
                    content=accumulated,
                    model=self.config.model,
                    provider=self.config.provider,
                    # Token counts unavailable from most streaming APIs without
                    # an extra round-trip; leave as 0 and callers that need them
                    # should use the blocking chat() method instead.
                    input_tokens=0,
                    output_tokens=0,
                )

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def switch_provider(self, provider: str, model: str = '', api_key: str = '') -> None:
        """Hot-swap to a different provider without losing conversation history.

        Args:
            provider: Provider name from PROVIDER_PRESETS, or 'custom'.
            model:    Model name. Defaults to the preset default.
            api_key:  API key. Falls back to the relevant env var.
        """
        preset = PROVIDER_PRESETS.get(provider, {})
        self.config.provider = provider
        self.config.model    = model or preset.get('default_model', '')
        self.config.base_url = preset.get('base_url', '')

        if api_key:
            self.config.api_key = api_key
        elif preset.get('env_key'):
            self.config.api_key = os.environ.get(preset['env_key'], self.config.api_key)

        self._provider = None  # Force re-creation on next access

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """Reset conversation history (does not reset token counters)."""
        self.history.clear()

    def _history_as_dicts(self) -> list[dict]:
        """Serialize history to the message format expected by all providers."""
        return [{'role': m.role, 'content': m.content} for m in self.history]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def turn_count(self) -> int:
        """Number of user turns sent so far."""
        return sum(1 for m in self.history if m.role == 'user')

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def _update_token_counts(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens  += input_tokens
        self.total_output_tokens += output_tokens

    def __repr__(self) -> str:
        return (
            f'ModelClient(provider={self.config.provider!r}, '
            f'model={self.config.model!r}, '
            f'turns={self.turn_count}, '
            f'configured={self.config.is_configured})'
        )


# ---------------------------------------------------------------------------
# Interactive setup wizard
# ---------------------------------------------------------------------------

def setup_interactive() -> ModelConfig:
    """CLI wizard that guides the user through provider selection and saves config.

    Walks through:
      1. Provider selection (numbered list or custom endpoint)
      2. Model override (with sensible default)
      3. API key entry (with env var detection)
      4. Optional connectivity test
      5. Save to ~/.orbit/config.json

    Returns:
        A fully populated and saved ModelConfig.
    """
    print(f'\n{BOLD}Orbit Model Setup{RESET}\n')
    print('Available providers:\n')

    providers = list(PROVIDER_PRESETS.keys())
    for i, name in enumerate(providers, 1):
        preset = PROVIDER_PRESETS[name]
        key_hint = f'env: ${preset["env_key"]}' if preset['env_key'] else 'no key needed'
        print(
            f'  {CYAN}{i}{RESET}. {name:<15s} '
            f'{DIM}{preset["default_model"]:<38s} ({key_hint}){RESET}'
        )
    print(f'\n  {CYAN}0{RESET}. Custom OpenAI-compatible endpoint')
    print()

    raw_choice = input('Select provider [1]: ').strip() or '1'

    config: ModelConfig

    if raw_choice == '0':
        # ---------- Custom endpoint ----------
        base_url = input('Base URL (e.g. http://localhost:8080/v1): ').strip()
        if not base_url:
            print(f'{RED}Base URL is required for a custom endpoint.{RESET}')
            base_url = 'http://localhost:8080/v1'
        model   = input('Model name: ').strip() or 'default'
        api_key = input('API key (or leave empty if not required): ').strip()
        config  = ModelConfig(
            provider='custom',
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
    else:
        # ---------- Named provider ----------
        try:
            idx      = int(raw_choice) - 1
            provider = providers[idx]
        except (ValueError, IndexError):
            print(f'{YELLOW}Invalid choice, defaulting to anthropic.{RESET}')
            provider = 'anthropic'

        preset   = PROVIDER_PRESETS[provider]
        default_model = preset['default_model']
        model    = input(f'Model [{default_model}]: ').strip() or default_model

        api_key = ''
        if preset['env_key']:
            existing = os.environ.get(preset['env_key'], '')
            if existing:
                print(f'{GREEN}Found ${preset["env_key"]} in environment — using it.{RESET}')
                api_key = existing
            else:
                # Also check ORBIT_API_KEY as a universal fallback
                orbit_key = os.environ.get('ORBIT_API_KEY', '')
                if orbit_key:
                    print(f'{GREEN}Found $ORBIT_API_KEY in environment — using it.{RESET}')
                    api_key = orbit_key
                else:
                    api_key = input(f'API key for {provider}: ').strip()
                    if not api_key:
                        print(
                            f'{YELLOW}No API key provided. You can set ${preset["env_key"]} '
                            f'later and Orbit will pick it up automatically.{RESET}'
                        )

        config = ModelConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=preset['base_url'],
        )

    # ---------- Optional connectivity test ----------
    if config.is_configured:
        do_test = input('\nTest connection now? [Y/n]: ').strip().lower()
        if do_test in ('', 'y', 'yes'):
            print(f'{DIM}Testing connection to {config.provider}…{RESET}', end=' ', flush=True)
            try:
                test_client = ModelClient(config)
                # Send a minimal, cheap prompt
                test_client.chat('Reply with only the word "OK".')
                print(f'{GREEN}OK{RESET}')
            except PermissionError:
                print(f'{RED}FAILED — authentication error. Double-check your API key.{RESET}')
            except ConnectionError as exc:
                print(f'{RED}FAILED — could not connect: {exc}{RESET}')
            except Exception as exc:  # noqa: BLE001
                print(f'{RED}FAILED — {exc}{RESET}')

    # ---------- Save ----------
    config.save()
    print(f'\n{GREEN}Configuration saved to ~/.orbit/config.json{RESET}')
    print(f'Provider : {BOLD}{config.provider}{RESET}')
    print(f'Model    : {BOLD}{config.model}{RESET}')
    if not config.is_configured:
        print(
            f'\n{YELLOW}Note: no API key configured yet. '
            f'Set the relevant env var before using Orbit.{RESET}'
        )
    print()
    return config
