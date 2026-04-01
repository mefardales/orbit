"""GitHub star prompt for community engagement."""
from __future__ import annotations

import json
import time
from pathlib import Path

_STATE_DIR = Path.home() / '.orbit' / 'state'
_STAR_STATE_FILE = _STATE_DIR / 'github_star.json'
_REPO_URL = 'https://github.com/mefardales/orbit'
_PROMPT_AFTER_RUNS = 5          # Show after N CLI invocations
_PROMPT_COOLDOWN_SECONDS = 604800  # 7 days between prompts


def _load_state() -> dict:
    try:
        return json.loads(_STAR_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _STAR_STATE_FILE.write_text(json.dumps(state))


def maybe_prompt_github_star() -> None:
    """Prompt the user to star the repo after enough usage."""
    try:
        state = _load_state()

        if state.get('dismissed'):
            return

        run_count = state.get('run_count', 0) + 1
        state['run_count'] = run_count
        now = time.time()

        last_prompt = state.get('last_prompt', 0)
        if run_count >= _PROMPT_AFTER_RUNS and (now - last_prompt) >= _PROMPT_COOLDOWN_SECONDS:
            print(
                f'\n  Enjoying Orbit? Give us a star on GitHub!'
                f'\n  -> {_REPO_URL}'
                f'\n  (Run `orbit star --dismiss` to hide this message)\n'
            )
            state['last_prompt'] = now

        _save_state(state)
    except Exception:
        pass  # Never block CLI startup
