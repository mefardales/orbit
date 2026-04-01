"""One-shot prompt handler, mirrors src/cli/ask.ts."""

from __future__ import annotations

from .constants import EXIT_ERROR, EXIT_OK


def send_ask(prompt: str, model: str | None = None) -> int:
    """Send a single prompt and print the response.

    This is a placeholder that echoes the prompt.  A real implementation
    would route through the agent runtime.
    """
    if not prompt.strip():
        print('Error: empty prompt')
        return EXIT_ERROR

    label = f' (model={model})' if model else ''
    print(f'[ask{label}] {prompt}')
    return EXIT_OK
