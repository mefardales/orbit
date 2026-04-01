"""Orbit ask command - non-interactive single-shot prompt handler.

Supports multiple providers (claude, openai, ollama), optional role enhancement
from prompt .md files, and rich terminal output with markdown rendering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from .constants import EXIT_ERROR, EXIT_OK

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

OutputFormat = Literal["text", "json", "markdown"]
Provider = Literal["claude", "openai", "ollama"]

# Provider aliases mapped to ModelClient provider names
_PROVIDER_MAP: dict[str, str] = {
    "claude": "anthropic",
    "anthropic": "anthropic",
    "openai": "openai",
    "gpt": "openai",
    "ollama": "ollama",
}

# ---------------------------------------------------------------------------
# Prompt resolution
# ---------------------------------------------------------------------------

def _pkg_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _resolve_prompt_file(role: str) -> Path | None:
    """Search for {role}.md in project prompts/ then ~/.orbit/prompts/."""
    candidates = [
        _pkg_root() / "prompts" / f"{role}.md",
        Path.home() / ".orbit" / "prompts" / f"{role}.md",
        Path.cwd() / "prompts" / f"{role}.md",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _load_role_prompt(role: str) -> str | None:
    """Load and return the text of a role prompt file, stripping YAML frontmatter."""
    path = _resolve_prompt_file(role)
    if path is None:
        return None
    content = path.read_text(encoding="utf-8")
    import re
    match = re.match(r"^---\r?\n[\s\S]*?\r?\n---\r?\n?", content)
    if match:
        content = content[match.end():].strip()
    return content


# ---------------------------------------------------------------------------
# Rich output rendering
# ---------------------------------------------------------------------------

def _get_console():
    """Get or create a Rich console instance with UTF-8 support."""
    import io
    from rich.console import Console
    from rich.theme import Theme
    theme = Theme({
        "orbit.green": "green",
        "orbit.cyan": "cyan",
        "orbit.dim": "dim",
        "orbit.accent": "bold cyan",
    })
    # Force UTF-8 output on Windows to avoid cp1252 encoding errors
    file = None
    if sys.platform == 'win32':
        try:
            file = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass
    return Console(theme=theme, file=file, force_terminal=True)


def _render_rich(response_text: str, provider: str, model: str, console):
    """Render response with rich markdown, syntax highlighting, and panels."""
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.text import Text

    # Header with provider info
    header = Text()
    header.append(f" {provider}", style="bold green")
    header.append(" \u00b7 ", style="dim")
    header.append(model, style="dim")
    console.print(header)
    console.print()

    # Render response as markdown (handles code blocks, headers, lists, etc.)
    md = Markdown(response_text)
    console.print(md)
    console.print()


def _render_streaming_rich(token_iter, provider: str, model: str, console):
    """Accumulate tokens with spinner, then render once as rich markdown."""
    from rich.markdown import Markdown
    from rich.text import Text

    # Header
    header = Text()
    header.append(f" {provider}", style="bold green")
    header.append(" \u00b7 ", style="dim")
    header.append(model, style="dim")
    console.print(header)

    # Accumulate all tokens with orbit spinner, then render once
    from .rich_output import OrbitSpinner
    full_text = ""
    with OrbitSpinner(console):
        for token in token_iter:
            full_text += token

    if not full_text:
        console.print("[dim]No response received.[/]")
        return ""

    # Single rich render
    console.print()
    console.print(Markdown(full_text))
    console.print()
    return full_text


def _format_json(response_text: str, prompt: str, provider: str, model: str) -> str:
    payload = {
        "prompt": prompt,
        "response": response_text,
        "provider": provider,
        "model": model,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ask(
    prompt: str,
    provider: str | None = None,
    role: str | None = None,
    output_format: OutputFormat = "text",
    model: str | None = None,
    stream: bool = False,
) -> int:
    """Send a single prompt to a model and print the response to stdout."""
    if not prompt.strip():
        print("Error: empty prompt", file=sys.stderr)
        return EXIT_ERROR

    try:
        from ..model_client import ModelClient, ModelConfig
    except ImportError:
        print("Error: model_client not available", file=sys.stderr)
        return EXIT_ERROR

    # Build config
    config = ModelConfig.from_env()

    # Apply provider override
    if provider:
        import os
        from ..model_client import PROVIDER_PRESETS

        resolved_provider = _PROVIDER_MAP.get(provider.lower(), provider.lower())
        preset = PROVIDER_PRESETS.get(resolved_provider, {})

        config.provider = resolved_provider
        config.base_url = preset.get("base_url", "")
        if not model:
            config.model = preset.get("default_model", "")
        env_key = preset.get("env_key", "")
        config.api_key = ""
        if env_key:
            config.api_key = os.environ.get(env_key, "")

    # Apply model override
    if model:
        config.model = model

    # Role enhancement
    if role:
        role_prompt = _load_role_prompt(role)
        if role_prompt:
            config.system_prompt = role_prompt
        else:
            print(
                f"Warning: role '{role}' not found in prompts/ or ~/.orbit/prompts/",
                file=sys.stderr,
            )

    client = ModelClient(config=config)
    console = _get_console()

    try:
        if output_format == "json":
            # JSON output: no rich formatting
            if stream:
                full_text = ""
                for token in client.stream_chat(prompt):
                    full_text += token
                print(_format_json(full_text, prompt, config.provider, config.model))
            else:
                response = client.chat(prompt)
                print(_format_json(
                    response.content, prompt,
                    response.provider or config.provider,
                    response.model or config.model,
                ))
        elif stream:
            _render_streaming_rich(
                client.stream_chat(prompt),
                config.provider, config.model, console,
            )
        else:
            response = client.chat(prompt)
            _render_rich(
                response.content,
                response.provider or config.provider,
                response.model or config.model,
                console,
            )

    except RuntimeError as exc:
        console.print(f"[red]Error:[/] {exc}", highlight=False)
        return EXIT_ERROR
    except Exception as exc:
        console.print(f"[red]Error calling {config.provider}:[/] {exc}", highlight=False)
        return EXIT_ERROR

    return EXIT_OK


# ---------------------------------------------------------------------------
# Legacy shim
# ---------------------------------------------------------------------------

def send_ask(prompt: str, model: str | None = None) -> int:
    """Backward-compatible shim. Use run_ask() for new code."""
    return run_ask(prompt, model=model)
