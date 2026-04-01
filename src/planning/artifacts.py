"""Planning artifacts: save, load, list, and delete plan files."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class PlanArtifact:
    """A serialisable planning artifact."""

    artifact_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    plan_type: str = "generic"  # generic | implementation | migration | review
    status: str = "draft"  # draft | active | completed | archived
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    author: str = ""
    tags: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(
        self,
        description: str,
        *,
        assignee: str = "",
        done: bool = False,
        estimated_effort: str = "",
    ) -> dict[str, Any]:
        step = {
            "step_id": uuid.uuid4().hex[:8],
            "description": description,
            "assignee": assignee,
            "done": done,
            "estimated_effort": estimated_effort,
        }
        self.steps.append(step)
        self.updated_at = time.time()
        return step

    def mark_step_done(self, step_id: str) -> bool:
        for step in self.steps:
            if step.get("step_id") == step_id:
                step["done"] = True
                self.updated_at = time.time()
                return True
        return False

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.get("done"))
        return round(done / len(self.steps), 4)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanArtifact:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

_DEFAULT_DIR = Path.home() / ".orbit" / "plans"


def _ensure_dir(directory: Optional[Path] = None) -> Path:
    d = directory or _DEFAULT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_artifact(
    artifact: PlanArtifact,
    *,
    directory: Optional[Path | str] = None,
) -> Path:
    """Write *artifact* to disk as JSON. Returns the file path."""
    d = _ensure_dir(Path(directory) if directory else None)
    artifact.updated_at = time.time()
    fp = d / f"{artifact.artifact_id}.json"
    fp.write_text(json.dumps(artifact.to_dict(), indent=2))
    return fp


def load_artifact(
    artifact_id: str,
    *,
    directory: Optional[Path | str] = None,
) -> Optional[PlanArtifact]:
    """Load a single artifact by id. Returns ``None`` if not found."""
    d = _ensure_dir(Path(directory) if directory else None)
    fp = d / f"{artifact_id}.json"
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_text())
        return PlanArtifact.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


def list_artifacts(
    *,
    directory: Optional[Path | str] = None,
    status: Optional[str] = None,
    plan_type: Optional[str] = None,
) -> list[PlanArtifact]:
    """Return all artifacts, optionally filtered by status or type."""
    d = _ensure_dir(Path(directory) if directory else None)
    results: list[PlanArtifact] = []
    for fp in sorted(d.glob("*.json")):
        try:
            data = json.loads(fp.read_text())
            art = PlanArtifact.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError):
            continue
        if status and art.status != status:
            continue
        if plan_type and art.plan_type != plan_type:
            continue
        results.append(art)
    return results


def delete_artifact(
    artifact_id: str,
    *,
    directory: Optional[Path | str] = None,
) -> bool:
    """Delete an artifact file. Returns ``True`` if it existed."""
    d = _ensure_dir(Path(directory) if directory else None)
    fp = d / f"{artifact_id}.json"
    if fp.exists():
        fp.unlink()
        return True
    return False
