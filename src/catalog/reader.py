"""Catalog manifest reader with caching and public contract generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import (
    CatalogCounts,
    CatalogManifest,
    EntryStatus,
    summarize_catalog_counts,
    validate_catalog_manifest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Candidate search paths (relative to package root)
# ---------------------------------------------------------------------------

_MANIFEST_CANDIDATE_PATHS: tuple[tuple[str, ...], ...] = (
    ("templates", "catalog-manifest.json"),
    ("src", "catalog", "manifest.json"),
    ("dist", "catalog", "manifest.json"),
)

# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_cached_manifest: CatalogManifest | None = None
_cached_path: Path | None = None


def _get_package_root() -> Path:
    """Return the project root (two levels above this file)."""
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_manifest_path() -> Path | None:
    """Return the first existing manifest path, or ``None``."""
    root = _get_package_root()
    for parts in _MANIFEST_CANDIDATE_PATHS:
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            return candidate
    return None


def read_catalog_manifest() -> CatalogManifest:
    """Read, validate, and cache the catalog manifest.

    Raises ``FileNotFoundError`` if no manifest is found and
    ``ValueError`` on validation failure.
    """
    global _cached_manifest, _cached_path

    path = resolve_manifest_path()
    if path is None:
        raise FileNotFoundError("No catalog manifest found in any candidate path")

    if _cached_manifest is not None and _cached_path == path:
        return _cached_manifest

    raw = json.loads(path.read_text(encoding="utf-8"))
    manifest = validate_catalog_manifest(raw)

    _cached_manifest = manifest
    _cached_path = path
    return manifest


def try_read_catalog_manifest() -> CatalogManifest | None:
    """Like :func:`read_catalog_manifest` but returns ``None`` on error."""
    try:
        return read_catalog_manifest()
    except Exception:
        logger.debug("Failed to read catalog manifest", exc_info=True)
        return None


def get_catalog_counts() -> CatalogCounts:
    """Read the manifest and return summarised counts."""
    return summarize_catalog_counts(read_catalog_manifest())


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PublicCatalogContract:
    generated_at: str
    version: str
    counts: CatalogCounts
    core_skills: tuple[str, ...]
    skills: tuple[Any, ...]
    agents: tuple[Any, ...]
    aliases: tuple[dict[str, str], ...]
    internal_hidden: tuple[str, ...]


def to_public_catalog_contract() -> PublicCatalogContract:
    """Transform the manifest into a public-facing contract."""
    manifest = read_catalog_manifest()
    counts = summarize_catalog_counts(manifest)

    core_skills = tuple(
        s.name for s in manifest.skills if s.core and s.status == EntryStatus.ACTIVE
    )

    aliases = tuple(
        {"name": s.name, "canonical": s.canonical}
        for s in manifest.skills
        if s.status in (EntryStatus.ALIAS, EntryStatus.MERGED) and s.canonical
    )

    internal_hidden = tuple(
        s.name for s in manifest.skills if s.status == EntryStatus.INTERNAL
    )

    return PublicCatalogContract(
        generated_at=datetime.now(timezone.utc).isoformat(),
        version=manifest.catalog_version,
        counts=counts,
        core_skills=core_skills,
        skills=manifest.skills,
        agents=manifest.agents,
        aliases=aliases,
        internal_hidden=internal_hidden,
    )
