"""Mode state management for OMX runtime modes (autoresearch, team, etc.)."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

ModeKind = Literal['autoresearch', 'team', 'pipeline', 'idle']

@dataclass
class ModeState:
    kind: ModeKind = 'idle'
    active: bool = False
    run_id: str | None = None
    metadata: dict = field(default_factory=dict)
    updated_at: str = ''

def _state_path(project_root: Path) -> Path:
    return project_root / '.omx' / 'state' / 'mode-state.json'

def read_mode_state(project_root: Path) -> ModeState:
    path = _state_path(project_root)
    if not path.exists():
        return ModeState()
    data = json.loads(path.read_text())
    return ModeState(**{k: v for k, v in data.items() if k in ModeState.__dataclass_fields__})

def start_mode(project_root: Path, kind: ModeKind, run_id: str) -> ModeState:
    from datetime import datetime, timezone
    state = ModeState(kind=kind, active=True, run_id=run_id, updated_at=datetime.now(timezone.utc).isoformat())
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))
    return state

def cancel_mode(project_root: Path) -> ModeState:
    from datetime import datetime, timezone
    state = ModeState(updated_at=datetime.now(timezone.utc).isoformat())
    path = _state_path(project_root)
    if path.exists():
        path.write_text(json.dumps(asdict(state), indent=2))
    return state

def update_mode_state(project_root: Path, **updates) -> ModeState:
    state = read_mode_state(project_root)
    for k, v in updates.items():
        if hasattr(state, k):
            setattr(state, k, v)
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))
    return state
