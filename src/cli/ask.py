"""Orbit ask command - non-interactive single-shot prompt handler.

Supports multiple providers (claude, openai, ollama), optional role enhancement
from prompt .md files, and configurable output formats.
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
        # Also check relative to cwd for project-local overrides
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
    # Strip YAML frontmatter (--- ... ---)
    import re
    match = re.match(r"^---\r?\n[\s\S]*?\r?\n---\r?\n?", content)
    if match:
        content = content[match.end():].strip()
    return content


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _format_response(
    response_text: str,
    prompt: str,
    provider: str,
    model: str,
    output_format: OutputFormat,
) -> str:
    if output_format == "json":
        payload = {
            "prompt": prompt,
            "response": response_text,
            "provider": provider,
            "model": model,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if output_format == "markdown":
        lines = [
            f"## Response",
            "",
            f"**Provider:** {provider}  **Model:** {model}",
            "",
            response_text,
        ]
        return "\n".join(lines)

    # Default: plain text
    return response_text


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
    """Send a single prompt to a model and print the response to stdout.

    Args:
        prompt:        The user prompt text.
        provider:      Provider override: 'claude', 'openai', 'ollama', or any
                       name accepted by ModelClient. Defaults to config/env.
        role:          Agent role name (e.g. 'executor', 'architect').  When set,
                       the corresponding .md prompt is prepended as the system
                       prompt, enhancing context with posture/model overlays.
        output_format: 'text' (default), 'json', or 'markdown'.
        model:         Model override (e.g. 'gpt-4o', 'claude-3-5-sonnet-20241022').
        stream:        If True, stream tokens to stdout as they arrive.
    """
    if not prompt.strip():
        print("Error: empty prompt", file=sys.stderr)
        return EXIT_ERROR

    # Import here to avoid circular imports at module load time
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
        # Always reset base_url and model from the new preset when provider is
        # explicitly given - the loaded config values belong to the old provider.
        config.base_url = preset.get("base_url", "")
        if not model:
            config.model = preset.get("default_model", "")
        # Reset api_key to what the new preset expects
        env_key = preset.get("env_key", "")
        config.api_key = ""
        if env_key:
            config.api_key = os.environ.get(env_key, "")

    # Apply model override
    if model:
        config.model = model

    # Role enhancement: load .md system prompt
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

    # Execute
    try:
        if stream:
            full_text = ""
            for token in client.stream_chat(prompt):
                print(token, end="", flush=True)
                full_text += token
            print()  # Trailing newline
            if output_format != "text":
                # Re-format and reprint for non-text formats after streaming
                formatted = _format_response(
                    full_text, prompt, config.provider, config.model, output_format
                )
                print(formatted)
        else:
            response = client.chat(prompt)
            formatted = _format_response(
                response.content, prompt, response.provider or config.provider,
                response.model or config.model, output_format,
            )
            print(formatted)

    except RuntimeError as exc:
        # Provider-specific import errors (pip install needed)
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:
        print(f"Error calling {config.provider}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    return EXIT_OK


# ---------------------------------------------------------------------------
# Legacy shim (backward compat with old send_ask() callers)
# ---------------------------------------------------------------------------

def send_ask(prompt: str, model: str | None = None) -> int:
    """Backward-compatible shim. Use run_ask() for new code."""
    return run_ask(prompt, model=model)
