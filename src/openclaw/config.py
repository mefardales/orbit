from __future__ import annotations
import json
from pathlib import Path
from .types import OpenclawConfig

def load_openclaw_config(project_root: Path) -> OpenclawConfig:
    config_path = project_root / '.omx' / 'openclaw.json'
    if not config_path.exists():
        return OpenclawConfig()
    data = json.loads(config_path.read_text())
    return OpenclawConfig(enabled=data.get('enabled', False), endpoint=data.get('endpoint', ''), token=data.get('token', ''))
