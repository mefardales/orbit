"""Path utilities for OMX."""
from __future__ import annotations
import os
from pathlib import Path

def get_omx_home() -> Path:
    return Path(os.environ.get('OMX_HOME', Path.home() / '.omx'))

def get_omx_state_dir() -> Path:
    return get_omx_home() / 'state'

def get_package_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent

def codex_agents_dir() -> Path:
    return Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'agents'
