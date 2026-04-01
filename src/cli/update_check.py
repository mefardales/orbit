"""Automatic update check for Orbit CLI."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .version import get_version

_STATE_DIR = Path.home() / '.orbit' / 'state'
_UPDATE_STATE_FILE = _STATE_DIR / 'update_check.json'
_CHECK_INTERVAL_SECONDS = 86400  # 24 hours
_PYPI_PACKAGE = 'orbit'


def _load_state() -> dict:
    try:
        return json.loads(_UPDATE_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _UPDATE_STATE_FILE.write_text(json.dumps(state))


def _fetch_latest_version() -> str | None:
    """Fetch the latest version from PyPI (non-blocking, best-effort)."""
    try:
        from urllib.request import urlopen
        from urllib.error import URLError
        url = f'https://pypi.org/pypi/{_PYPI_PACKAGE}/json'
        with urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read())
            return data.get('info', {}).get('version')
    except Exception:
        return None


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse version string to tuple for comparison."""
    parts = []
    for p in v.split('.'):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts)


def maybe_check_and_prompt_update() -> None:
    """Check for updates if enough time has passed. Print a notice if outdated."""
    try:
        state = _load_state()
        last_check = state.get('last_check', 0)
        now = time.time()

        if now - last_check < _CHECK_INTERVAL_SECONDS:
            return

        latest = _fetch_latest_version()
        state['last_check'] = now
        if latest:
            state['latest_version'] = latest
        _save_state(state)

        if latest and _version_tuple(latest) > _version_tuple(get_version()):
            print(
                f'\n  Update available: {get_version()} -> {latest}'
                f'\n  Run: pip install --upgrade {_PYPI_PACKAGE}\n'
            )
    except Exception:
        pass  # Never block CLI startup
