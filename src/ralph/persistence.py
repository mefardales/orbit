"""Ralph persistence: canonical artifacts, progress ledger, and visual feedback."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..visual.constants import VISUAL_NEXT_ACTIONS_LIMIT, VisualVerdictStatus

LEGACY_PRD_PATH = ".pyclaude/prd.json"
LEGACY_PROGRESS_PATH = ".pyclaude/progress.txt"
PRD_PREFIX = "prd-"
PRD_SUFFIX = ".md"
DEFAULT_VISUAL_THRESHOLD = 90


@dataclass
class RalphVisualFeedback:
    score: int
    verdict: VisualVerdictStatus
    category_match: bool
    differences: list[str]
    suggestions: list[str]
    reasoning: str = ""
    threshold: Optional[int] = None


@dataclass
class RalphProgressLedger:
    schema_version: int = 2
    source: Optional[str] = None
    source_sha256: Optional[str] = None
    strategy: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    visual_feedback: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RalphCanonicalArtifacts:
    canonical_prd_path: Optional[str] = None
    canonical_progress_path: str = ""
    migrated_prd: bool = False
    migrated_progress: bool = False


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _slugify(raw: str) -> str:
    slug = raw.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")[:48]
    return slug or "legacy"


def _stable_json(value: Any) -> str:
    """Produce a deterministic JSON string with sorted keys."""
    if value is None or not isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(_stable_json(item) for item in value) + "]"
    entries = sorted(value.items())
    parts = [f"{json.dumps(k)}:{_stable_json(v)}" for k, v in entries]
    return "{" + ",".join(parts) + "}"


def _stable_json_pretty(value: Any) -> str:
    return json.dumps(json.loads(_stable_json(value)), indent=2)


def _get_state_dir(cwd: str, session_id: Optional[str] = None) -> str:
    base = str(Path(cwd) / ".pyclaude" / "state")
    if session_id:
        return str(Path(base) / session_id)
    return base


def _resolve_legacy_prd_title(parsed: dict[str, Any]) -> str:
    for key in ("project", "title", "branchName", "description"):
        candidate = parsed.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return "Legacy Ralph PRD"


def _list_canonical_prd_files(cwd: str) -> list[str]:
    plans_dir = Path(cwd) / ".pyclaude" / "plans"
    if not plans_dir.exists():
        return []
    try:
        files = sorted(
            f.name for f in plans_dir.iterdir()
            if f.is_file() and f.name.startswith(PRD_PREFIX) and f.name.endswith(PRD_SUFFIX)
        )
        return [str(plans_dir / f) for f in files]
    except OSError:
        return []


def _split_progress_lines(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.strip()]


def _ensure_canonical_progress_ledger_file(path: str) -> None:
    if os.path.exists(path):
        return
    now = datetime.now(timezone.utc).isoformat()
    payload = RalphProgressLedger(created_at=now, updated_at=now)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(_stable_json_pretty(_ledger_to_dict(payload)) + "\n")


def _ledger_to_dict(ledger: RalphProgressLedger) -> dict[str, Any]:
    return {
        "schema_version": ledger.schema_version,
        "source": ledger.source,
        "source_sha256": ledger.source_sha256,
        "strategy": ledger.strategy,
        "created_at": ledger.created_at,
        "updated_at": ledger.updated_at,
        "entries": ledger.entries,
        "visual_feedback": ledger.visual_feedback,
    }


def _read_canonical_progress_ledger(path: str) -> RalphProgressLedger:
    if not os.path.exists(path):
        _ensure_canonical_progress_ledger_file(path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        parsed = json.loads(Path(path).read_text(encoding="utf-8"))
        return RalphProgressLedger(
            schema_version=parsed.get("schema_version", 2) if isinstance(parsed.get("schema_version"), int) else 2,
            source=parsed.get("source"),
            source_sha256=parsed.get("source_sha256"),
            strategy=parsed.get("strategy"),
            entries=parsed.get("entries", []) if isinstance(parsed.get("entries"), list) else [],
            visual_feedback=parsed.get("visual_feedback", []) if isinstance(parsed.get("visual_feedback"), list) else [],
            created_at=parsed.get("created_at", now) if isinstance(parsed.get("created_at"), str) else now,
            updated_at=now,
        )
    except (json.JSONDecodeError, OSError):
        return RalphProgressLedger(created_at=now, updated_at=now)


def _write_migration_marker(cwd: str, patch: dict[str, Any]) -> None:
    marker_path = Path(cwd) / ".pyclaude" / "plans" / "ralph-migration-marker.json"
    existing: dict[str, Any] = {}
    if marker_path.exists():
        try:
            existing = json.loads(marker_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    merged = {"compatibility_window": "legacy-read-only-one-release-cycle", **existing, **patch}
    marker_path.write_text(_stable_json_pretty(merged) + "\n")


def _migrate_legacy_prd_if_needed(
    cwd: str, existing_canonical_prd: Optional[str]
) -> tuple[Optional[str], bool]:
    if existing_canonical_prd:
        return existing_canonical_prd, False

    legacy_prd_path = Path(cwd) / LEGACY_PRD_PATH
    if not legacy_prd_path.exists():
        return None, False

    legacy_raw = legacy_prd_path.read_text(encoding="utf-8")
    try:
        legacy_parsed = json.loads(legacy_raw)
    except json.JSONDecodeError:
        legacy_parsed = {"parse_error": "invalid_json", "raw": legacy_raw}

    plans_dir = Path(cwd) / ".pyclaude" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    title = _resolve_legacy_prd_title(legacy_parsed)
    base_slug = _slugify(title)
    canonical_prd_path = plans_dir / f"prd-{base_slug}.md"
    counter = 1
    while canonical_prd_path.exists():
        canonical_prd_path = plans_dir / f"prd-{base_slug}-{counter}.md"
        counter += 1

    markdown = "\n".join([
        f"# {title}",
        "",
        "> Migrated from legacy `.pyclaude/prd.json` (read-only compatibility import).",
        "",
        "## Migration Marker",
        f"- Source: `{LEGACY_PRD_PATH}`",
        f"- Source SHA256: `{_sha256(legacy_raw)}`",
        "- Strategy: one-way conversion to canonical PRD markdown",
        "",
        "## Legacy Snapshot",
        "```json",
        _stable_json_pretty(legacy_parsed),
        "```",
        "",
    ])
    canonical_prd_path.write_text(markdown)

    _write_migration_marker(cwd, {
        "prd_migration": {
            "source": LEGACY_PRD_PATH,
            "source_sha256": _sha256(legacy_raw),
            "canonical_path": str(canonical_prd_path),
            "strategy": "one-way-read-only",
        }
    })
    return str(canonical_prd_path), True


def _migrate_legacy_progress_if_needed(cwd: str, canonical_progress_path: str) -> bool:
    if os.path.exists(canonical_progress_path):
        return False

    legacy_path = Path(cwd) / LEGACY_PROGRESS_PATH
    if not legacy_path.exists():
        return False

    raw = legacy_path.read_text(encoding="utf-8")
    lines = _split_progress_lines(raw)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 2,
        "source": LEGACY_PROGRESS_PATH,
        "source_sha256": _sha256(raw),
        "strategy": "one-way-read-only",
        "created_at": now,
        "updated_at": now,
        "entries": [{"index": i + 1, "text": line} for i, line in enumerate(lines)],
        "visual_feedback": [],
    }
    Path(canonical_progress_path).parent.mkdir(parents=True, exist_ok=True)
    Path(canonical_progress_path).write_text(_stable_json_pretty(payload) + "\n")

    _write_migration_marker(cwd, {
        "progress_migration": {
            "source": LEGACY_PROGRESS_PATH,
            "source_sha256": _sha256(raw),
            "canonical_path": canonical_progress_path,
            "imported_entries": len(lines),
            "strategy": "one-way-read-only",
        }
    })
    return True


def record_ralph_visual_feedback(
    cwd: str,
    feedback: RalphVisualFeedback,
    session_id: Optional[str] = None,
) -> None:
    """Record visual feedback into the canonical progress ledger."""
    canonical_progress_path = str(Path(_get_state_dir(cwd, session_id)) / "ralph-progress.json")
    ledger = _read_canonical_progress_ledger(canonical_progress_path)

    threshold = feedback.threshold if feedback.threshold is not None else DEFAULT_VISUAL_THRESHOLD
    next_actions = (
        [s.strip() for s in feedback.suggestions if s.strip()]
        + [f"Resolve difference: {d.strip()}" for d in feedback.differences if d.strip()]
    )[:VISUAL_NEXT_ACTIONS_LIMIT]

    entry: dict[str, Any] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "score": feedback.score,
        "verdict": feedback.verdict,
        "category_match": feedback.category_match,
        "threshold": threshold,
        "passes_threshold": feedback.score >= threshold,
        "differences": feedback.differences,
        "suggestions": feedback.suggestions,
        "reasoning": feedback.reasoning or "",
        "next_actions": next_actions,
        "qualitative_feedback": {
            "summary": feedback.reasoning or feedback.verdict,
            "next_actions": next_actions,
        },
    }

    vf = ledger.visual_feedback if isinstance(ledger.visual_feedback, list) else []
    vf.append(entry)
    ledger.visual_feedback = vf[-30:]
    ledger.updated_at = datetime.now(timezone.utc).isoformat()

    Path(canonical_progress_path).parent.mkdir(parents=True, exist_ok=True)
    Path(canonical_progress_path).write_text(_stable_json_pretty(_ledger_to_dict(ledger)) + "\n")


def ensure_canonical_ralph_artifacts(
    cwd: str, session_id: Optional[str] = None
) -> RalphCanonicalArtifacts:
    """Ensure canonical ralph artifacts exist, migrating legacy files if needed."""
    canonical_progress_path = str(Path(_get_state_dir(cwd, session_id)) / "ralph-progress.json")
    (Path(cwd) / ".pyclaude" / "plans").mkdir(parents=True, exist_ok=True)
    Path(_get_state_dir(cwd, session_id)).mkdir(parents=True, exist_ok=True)

    canonical_prd_files = _list_canonical_prd_files(cwd)
    prd_path, migrated_prd = _migrate_legacy_prd_if_needed(
        cwd, canonical_prd_files[0] if canonical_prd_files else None
    )
    migrated_progress = _migrate_legacy_progress_if_needed(cwd, canonical_progress_path)
    _ensure_canonical_progress_ledger_file(canonical_progress_path)

    return RalphCanonicalArtifacts(
        canonical_prd_path=prd_path,
        canonical_progress_path=canonical_progress_path,
        migrated_prd=migrated_prd,
        migrated_progress=migrated_progress,
    )
