"""Planning artifacts for structured plan storage."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

@dataclass
class PlanArtifact:
    plan_id: str
    title: str
    steps: list[str] = field(default_factory=list)
    status: str = 'draft'
    created_at: str = ''
    updated_at: str = ''

def _artifacts_dir(project_root: Path) -> Path:
    return project_root / '.omx' / 'plans'

def save_plan_artifact(project_root: Path, artifact: PlanArtifact) -> Path:
    d = _artifacts_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f'{artifact.plan_id}.json'
    path.write_text(json.dumps(asdict(artifact), indent=2))
    return path

def load_plan_artifact(project_root: Path, plan_id: str) -> PlanArtifact | None:
    path = _artifacts_dir(project_root) / f'{plan_id}.json'
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return PlanArtifact(**data)
